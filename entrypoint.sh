#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  if ! alembic upgrade head; then
    echo "WARNING: database migration failed; continuing so the web service can expose health diagnostics." >&2
  fi
fi

set +e
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
status=$?
set -e

if [ "$status" -eq 3 ]; then
  echo "WARNING: application lifespan startup failed; restarting without lifespan so the service remains reachable." >&2
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --lifespan off
fi

exit "$status"
