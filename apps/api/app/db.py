from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def create_engine_for_url(url: str, *, echo: bool = False) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    created_engine = create_engine(
        url, echo=echo, future=True, pool_pre_ping=True, connect_args=connect_args
    )
    if url.startswith("sqlite"):
        @event.listens_for(created_engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return created_engine


engine = create_engine_for_url(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
