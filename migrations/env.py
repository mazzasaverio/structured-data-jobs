from logging.config import fileConfig
import os
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import engine_from_config

from alembic import context

# Import your models here - this is the most important part
from src.db.models.models import Base

# Load environment variables
load_dotenv()

# this is the Alembic Config object
config = context.config

# Get the database URL from environment
database_url = os.environ.get("DATABASE_URL")

# Important: Convert from PostgreSQL URL to SQLAlchemy URL format
# We need to use the standard psycopg2 driver for Alembic
if database_url and "postgresql://" in database_url:
    # Remove any async specifics and ensure standard psycopg2 format
    sqlalchemy_url = database_url
    # Make sure sslmode is included if needed (for Neon)
    if "neon.tech" in database_url and "sslmode=require" not in database_url:
        sqlalchemy_url += "&sslmode=require" if "?" in sqlalchemy_url else "?sslmode=require"
    config.set_main_option("sqlalchemy.url", sqlalchemy_url)

# Interpret the config file for Python logging
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a standard synchronous engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()  # Direct call, no asyncio.run()
