FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY src/education_site/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/education_site/ .

USER appuser

EXPOSE 8000

CMD ["gunicorn", "education_site.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
