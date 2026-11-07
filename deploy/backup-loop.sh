#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${BACKUP_KEEP_COUNT:-14}"

mkdir -p /backups

while true; do
  TS="$(date -u +%Y%m%dT%H%MZ)"
  FILE="/backups/${PGDATABASE}-${TS}.sql.gz"
  echo "backup: ${FILE}"
  pg_dump -Fc "$PGDATABASE" | gzip > "${FILE}"
  ls -1t /backups/*.sql.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
  sleep "${INTERVAL}"
done
