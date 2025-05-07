import os
import asyncio
from urllib.parse import urlparse, parse_qs
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any
import traceback
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from src.db.models.models import Base
from src.utils.logging import log_span, log_db_query
import logfire

load_dotenv()


def create_async_db_engine():
    """Create an optimized async SQLAlchemy engine for Neon Postgres."""
    database_url = os.getenv("DATABASE_URL")

    parsed_url = urlparse(database_url)

    # For Neon Postgres, create the proper connection string with ssl=require
    async_url = f"postgresql+asyncpg://{parsed_url.username}:{parsed_url.password}@{parsed_url.hostname}{parsed_url.path}?ssl=require"

    # Mask password in logs
    safe_url = async_url.replace(f":{parsed_url.password}@", ":***@")
    logfire.info("Connecting to database", url=safe_url)

    engine = create_async_engine(
        async_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        pool_recycle=300,
        pool_timeout=30,
        connect_args={
            "command_timeout": 10,
            "server_settings": {
                "application_name": "structured-data-jobs",
                "statement_timeout": "10000",
                "idle_in_transaction_session_timeout": "30000",
            },
        },
    )

    try:
        from src.utils.logging import setup_sqlalchemy_instrumentation

        setup_sqlalchemy_instrumentation(engine)
    except Exception:
        pass

    return engine


def get_async_session_factory(engine):
    """Create an async session factory."""
    return async_sessionmaker(
        engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Session context manager with automatic commit/rollback."""
    engine = create_async_db_engine()
    session_factory = get_async_session_factory(engine)
    session = session_factory()

    with log_span("database_session"):
        try:
            yield session
            await session.commit()
            logfire.info("Database session committed")
        except Exception as e:
            await session.rollback()
            error_msg = str(e)
            error_type = type(e).__name__

            # Log more details for potential duplicate entries
            if (
                "duplicate key" in error_msg.lower()
                or "unique constraint" in error_msg.lower()
            ):
                logfire.error(
                    "Database duplicate entry error",
                    error=error_msg,
                    error_type=error_type,
                    constraint=(
                        error_msg.split("constraint")[1]
                        if "constraint" in error_msg
                        else "unknown"
                    ),
                    trace=traceback.format_exc(),
                )
            else:
                logfire.error(
                    "Database session error",
                    error=error_msg,
                    error_type=error_type,
                    trace=traceback.format_exc(),
                )
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database schema."""
    engine = create_async_db_engine()

    with log_span("initialize_database"):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logfire.info("Database tables created")
        except Exception as e:
            logfire.error("Database initialization failed", error=str(e))
            raise
        finally:
            await engine.dispose()


async def test_connection() -> bool:
    """Test database connectivity."""
    engine = create_async_db_engine()

    with log_span("test_database_connection"):
        try:
            async with engine.connect() as conn:
                query = "SELECT version(), current_timestamp"
                log_db_query(query)

                result = await conn.execute(text(query))
                row = result.fetchone()

                logfire.info(
                    "Database connection successful",
                    postgres_version=str(row[0]),
                    server_time=str(row[1]),
                )
                return True
        except Exception as e:
            logfire.error(
                "Database connection failed",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )
            # Print detailed error for debugging
            print(f"Database connection error: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            print(traceback.format_exc())
            return False
        finally:
            await engine.dispose()


def setup_sqlalchemy_instrumentation(engine):
    try:
        logfire.instrument_sqlalchemy(engine=engine)
        logfire.info("SQLAlchemy instrumentation configured successfully")
    except (ImportError, AttributeError) as e:
        logfire.warning(f"SQLAlchemy instrumentation failed: {str(e)}")


def verify_database_url():
    """Verify database URL is properly formed."""
    database_url = os.getenv("DATABASE_URL")

    # Check if DATABASE_URL is set
    if not database_url:
        logfire.error("DATABASE_URL environment variable is not set")
        return False

    # Parse URL to verify components
    parsed_url = urlparse(database_url)

    if not parsed_url.hostname:
        logfire.error("DATABASE_URL is missing hostname")
        return False

    if not parsed_url.username:
        logfire.error("DATABASE_URL is missing username")
        return False

    if not parsed_url.password:
        logfire.error("DATABASE_URL is missing password")
        return False

    # Check for Neon.tech specific requirements
    is_neon = "neon.tech" in parsed_url.hostname
    if (
        is_neon
        and "sslmode=require" not in database_url
        and "ssl=true" not in database_url
    ):
        logfire.warning(
            "Neon PostgreSQL detected but sslmode=require is missing - adding automatically"
        )

    # Log masked URL for verification
    safe_url = database_url.replace(parsed_url.password, "***")
    logfire.info("Database URL verified", url=safe_url)

    return True
