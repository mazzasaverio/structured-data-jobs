import os
import asyncio
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import traceback
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

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

    return engine


def get_async_session_factory(engine):
    """Create an async session factory."""
    # Use regular sessionmaker with AsyncSession class for SQLAlchemy 1.x
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
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
        await engine.dispose()


async def test_connection() -> bool:
    """Test database connectivity."""
    engine = create_async_db_engine()

    try:
        async with engine.connect() as conn:
            query = "SELECT version(), current_timestamp"
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
        return False
    finally:
        await engine.dispose()
