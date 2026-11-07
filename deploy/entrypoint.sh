#!/usr/bin/env bash
set -euo pipefail

cd /app

python manage.py migrate --noinput

if [[ "${COLLECT_STATIC_AT_START:-1}" == "1" ]]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
