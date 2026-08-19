from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import settings, validate_runtime_settings
from app.db import Base, SessionLocal, engine
from app.demo_data.rivermere import (
    CHAPEL_PROJECT_CODE,
    EVERYDAY_PROJECT_CODE,
    assert_safe_demo_target,
    remove_rivermere_project,
    seed_rivermere,
)
from app.storage import build_storage


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or remove the fictional Rivermere local-development dataset.")
    parser.add_argument("--confirm-local-development", action="store_true", help="Required acknowledgement that the configured target is disposable local development data.")
    parser.add_argument("--remove", choices=["everyday-life", "chapel-lane"], help="Remove only the selected Rivermere demonstration project.")
    args = parser.parse_args()
    if not args.confirm_local_development:
        parser.error("--confirm-local-development is required; no records were changed")

    validate_runtime_settings(settings)
    repo_root = Path(__file__).resolve().parents[1]
    database_path, evidence_path = assert_safe_demo_target(
        database_url=settings.database_url, environment=settings.environment,
        storage_backend=settings.storage_backend, storage_path=settings.local_storage_path,
        repo_root=repo_root,
    )
    Base.metadata.create_all(engine)
    storage = build_storage(); storage.ensure_ready()
    with SessionLocal() as db:
        if args.remove:
            code = EVERYDAY_PROJECT_CODE if args.remove == "everyday-life" else CHAPEL_PROJECT_CODE
            result = remove_rivermere_project(db, storage, code)
            action = f"removed:{code}"
        else:
            result = seed_rivermere(db, storage).as_dict()
            action = "seeded"
    print(json.dumps({
        "action": action, "environment": settings.environment,
        "database": str(database_path), "storage": str(evidence_path), "result": result,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
