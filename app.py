import os
from datetime import datetime, date, time, timedelta
from functools import wraps
import secrets
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import and_, inspect, text
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'troque-esta-chave-antes-de-publicar')
database_url = os.environ.get(
    'DATABASE_URL',
    'sqlite:///barberflow.db'
)

if database_url.startswith('postgres://'):
    database_url = database_url.replace(
        'postgres://',
        'postgresql+psycopg://',
        1
    )
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace(
        'postgresql://',
        'postgresql+psycopg://',
        1
    )

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=[])

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), default='')
    price = db.Column(db.Float, nullable=False, default=0)
    duration = db.Column(db.Integer, nullable=False, default=30)
    active = db.Column(db.Boolean, default=True)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    service = db.relationship('Service')
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False, default='presencial')
    status = db.Column(db.String(20), nullable=False, default='confirmado')
    notes = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    manage_token = db.Column(db.String(64), unique=True, index=True, nullable=True)

class AdminNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    event_type = db.Column(db.String(30), nullable=False, default='info')
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)

class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

DEFAULTS = {
    'shop_name': 'BarberFlow Barber Shop', 'opening_time': '09:00',
    'closing_time': '19:00', 'slot_interval': '15', 'work_days': '0,1,2,3,4,5',
    'pix_key': '', 'whatsapp': '', 'closed_dates': '',
    'instagram_url': '', 'address': ''
}

def setting(key):
    row = db.session.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, '')

def save_setting(key, value):
    row = db.session.get(Setting, key)
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))

def ensure_schema():
    """Additive migration for existing SQLite databases; preserves old bookings."""
    db.create_all()
    inspector = inspect(db.engine)
    columns = {c['name'] for c in inspector.get_columns('appointment')}
    if 'manage_token' not in columns:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE appointment ADD COLUMN manage_token VARCHAR(64)'))
    with db.engine.begin() as conn:
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_appointment_manage_token ON appointment (manage_token)'))
    # Existing bookings get private management links when a client opens the new flow only;
    # no customer data is exposed through a public phone-number lookup.

def phone_digits(value):
    return ''.join(char for char in (value or '') if char.isdigit())

def notify_admin(title, message, event_type='info', appointment_id=None):
    item = AdminNotification(title=title, message=message, event_type=event_type,
                             appointment_id=appointment_id)
    db.session.add(item)
    db.session.commit()
    payload = {'id': item.id, 'title': item.title, 'message': item.message,
               'event_type': item.event_type, 'created_at': item.created_at.strftime('%d/%m %H:%M')}
    socketio.emit('admin_notification', payload, namespace='/admin')

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {'shop_name': setting('shop_name') if db.engine and db.inspect(db.engine).has_table('setting') else DEFAULTS['shop_name'], 'timedelta': timedelta}

@app.route('/')
def home():
    instagram_url = setting('instagram_url').strip()
    instagram_username = ''
    if instagram_url:
        from urllib.parse import urlparse
        parsed = urlparse(instagram_url if '://' in instagram_url else 'https://' + instagram_url)
        if parsed.netloc.lower().endswith('instagram.com'):
            instagram_username = parsed.path.strip('/').split('/')[0]
    return render_template('home.html', instagram_url=instagram_url,
        instagram_username=instagram_username, address=setting('address'))

@app.route('/agendar-horario')
def booking_page():
    services = Service.query.filter_by(active=True).order_by(Service.name).all()
    return render_template('booking.html', services=services)


def get_available_slots(selected, service, exclude_appointment_id=None):
    """Retorna horários disponíveis, respeitando o intervalo de almoço."""
    work_days = [
        int(x) for x in setting('work_days').split(',')
        if x.strip().isdigit()
    ]

    day_text = selected.isoformat()
    closed_dates = [
        x.strip() for x in setting('closed_dates').split(',')
        if x.strip()
    ]

    if (
        selected < date.today()
        or selected.weekday() not in work_days
        or day_text in closed_dates
    ):
        return [], 0

    start = datetime.combine(
        selected,
        time.fromisoformat(setting('opening_time'))
    )

    close = datetime.combine(
        selected,
        time.fromisoformat(setting('closing_time'))
    )

    # Intervalo de almoço
    lunch_start = datetime.combine(selected, time(12, 0))
    lunch_end = datetime.combine(selected, time(14, 0))

    interval = max(5, int(setting('slot_interval') or 15))

    day_start = datetime.combine(selected, time.min)
    day_end = day_start + timedelta(days=1)

    existing = Appointment.query.filter(
        Appointment.starts_at >= day_start,
        Appointment.starts_at < day_end,
        Appointment.status != 'cancelado'
    ).all()

    if exclude_appointment_id is not None:
        existing = [
            item for item in existing
            if item.id != exclude_appointment_id
        ]

    available = []
    total = 0
    cursor = start
    now = datetime.now()

    while cursor < close:
        end = cursor + timedelta(minutes=service.duration)

        # Verifica se o serviço invade o horário de almoço
        overlaps_lunch = (
    cursor.time() >= time(12, 0)
    and cursor.time() < time(14, 0)
)

        if not overlaps_lunch:
            if selected > date.today() or cursor > now:
                total += 1

                conflict = any(
                    cursor < appointment.ends_at
                    and end > appointment.starts_at
                    for appointment in existing
                )

                if not conflict:
                    available.append(cursor.strftime('%H:%M'))

        cursor += timedelta(minutes=interval)

    return available, total



@app.route('/api/calendar')
def calendar_availability():
    service_id = request.args.get('service_id', type=int)
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    service = db.session.get(Service, service_id) if service_id else None
    if not service or not service.active or not year or not month or month < 1 or month > 12:
        return jsonify({'days': {}, 'error': 'Parâmetros inválidos'}), 400

    import calendar
    _, days_in_month = calendar.monthrange(year, month)
    result = {}
    for day_number in range(1, days_in_month + 1):
        selected = date(year, month, day_number)
        available, total = get_available_slots(selected, service)
        if total:
            free = len(available)
            occupied_percent = round(((total - free) / total) * 100)
            if free == 0:
                label = 'Esgotado'
            elif free <= 2:
                label = f'Últimas {free} vagas'
            else:
                label = f'{free} horários livres'
            result[selected.isoformat()] = {
                'available': free,
                'total': total,
                'occupied_percent': occupied_percent,
                'label': label,
                'selectable': free > 0
            }
        else:
            result[selected.isoformat()] = {
                'available': 0, 'total': 0, 'occupied_percent': 100,
                'label': 'Indisponível', 'selectable': False
            }
    return jsonify({'days': result})


@app.route('/api/slots')
def slots():
    day_text = request.args.get('date', '')
    service_id = request.args.get('service_id', type=int)
    try:
        selected = date.fromisoformat(day_text)
    except ValueError:
        return jsonify({'slots': [], 'error': 'Data inválida'}), 400
    service = db.session.get(Service, service_id) if service_id else None
    if not service or not service.active:
        return jsonify({'slots': [], 'error': 'Serviço inválido'}), 400
    available, total = get_available_slots(selected, service)
    return jsonify({'slots': available, 'total': total, 'available': len(available)})

@app.route('/agendar', methods=['POST'])
def book():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    service = db.session.get(Service, request.form.get('service_id', type=int))
    day_text, hour_text = request.form.get('date', ''), request.form.get('time', '')
    method = request.form.get('payment_method', 'presencial')
    if not name or len(name) < 2 or not phone or not service or not service.active or method not in ('presencial', 'pix'):
        flash('Confira os dados e tente novamente.', 'error')
        return redirect(url_for('booking_page'))
    try:
        starts = datetime.combine(date.fromisoformat(day_text), time.fromisoformat(hour_text))
    except ValueError:
        flash('Data ou horário inválido.', 'error')
        return redirect(url_for('booking_page'))
    ends = starts + timedelta(minutes=service.duration)
    available_slots, _ = get_available_slots(starts.date(), service)
    if starts.strftime('%H:%M') not in available_slots:
        flash('Esse horário não está mais disponível. Escolha outro.', 'error')
        return redirect(url_for('booking_page'))
    conflict = Appointment.query.filter(Appointment.status != 'cancelado', Appointment.starts_at < ends, Appointment.ends_at > starts).first()
    if conflict:
        flash('Esse horário acabou de ser reservado. Escolha outro.', 'error')
        return redirect(url_for('booking_page'))
    appt = Appointment(customer_name=name, phone=phone, service=service, starts_at=starts, ends_at=ends,
                        payment_method=method, manage_token=secrets.token_urlsafe(32))
    db.session.add(appt)
    db.session.commit()
    session['customer_access_token'] = appt.manage_token
    notify_admin('Novo agendamento', f'{name} marcou {service.name} para {starts.strftime("%d/%m às %H:%M")}.',
                 'booking', appt.id)
    return render_template('confirmation.html', appt=appt, whatsapp=setting('whatsapp'),
                           pix_key=setting('pix_key'), manage_token=appt.manage_token)

@app.route('/meus-cortes', methods=['GET', 'POST'])
def customer_access():
    if request.method == 'POST':
        token = request.form.get('access_token', '').strip()
        if Appointment.query.filter_by(manage_token=token).first():
            session['customer_access_token'] = token
            return redirect(url_for('customer_portal', token=token))
        flash('Código de acesso inválido. Use o link ou código recebido ao concluir seu agendamento.', 'error')
    token = session.get('customer_access_token')
    if token and Appointment.query.filter_by(manage_token=token).first():
        return redirect(url_for('customer_portal', token=token))
    return render_template('customer_access.html')

@app.route('/cliente/<token>')
def customer_portal(token):
    appt = Appointment.query.filter_by(manage_token=token).first_or_404()
    # The unguessable token is the private access credential; no phone-only lookup.
    items = [item for item in Appointment.query.order_by(Appointment.starts_at.desc()).all()
             if phone_digits(item.phone) == phone_digits(appt.phone)]
    return render_template('customer_portal.html', appointments=items, access_token=token, now=datetime.now())

@app.route('/cliente/<token>/cancelar/<int:appointment_id>', methods=['POST'])
def customer_cancel(token, appointment_id):
    access = Appointment.query.filter_by(manage_token=token).first_or_404()
    appt = db.get_or_404(Appointment, appointment_id)
    if phone_digits(appt.phone) != phone_digits(access.phone):
        return ('Não encontrado', 404)
    if appt.status == 'cancelado':
        flash('Este agendamento já está cancelado.', 'error')
    elif appt.status != 'confirmado':
        flash('Este agendamento não pode mais ser cancelado por aqui.', 'error')
    elif appt.starts_at <= datetime.now() + timedelta(hours=12):
        flash('Cancelamentos precisam ser feitos com pelo menos 12 horas de antecedência. Fale com a barbearia para solicitar ajuda.', 'error')
    else:
        appt.status = 'cancelado'
        db.session.commit()
        notify_admin('Agendamento cancelado', f'{appt.customer_name} cancelou {appt.service.name} de {appt.starts_at.strftime("%d/%m às %H:%M")}.',
                     'cancellation', appt.id)
        flash('Agendamento cancelado. O horário voltou a ficar disponível.', 'success')
    return redirect(url_for('customer_portal', token=token))

@app.route('/api/admin/notifications')
@admin_required
def admin_notifications():
    items = AdminNotification.query.order_by(AdminNotification.created_at.desc()).limit(30).all()
    return jsonify({'notifications': [{'id': n.id, 'title': n.title, 'message': n.message,
        'event_type': n.event_type, 'read': n.read, 'created_at': n.created_at.strftime('%d/%m %H:%M')}
        for n in items], 'unread': AdminNotification.query.filter_by(read=False).count()})

@app.route('/api/admin/notifications/read', methods=['POST'])
@admin_required
def mark_notifications_read():
    AdminNotification.query.filter_by(read=False).update({'read': True})
    db.session.commit()
    return jsonify({'ok': True})

@socketio.on('connect', namespace='/admin')
def admin_socket_connect():
    if not session.get('admin_id'):
        return False

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Admin.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user and check_password_hash(user.password_hash, request.form.get('password', '')):
            session.clear(); session['admin_id'] = user.id
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Usuário ou senha incorretos.', 'error')
    return render_template('login.html')

@app.route('/sair')
def logout():
    session.clear(); return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def dashboard():
    today = date.today()
    today_appts = Appointment.query.filter(db.func.date(Appointment.starts_at) == today.isoformat()).order_by(Appointment.starts_at).all()
    upcoming = Appointment.query.filter(Appointment.starts_at >= datetime.now(), Appointment.status != 'cancelado').order_by(Appointment.starts_at).limit(8).all()
    month_start = datetime(today.year, today.month, 1)
    completed = Appointment.query.filter(Appointment.starts_at >= month_start, Appointment.status == 'concluido').all()
    revenue = sum(a.service.price for a in completed)
    month_count = Appointment.query.filter(Appointment.starts_at >= month_start, Appointment.status != 'cancelado').count()
    return render_template('dashboard.html', today_appts=today_appts, upcoming=upcoming, revenue=revenue, month_count=month_count)

@app.route('/admin/agendamentos')
@admin_required
def appointments():
    selected = request.args.get('date', '')
    query = Appointment.query
    if selected:
        try:
            d = date.fromisoformat(selected)
            query = query.filter(Appointment.starts_at >= datetime.combine(d, time.min), Appointment.starts_at < datetime.combine(d + timedelta(days=1), time.min))
        except ValueError: pass
    items = query.order_by(Appointment.starts_at.desc()).limit(250).all()
    return render_template('appointments.html', appointments=items, selected=selected)

@app.route('/admin/agendamento/<int:appointment_id>/status', methods=['POST'])
@admin_required
def update_status(appointment_id):
    appt = db.get_or_404(Appointment, appointment_id)
    status = request.form.get('status')
    if status in ('confirmado', 'concluido', 'cancelado', 'faltou'):
        old_status = appt.status
        appt.status = status
        db.session.commit()
        if old_status != status and status == 'cancelado':
            notify_admin('Agendamento cancelado', f'{appt.customer_name} teve o agendamento de {appt.starts_at.strftime("%d/%m às %H:%M")} cancelado no painel.', 'cancellation', appt.id)
        flash('Agendamento atualizado.', 'success')
    return redirect(request.referrer or url_for('appointments'))


@app.route('/admin/servicos', methods=['GET', 'POST'])
@admin_required
def services():
    if request.method == 'POST':
        try:
            price = float(request.form.get('price', '0').replace(',', '.'))
            name = request.form.get('name', '').strip()

            if not name or price < 0:
                raise ValueError()

            db.session.add(Service(
                name=name,
                description=request.form.get('description', '').strip(),
                price=price
            ))

            db.session.commit()
            flash('Serviço cadastrado.', 'success')

        except ValueError:
            flash('Confira o nome e o preço do serviço.', 'error')

        return redirect(url_for('services'))

    return render_template(
        'services.html',
        services=Service.query.order_by(Service.name).all()
    )


@app.route('/admin/servico/<int:service_id>/toggle', methods=['POST'])
@admin_required
def toggle_service(service_id):
    item = db.get_or_404(Service, service_id)
    item.active = not item.active
    db.session.commit()

    return redirect(url_for('services'))


@app.route('/admin/configuracoes', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        for key in ('shop_name', 'opening_time', 'closing_time', 'slot_interval', 'pix_key', 'whatsapp', 'closed_dates', 'instagram_url', 'address'):
            save_setting(key, request.form.get(key, '').strip())
        days = request.form.getlist('work_days')
        save_setting('work_days', ','.join(str(int(x)) for x in days if x.isdigit() and 0 <= int(x) <= 6))
        db.session.commit(); flash('Configurações salvas.', 'success'); return redirect(url_for('settings'))
    return render_template('settings.html', values={k: setting(k) for k in DEFAULTS}, work_days=[int(x) for x in setting('work_days').split(',') if x.isdigit()])

@app.route('/admin/alterar-senha', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        admin = db.get_or_404(Admin, session['admin_id'])
        if not check_password_hash(admin.password_hash, request.form.get('current_password', '')):
            flash('Senha atual incorreta.', 'error')
        elif len(request.form.get('new_password', '')) < 10:
            flash('A nova senha precisa ter pelo menos 10 caracteres.', 'error')
        else:
            admin.password_hash = generate_password_hash(request.form['new_password']); db.session.commit()
            flash('Senha alterada.', 'success'); return redirect(url_for('dashboard'))
    return render_template('password.html')

@app.route('/admin/relatorios')
@admin_required
def reports():
    today = date.today(); first = datetime(today.year, today.month, 1)
    done = Appointment.query.filter(Appointment.starts_at >= first, Appointment.status == 'concluido').all()
    by_service = {}
    for a in done: by_service[a.service.name] = by_service.get(a.service.name, 0) + 1
    return render_template('reports.html', revenue=sum(a.service.price for a in done), count=len(done), by_service=by_service)

@app.cli.command('init-db')
def init_db():
    db.create_all()
    if not Admin.query.first():
        username = os.environ.get('ADMIN_USER', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'BarberFlow@2026!')
        db.session.add(Admin(username=username, password_hash=generate_password_hash(password)))
    for key, value in DEFAULTS.items():
        if not db.session.get(Setting, key): db.session.add(Setting(key=key, value=value))
    if not Service.query.first():
        db.session.add_all([
            Service(name='Corte tradicional', description='Corte na tesoura ou máquina', price=35, duration=40),
            Service(name='Corte + barba', description='Corte completo com acabamento de barba', price=55, duration=60),
            Service(name='Barba', description='Modelagem e acabamento', price=25, duration=30),
        ])
    db.session.commit()
    print('Banco inicializado. Login padrão: admin | senha: BarberFlow@2026! (altere após entrar)')

if __name__ == '__main__':
    with app.app_context():
        ensure_schema()
        if not Admin.query.first():
            db.session.add(Admin(username=os.environ.get('ADMIN_USER', 'admin'), password_hash=generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'BarberFlow@2026!'))))
        for key, value in DEFAULTS.items():
            if not db.session.get(Setting, key): db.session.add(Setting(key=key, value=value))
        if not Service.query.first():
            db.session.add_all([Service(name='Corte tradicional', description='Corte na tesoura ou máquina', price=35, duration=40), Service(name='Corte + barba', description='Corte completo com acabamento de barba', price=55, duration=60), Service(name='Barba', description='Modelagem e acabamento', price=25, duration=30)])
        db.session.commit()
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, allow_unsafe_werkzeug=True)
