#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  # A release must never report healthy after an incomplete schema upgrade.
  # The release workflow runs this only after its backup and approval gates.
  alembic upgrade head
fi

if [ "${RUN_RIVERMERE_DEMO_SEED:-false}" = "true" ]; then
  if [ "${ENVIRONMENT:-}" != "staging" ]; then
    echo "RUN_RIVERMERE_DEMO_SEED is restricted to the staging environment." >&2
    exit 1
  fi
  PYTHONPATH=. python scripts/seed_rivermere_demo.py \
    --environment staging \
    --organisation-slug rivermere-town-council \
    --confirm-nonlocal-demo \
    --create-staging-demo-organisation
  PYTHONPATH=. python scripts/seed_rivermere_demo.py \
    --environment staging \
    --organisation-slug rivermere-town-council \
    --verify
fi

if [ "${RUN_RIVERMERE_PRODUCTION_DEMO_SEED:-false}" = "true" ]; then
  if [ "${ENVIRONMENT:-}" != "production" ]; then
    echo "RUN_RIVERMERE_PRODUCTION_DEMO_SEED is restricted to the production environment." >&2
    exit 1
  fi
  PYTHONPATH=. python scripts/seed_rivermere_demo.py \
    --environment production \
    --organisation-slug rivermere-town-council \
    --confirm-nonlocal-demo \
    --confirm-production-demo \
    --create-production-demo-organisation \
    --grant-sole-platform-admin-access
  PYTHONPATH=. python scripts/seed_rivermere_demo.py \
    --environment production \
    --organisation-slug rivermere-town-council \
    --verify
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
