from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    settings = get_settings()
    url: str | URL = settings.database_url.replace("postgresql+asyncpg:", "postgresql+psycopg:")
    if settings.database_secret_arn:
        import json

        from app.integrations.aws import aws_client

        secret = json.loads(
            aws_client("secretsmanager").get_secret_value(SecretId=settings.database_secret_arn)[
                "SecretString"
            ]
        )
        url = URL.create(
            "postgresql+psycopg",
            username=secret["username"],
            password=secret["password"],
            host=settings.database_host,
            database=settings.database_name,
            port=5432,
            query={
                "sslmode": settings.database_sslmode,
                **({"sslrootcert": settings.database_sslrootcert} if settings.database_sslrootcert else {}),
            },
        )
    kwargs = (
        {"connect_args": {"check_same_thread": False}}
        if str(url).startswith("sqlite")
        else {"connect_args": {"connect_timeout": 5}}
    )
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def session_factory():
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
