(() => {
  const form = document.querySelector('#booking-form');
  if (!form) return;

  const panels = [...document.querySelectorAll('.wizard-panel')];
  const dots = [...document.querySelectorAll('.wizard-dot')];
  const stepCounter = document.querySelector('#step-counter');
  const stepName = document.querySelector('#step-name');
  const progressFill = document.querySelector('#wizard-progress-fill');
  const serviceIdInput = document.querySelector('#selected-service-id');
  const dateInput = document.querySelector('#selected-date');
  const timeInput = document.querySelector('#selected-time');
  const serviceCards = [...document.querySelectorAll('.service-choice')];
  const calendarGrid = document.querySelector('#calendar-grid');
  const monthLabel = document.querySelector('#calendar-month-label');
  const selectedDayDetail = document.querySelector('#selected-day-detail');
  const dayTitle = document.querySelector('#selected-day-title');
  const dayCount = document.querySelector('#selected-day-count');
  const dayCaption = document.querySelector('#selected-day-caption');
  const availabilityFill = document.querySelector('#availability-progress-fill');
  const timeGrid = document.querySelector('#time-choice-grid');
  const toDate = document.querySelector('#to-date');
  const toTime = document.querySelector('#to-time');
  const toDetails = document.querySelector('#to-details');

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let currentMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  let selectedService = null;
  let selectedAvailability = null;
  let selectedTime = '';
  let calendarDays = {};
  const stepTitles = ['Escolha o serviço', 'Escolha a data', 'Escolha o horário', 'Seus dados'];
  const monthFormatter = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' });
  const dateFormatter = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });

  function goToStep(step) {
    panels.forEach((panel, index) => {
      const active = index + 1 === step;
      panel.hidden = !active;
      panel.classList.toggle('active', active);
    });
    dots.forEach((dot, index) => {
      dot.classList.toggle('active', index + 1 <= step);
      dot.classList.toggle('current', index + 1 === step);
    });
    stepCounter.textContent = `ETAPA ${step} DE 4`;
    stepName.textContent = stepTitles[step - 1];
    progressFill.style.width = `${step * 25}%`;
    document.querySelector('.booking-wizard-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  serviceCards.forEach(card => card.addEventListener('click', () => {
    serviceCards.forEach(item => item.classList.remove('selected'));
    card.classList.add('selected');
    selectedService = {
      id: card.dataset.serviceId,
      name: card.dataset.serviceName,
      price: Number(card.dataset.servicePrice),
      duration: Number(card.dataset.serviceDuration)
    };
    serviceIdInput.value = selectedService.id;
    toDate.disabled = false;
  }));

  function dateKey(year, month, day) {
    return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  async function loadCalendar() {
    if (!selectedService) return;
    monthLabel.textContent = monthFormatter.format(currentMonth).replace(/^./, c => c.toLocaleUpperCase('pt-BR'));
    calendarGrid.innerHTML = '<div class="calendar-loading">Consultando disponibilidade...</div>';
    selectedAvailability = null;
    dateInput.value = '';
    toTime.disabled = true;
    selectedDayDetail.hidden = true;
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth() + 1;
    try {
      const response = await fetch(`${window.BARBERFLOW.calendarUrl}?service_id=${encodeURIComponent(selectedService.id)}&year=${year}&month=${month}`);
      if (!response.ok) throw new Error('Não foi possível consultar as datas.');
      const data = await response.json();
      calendarDays = data.days || {};
      renderCalendar();
    } catch (error) {
      calendarGrid.innerHTML = `<p class="calendar-error">${error.message}</p>`;
    }
  }

  function renderCalendar() {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstWeekday = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    calendarGrid.innerHTML = '';
    for (let blank = 0; blank < firstWeekday; blank++) {
      const spacer = document.createElement('span');
      spacer.className = 'calendar-empty';
      calendarGrid.appendChild(spacer);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const key = dateKey(year, month, day);
      const info = calendarDays[key] || { available: 0, total: 0, occupied_percent: 100, label: 'Indisponível', selectable: false };
      const dayDate = new Date(year, month, day);
      const isPast = dayDate < today;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'calendar-day';
      if (isPast || !info.selectable) button.classList.add('unavailable');
      else if (info.available <= 2) button.classList.add('limited');
      else button.classList.add('available');
      if (dateInput.value === key) button.classList.add('selected');
      button.disabled = isPast || !info.selectable;
      button.innerHTML = `<span class="calendar-day-number">${day}</span><span class="calendar-day-status">${isPast ? '—' : (info.available === 0 ? 'Cheio' : `${info.available} livres`)}</span><span class="calendar-day-meter"><i style="width:${info.occupied_percent || 0}%"></i></span>`;
      button.title = info.label;
      button.addEventListener('click', () => chooseDate(key, info));
      calendarGrid.appendChild(button);
    }
  }

  function chooseDate(key, info) {
    if (!info.selectable) return;
    dateInput.value = key;
    selectedAvailability = info;
    toTime.disabled = false;
    renderCalendar();
    const [year, month, day] = key.split('-').map(Number);
    dayTitle.textContent = dateFormatter.format(new Date(year, month - 1, day));
    dayCount.textContent = info.available <= 2 ? `Restam ${info.available} ${info.available === 1 ? 'horário' : 'horários'}` : `${info.available} horários livres`;
    availabilityFill.style.width = `${info.occupied_percent}%`;
    dayCaption.textContent = info.available <= 2
      ? 'Atenção: esta data está quase completa. Escolha seu horário para garantir a vaga.'
      : 'A barra verde mostra quanto da agenda desta data já está preenchida.';
    selectedDayDetail.hidden = false;
  }

  document.querySelector('#prev-month').addEventListener('click', () => {
    const previous = new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1);
    if (previous < new Date(today.getFullYear(), today.getMonth(), 1)) return;
    currentMonth = previous;
    loadCalendar();
  });
  document.querySelector('#next-month').addEventListener('click', () => {
    const lastAllowed = new Date(today.getFullYear(), today.getMonth() + 6, 1);
    const next = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1);
    if (next > lastAllowed) return;
    currentMonth = next;
    loadCalendar();
  });

  toDate.addEventListener('click', () => {
    if (!selectedService) return;
    goToStep(2);
    loadCalendar();
  });

  toTime.addEventListener('click', async () => {
    if (!dateInput.value) return;
    goToStep(3);
    const [year, month, day] = dateInput.value.split('-').map(Number);
    document.querySelector('#time-summary').textContent = `${selectedService.name} · ${dateFormatter.format(new Date(year, month - 1, day))}`;
    timeGrid.innerHTML = '<p class="muted">Carregando horários disponíveis...</p>';
    toDetails.disabled = true;
    selectedTime = '';
    timeInput.value = '';
    try {
      const response = await fetch(`${window.BARBERFLOW.slotsUrl}?date=${encodeURIComponent(dateInput.value)}&service_id=${encodeURIComponent(selectedService.id)}`);
      const data = await response.json();
      timeGrid.innerHTML = '';
      if (!data.slots || !data.slots.length) {
        timeGrid.innerHTML = '<p class="no-times">Não há mais horários disponíveis nesta data. Volte e escolha outro dia.</p>';
        return;
      }
      data.slots.forEach(slot => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'time-choice';
        button.textContent = slot;
        button.addEventListener('click', () => {
          timeGrid.querySelectorAll('.time-choice').forEach(item => item.classList.remove('selected'));
          button.classList.add('selected');
          selectedTime = slot;
          timeInput.value = slot;
          toDetails.disabled = false;
        });
        timeGrid.appendChild(button);
      });
    } catch {
      timeGrid.innerHTML = '<p class="no-times">Erro ao consultar horários. Tente novamente.</p>';
    }
  });

  toDetails.addEventListener('click', () => {
    if (!selectedTime) return;
    const [year, month, day] = dateInput.value.split('-').map(Number);
    const formattedDate = dateFormatter.format(new Date(year, month - 1, day));
    document.querySelector('#final-summary').innerHTML = `<div><small>SERVIÇO</small><strong>${escapeHtml(selectedService.name)}</strong></div><div><small>DATA E HORÁRIO</small><strong>${formattedDate} · ${selectedTime}</strong></div><div><small>DURAÇÃO</small><strong>${selectedService.duration} minutos</strong></div><div><small>VALOR</small><strong>R$ ${selectedService.price.toFixed(2).replace('.', ',')}</strong></div>`;
    goToStep(4);
  });

  document.querySelectorAll('[data-back]').forEach(button => button.addEventListener('click', () => {
    const step = Number(button.dataset.back);
    goToStep(step);
  }));

  form.addEventListener('submit', event => {
    if (!serviceIdInput.value || !dateInput.value || !timeInput.value) {
      event.preventDefault();
      alert('Confira o serviço, a data e o horário escolhidos.');
    }
  });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
})();
