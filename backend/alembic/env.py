from alembic import context
from app.database import Base, get_engine
from app import models  # noqa: F401

if context.is_offline_mode():
    raise RuntimeError("Use an online database connection for migrations")
with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
