import logfire
import os
from typing import Optional


def setup_logging(service_name: Optional[str] = None, level: str = "INFO"):
    """
    Configure logging for the application using logfire

    Args:
        service_name: Optional name of the service for identification
        level: The logging level (DEBUG, INFO, WARNING, ERROR)
    """
    if not service_name:
        service_name = os.environ.get("SERVICE_NAME", "structured-data-jobs")

    logfire.configure(
        service_name=service_name,
        level=level,
    )

    logfire.info(f"Logging initialized for {service_name}")
