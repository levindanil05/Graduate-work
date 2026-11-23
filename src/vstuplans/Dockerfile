# --- Этап 1: сборка зависимостей ---
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv

WORKDIR /app

COPY src/vstuplans/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Этап 2: runtime ---
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src/vstuplans/ .
# Парсер PLX лежит вне каталога Django-проекта (src/plx_parser.py).
COPY src/plx_parser.py /app/plx_parser.py

RUN mkdir -p /app/staticfiles /app/userfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "vstuplans.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
