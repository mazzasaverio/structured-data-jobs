# Dockerfile
# Stage 1: Get uv
FROM ghcr.io/astral-sh/uv:0.1.25 as uv_builder
# Stage 2: Main image
FROM python:3.11-slim-bookworm

LABEL maintainer="Your Name <your.email@example.com>"
LABEL description="Custom Airflow image with uv package manager for the data pipeline project."

ENV PYTHONUNBUFFERED=1
ENV AIRFLOW_HOME=/opt/airflow
ENV PATH="${AIRFLOW_HOME}/.local/bin:${PATH}"

# System dependencies:
# - curl, gnupg, libssl-dev, libffi-dev: general utilities and for some python packages
# - build-essential, libpq-dev: for compiling some Python packages, specifically psycopg2 (Postgres driver)
# - git: if you need to install packages from git
# - tini: a lightweight init system for containers, helps manage zombie processes
RUN apt-get update -yqq \
    && apt-get upgrade -yqq \
    && apt-get install -yqq --no-install-recommends \
        curl \
        gnupg \
        libssl-dev \
        libffi-dev \
        build-essential \
        libpq-dev \
        git \
        tini \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from the builder stage and make it executable
COPY --from=uv_builder /uv /usr/local/bin/uv
RUN chmod +x /usr/local/bin/uv

# Create a non-root user for Airflow
# AIRFLOW_UID and AIRFLOW_GID will be passed as build arguments or set by docker-compose environment
ARG AIRFLOW_UID=50000
ARG AIRFLOW_GID=0
RUN groupadd --gid ${AIRFLOW_GID} airflow |
| groupmod -n airflow $(getent group ${AIRFLOW_GID} | cut -d: -f1) \
    && useradd --uid ${AIRFLOW_UID} --gid airflow --create-home --shell /bin/bash airflow

# Create directories and set permissions
RUN mkdir -p ${AIRFLOW_HOME}/dags ${AIRFLOW_HOME}/logs ${AIRFLOW_HOME}/plugins ${AIRFLOW_HOME}/config \
    && chown -R airflow:airflow ${AIRFLOW_HOME}

# Copy requirements.txt and install dependencies using uv
COPY requirements.txt /requirements.txt
RUN uv pip install --system --no-cache -r /requirements.txt \
    && rm /requirements.txt

# Copy entrypoint script (if you create one, e.g., for custom startup logic)
# COPY entrypoint.sh /entrypoint.sh
# RUN chmod +x /entrypoint.sh

USER airflow
WORKDIR ${AIRFLOW_HOME}

# Expose ports (actual mapping happens in docker-compose.yaml)
EXPOSE 8080
EXPOSE 5555
EXPOSE 8793

# Healthcheck for Airflow services
HEALTHCHECK --interval=30s --timeout=30s --retries=3 \
  CMD [ "airflow", "jobs", "check", "--local"]

# Default command (can be overridden by docker-compose)
# ENTRYPOINT ["/entrypoint.sh"] # If using an entrypoint script
# CMD ["bash"] # Or a default command like webserver, scheduler