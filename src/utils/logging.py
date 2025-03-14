import os
import sys
from typing import Any, Dict, Optional

import logfire

def setup_logging() -> None:
    """Configure Logfire for application logging with fault tolerance."""
    try:
        env = os.environ.get("ENVIRONMENT", "development")
        service_name = "lean-jobs-crawler"
        
        logfire.configure(
            service_name=service_name,
            environment=env,
        )
        
        log_level = "DEBUG" if env == "development" else "INFO"
        
        _try_setup_integrations()
        
        logfire.info(
            "Logging system initialized successfully", 
            service=service_name, 
            environment=env,
            log_level=log_level
        )
    except Exception as e:
        print(f"WARNING: Failed to initialize Logfire: {e}", file=sys.stderr)
        print("Continuing without structured logging...", file=sys.stderr)


def _try_setup_integrations():
    """Setup available integrations without failing if they're missing."""
    pass


def setup_sqlalchemy_instrumentation(engine) -> bool:
    """Configure SQLAlchemy instrumentation if available."""
    try:
        logfire.instrument_sqlalchemy(engine=engine)
        logfire.info("SQLAlchemy instrumentation configured")
        return True
    except Exception as e:
        print(f"SQLAlchemy instrumentation skipped: {str(e)}", file=sys.stderr)
        return False


def get_logger() -> Any:
    """Get a reference to the Logfire logger."""
    return logfire


def log_span(name: str, **attrs) -> Any:
    """Create a fault-tolerant logging span."""
    try:
        return logfire.span(name, **attrs)
    except Exception:
        class DummySpan:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return DummySpan()


def log_db_query(query: str, parameters: Optional[Dict[str, Any]] = None) -> None:
    """Log a database query with sensitive data masking."""
    try:
        safe_params = None
        if parameters:
            safe_params = {}
            for key, value in parameters.items():
                if any(sensitive in key.lower() for sensitive in ["password", "secret", "token", "key"]):
                    safe_params[key] = "********"
                else:
                    safe_params[key] = value
        
        logfire.info("DB Query", query=query, parameters=safe_params)
    except Exception:
        pass
