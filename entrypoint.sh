#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  # A release must never report healthy after an incomplete schema upgrade.
  # The release workflow runs this only after its backup and approval gates.
  alembic upgrade head
fi

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
