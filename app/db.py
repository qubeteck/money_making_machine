from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import ensure_data_dir, get_settings, normalize_database_url

ensure_data_dir()
settings = get_settings()
database_url = normalize_database_url(settings.database_url)

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

if database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)

    # Lightweight migration: add missing columns (SQLite)
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "last_login_at" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL"))
                conn.commit()
        if "telegram_chat_id" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50) NULL"))
                conn.commit()
        if "telegram_verified" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_verified BOOLEAN DEFAULT 0"))
                conn.commit()
        if "telegram_registered_at" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN telegram_registered_at TIMESTAMP NULL"))
                conn.commit()

    from app.models import BotSetting

    with session_scope() as db:
        row = db.get(BotSetting, 1)
        if row is None:
            db.add(BotSetting(id=1))
