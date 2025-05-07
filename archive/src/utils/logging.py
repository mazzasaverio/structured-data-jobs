import logfire
import os
from contextlib import contextmanager
from typing import Optional, Any, Dict
import logging


def setup_logging(
    service_name: str = "structured-data-jobs", environment: Optional[str] = None
):
    """Set up the Logfire logging system."""

    # Add a check to prevent multiple initializations
    if getattr(setup_logging, "initialized", False):
        return

    logfire.configure(
        service_name=service_name,
        console={
            "colors": "auto",
        },
    )

    # Mark as initialized
    setup_logging.initialized = True

    # try:
    #     import asyncpg
    #     logfire.instrument_asyncpg()
    # except (ImportError, AttributeError):
    #     pass

    # try:
    #     import sqlalchemy
    #     logfire.instrument_sqlalchemy()
    # except (ImportError, AttributeError):
    #     pass


@contextmanager
def log_span(name: str, extra_attrs: Optional[Dict[str, Any]] = None):
    """Context manager for creating spans."""
    with logfire.span(name) as span:
        try:
            yield span
        except Exception as e:
            # Log the exception
            logfire.error(f"{name} failed", exception=str(e))
            raise


# Funzione per aggiungere un separatore visivo nei log
def log_separator(title=None):
    """Print a visual separator in the logs."""
    if title:
        separator = f"\n{'=' * 30} {title} {'=' * 30}\n"
    else:
        separator = f"\n{'=' * 70}\n"
    print(separator)


# Funzione per abilitare il logging in modalità debug
def enable_debug_logging():
    """Enable detailed debug logging."""
    setup_logging()
    return logfire


# Funzione mancante per il logging delle query del database
def log_db_query(query: str, parameters: Optional[Dict[str, Any]] = None) -> None:
    """Log a database query with sensitive data masking."""
    try:
        safe_params = None
        if parameters:
            safe_params = {}
            for key, value in parameters.items():
                if any(
                    sensitive in key.lower()
                    for sensitive in ["password", "secret", "token", "key"]
                ):
                    safe_params[key] = "********"
                else:
                    safe_params[key] = value

        logfire.info("DB Query", query=query, parameters=safe_params)
    except Exception:
        pass
