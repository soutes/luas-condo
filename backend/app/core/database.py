import os
import urllib.parse
from typing import Generator
from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def parse_database_url() -> str | URL:
    postgres_host = os.getenv("POSTGRES_HOST")
    if postgres_host:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=postgres_host,
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "luas_condo"),
        )

    raw_url = os.getenv("DATABASE_URL", "sqlite:///./condo.db")
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    if raw_url.startswith("postgresql://") or raw_url.startswith("postgresql+psycopg2://"):
        prefix, _, rest = raw_url.partition("://")
        if "@" in rest:
            userinfo, _, host_db = rest.rpartition("@")
            user, _, password = userinfo.partition(":")
            encoded_user = urllib.parse.quote_plus(urllib.parse.unquote_plus(user))
            encoded_pass = urllib.parse.quote_plus(urllib.parse.unquote_plus(password))
            return f"{prefix}://{encoded_user}:{encoded_pass}@{host_db}"

    return raw_url


DATABASE_URL = parse_database_url()

connect_args = {}
url_str = DATABASE_URL.render_as_string(hide_password=False) if isinstance(DATABASE_URL, URL) else DATABASE_URL
if url_str.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    new_columns = [
        ("boleto_aluguel_path", "VARCHAR(500)"),
        ("valor_desconto_aluguel", "NUMERIC(10, 2) DEFAULT 0.00"),
        ("valor_saldo_residual", "NUMERIC(10, 2) DEFAULT 0.00"),
        ("itens_abatidos_aluguel", "JSON"),
        ("ultima_verificacao", "TIMESTAMP WITH TIME ZONE"),
        ("detalhes_verificacao", "TEXT"),
    ]
    try:
        with engine.begin() as conn:
            for col_name, col_type in new_columns:
                if conn.dialect.name == "postgresql":
                    conn.exec_driver_sql(
                        f"ALTER TABLE ciclos_condominio ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                elif conn.dialect.name == "sqlite":
                    cols = [
                        row[1]
                        for row in conn.exec_driver_sql("PRAGMA table_info(ciclos_condominio)").fetchall()
                    ]
                    if col_name not in cols:
                        conn.exec_driver_sql(
                            f"ALTER TABLE ciclos_condominio ADD COLUMN {col_name} {col_type}"
                        )
    except Exception:
        pass
