# syntax=docker/dockerfile:1.9
FROM python:3.12-slim AS build

# Installa le dipendenze di build
RUN apt-get update -qy && \
    apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    build-essential \
    libpq-dev \
    gcc

# Installa uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Configura uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12 \
    UV_PROJECT_ENVIRONMENT=/app \
    UV_NO_CACHE=1\
    PLAYWRIGHT_BROWSERS_PATH=/playwright-browsers

# Prima installa le dipendenze senza il progetto
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project

# Copia il codice sorgente e installalo
COPY . .
RUN uv sync \
    --locked \
    --no-dev \
    --no-cache

# Runtime stage
FROM python:3.12-slim

# Imposta l'ambiente
ENV PATH=/app/bin:$PATH \
    PYTHONPATH=/app:/app/src

RUN uv tool install playwright
RUN playwright install --with-deps chromium
RUN chmod -Rf 777 $PLAYWRIGHT_BROWSERS_PATH
# Installa le dipendenze runtime
RUN apt-get update -qy && \
    apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    libpq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copia l'ambiente creato nella build stage
COPY --from=build /app /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copia il codice sorgente nella directory appropriata
COPY ./src /app/src

# Imposta la directory di lavoro
WORKDIR /app

# Comando di default
CMD ["python", "-m", "src.main"]
