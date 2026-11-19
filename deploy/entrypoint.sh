#!/usr/bin/env bash
set -euo pipefail

cd /app

wait_for_db() {
  local retries="${DB_WAIT_RETRIES:-30}"
  local delay="${DB_WAIT_DELAY_SECONDS:-2}"
  local i=0
  echo "Waiting for database..."
  until python - <<'PY'
import os
import sys
from urllib.parse import unquote, urlparse

import psycopg

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit(0)
parsed = urlparse(url)
if parsed.scheme not in {"postgres", "postgresql"}:
    sys.exit(0)
conninfo = (
    f"dbname={parsed.path.lstrip('/')} "
    f"user={unquote(parsed.username or '')} "
    f"password={unquote(parsed.password or '')} "
    f"host={parsed.hostname or ''} "
    f"port={parsed.port or 5432} "
    f"connect_timeout=3"
)
try:
    with psycopg.connect(conninfo) as conn:
        conn.execute("SELECT 1")
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
PY
  do
    i=$((i + 1))
    if [[ "$i" -ge "$retries" ]]; then
      echo "Database is not available after ${retries} attempts" >&2
      exit 1
    fi
    sleep "$delay"
  done
  echo "Database is ready."
}

# Миграции и collectstatic — только у web (gunicorn), не у worker.
if [[ "${1:-}" == "gunicorn" ]]; then
  wait_for_db
  echo "Applying migrations..."
  python manage.py migrate --noinput
  if [[ "${COLLECT_STATIC_AT_START:-1}" == "1" ]]; then
    echo "Collecting static..."
    python manage.py collectstatic --noinput
  fi
fi

exec "$@"
