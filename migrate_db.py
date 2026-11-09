from pathlib import Path
from sqlalchemy import create_engine, inspect, select, text
from app import app, db

# Banco SQLite original
sqlite_path = Path(
    r"C:\Users\tadeu\Downloads\barberflow\instance\barberflow.db"
)

if not sqlite_path.exists():
    raise FileNotFoundError(f"Banco SQLite não encontrado: {sqlite_path}")

# Conexões
source_url = f"sqlite:///{sqlite_path.as_posix()}"
source_engine = create_engine(source_url)

target_url = app.config["SQLALCHEMY_DATABASE_URI"]
target_engine = create_engine(target_url)

if target_engine.dialect.name != "postgresql":
    raise RuntimeError("DATABASE_URL não está apontando para PostgreSQL.")

with app.app_context():
    # Cria as tabelas no PostgreSQL, caso ainda não existam
    db.create_all()

    source_inspector = inspect(source_engine)

    source_tables = set(source_inspector.get_table_names())

    # Evita duplicar ou sobrescrever dados existentes
    with target_engine.connect() as conn:
        for table in db.metadata.sorted_tables:
            if table.name in inspect(target_engine).get_table_names():
                count = conn.execute(
                    select(db.func.count()).select_from(table)
                ).scalar_one()

                if count:
                    raise RuntimeError(
                        f"A tabela {table.name} já possui dados. "
                        "Migração interrompida."
                    )

    # Copia os registros preservando os IDs
    with source_engine.connect() as source_conn:
        with target_engine.begin() as target_conn:

            for table in db.metadata.sorted_tables:

                if table.name not in source_tables:
                    print(f"Tabela ausente no SQLite: {table.name}")
                    continue

                source_table = source_conn.execute(
                    text(f'SELECT * FROM "{table.name}"')
                ).mappings().all()

                target_columns = {
                    column.name for column in table.columns
                }

                records = []

                for row in source_table:
                    records.append({
                        key: value
                        for key, value in row.items()
                        if key in target_columns
                    })

                if records:
                    target_conn.execute(table.insert(), records)

                print(
                    f"{table.name}: {len(records)} registros copiados."
                )

            # Atualiza sequências dos IDs no PostgreSQL
            for table in db.metadata.sorted_tables:
                if "id" in table.columns:
                    table_name = table.name

                    target_conn.execute(text(f"""
                        SELECT setval(
                            pg_get_serial_sequence(
                                '{table_name}', 'id'
                            ),
                            COALESCE(
                                (SELECT MAX(id) FROM "{table_name}"),
                                1
                            ),
                            EXISTS(
                                SELECT 1 FROM "{table_name}"
                            )
                        )
                    """))

print("\nMigração concluída!")
source_engine.dispose()
target_engine.dispose()