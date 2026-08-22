from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

from app.config import settings, validate_runtime_settings
from app.db import Base, SessionLocal, engine
from app.demo_data.rivermere import (
    CHAPEL_PROJECT_CODE,
    EVERYDAY_PROJECT_CODE,
    RIVERMERE_SLUG,
    assert_safe_demo_target,
    remove_rivermere_project,
    record_rivermere_verification,
    resolve_configured_production_owner,
    replace_superseded_rivermere_demo,
    seed_rivermere,
    update_rivermere_import_status,
    verify_rivermere,
)
from app.storage import build_storage

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s", force=True)
logger = logging.getLogger(__name__)
current_phase = "not_started"


def milestone(phase: str, **extra) -> None:
    global current_phase
    current_phase = phase
    logger.info(json.dumps({"event": "rivermere_importer", "phase": phase, **extra}, sort_keys=True))


def main() -> int:
    milestone("process_started")
    parser = argparse.ArgumentParser(description="Seed or remove the fictional Rivermere local-development dataset.")
    parser.add_argument("--environment", required=True, help="Must exactly match the configured application environment.")
    parser.add_argument("--organisation-slug", required=True, help="The designated fictional/demo organisation slug.")
    parser.add_argument("--confirm-local-development", action="store_true", help="Required acknowledgement for disposable local development data.")
    parser.add_argument("--confirm-nonlocal-demo", action="store_true", help="Required acknowledgement before staging or another nonlocal target is touched.")
    parser.add_argument("--confirm-production-demo", action="store_true", help="Separate confirmation required for the production fictional/demo organisation.")
    parser.add_argument(
        "--create-staging-demo-organisation",
        action="store_true",
        help="Create the exact fictional Rivermere organisation and non-login demo researcher when they are absent in staging.",
    )
    parser.add_argument(
        "--create-production-demo-organisation",
        action="store_true",
        help="Create the exact fictional Rivermere organisation and non-login demo researcher when they are absent in production.",
    )
    parser.add_argument(
        "--grant-sole-platform-admin-access",
        action="store_true",
        help="Grant the sole active platform administrator owner access to the fictional production workspace.",
    )
    parser.add_argument(
        "--grant-configured-production-owner-access",
        action="store_true",
        help="Grant the protected configured production platform administrator owner access to the fictional workspace.",
    )
    parser.add_argument(
        "--verify-configured-production-owner-access",
        action="store_true",
        help="Verify the protected configured production administrator has owner access without revealing the selector.",
    )
    parser.add_argument("--remove", choices=["everyday-life", "chapel-lane"], help="Remove only the selected Rivermere demonstration project.")
    parser.add_argument("--verify", action="store_true", help="Read-only verification against the bundled v1.1 content pack.")
    args = parser.parse_args()
    configured_environment = settings.environment.strip().lower()
    requested_environment = args.environment.strip().lower()
    if requested_environment != configured_environment:
        parser.error("--environment must exactly match the configured application environment; no records were changed")
    if args.organisation_slug != RIVERMERE_SLUG:
        parser.error("--organisation-slug must be the designated fictional Rivermere organisation; no records were changed")
    is_local = requested_environment in {"development", "dev", "test", "testing"}
    if args.verify and args.remove:
        parser.error("--verify and --remove cannot be used together")
    if args.create_staging_demo_organisation and requested_environment != "staging":
        parser.error("--create-staging-demo-organisation is restricted to staging; no records were changed")
    if args.create_staging_demo_organisation and (args.verify or args.remove):
        parser.error("--create-staging-demo-organisation is only valid when seeding; no records were changed")
    if args.create_production_demo_organisation and requested_environment != "production":
        parser.error("--create-production-demo-organisation is restricted to production; no records were changed")
    if args.create_production_demo_organisation and (args.verify or args.remove):
        parser.error("--create-production-demo-organisation is only valid when seeding; no records were changed")
    if args.grant_sole_platform_admin_access and not args.create_production_demo_organisation:
        parser.error("--grant-sole-platform-admin-access requires the production demo-organisation flag; no records were changed")
    if args.grant_configured_production_owner_access and not args.create_production_demo_organisation:
        parser.error("--grant-configured-production-owner-access requires the production demo-organisation flag; no records were changed")
    if args.grant_sole_platform_admin_access and args.grant_configured_production_owner_access:
        parser.error("Only one production owner selection mechanism is allowed; no records were changed")
    if args.verify_configured_production_owner_access and not args.verify:
        parser.error("--verify-configured-production-owner-access requires --verify; no records were changed")
    if args.verify_configured_production_owner_access and requested_environment != "production":
        parser.error("--verify-configured-production-owner-access is restricted to production; no records were changed")
    if not args.verify and is_local and not args.confirm_local_development:
        parser.error("--confirm-local-development is required; no records were changed")
    if not args.verify and not is_local and not args.confirm_nonlocal_demo:
        parser.error("--confirm-nonlocal-demo is required outside local development; no records were changed")
    if not args.verify and requested_environment == "production" and not args.confirm_production_demo:
        parser.error("--confirm-production-demo is required for production; no records were changed")

    validate_runtime_settings(settings)
    milestone("environment_safeguard_passed")
    if args.grant_configured_production_owner_access:
        update_rivermere_import_status("running", "environment_safeguard_passed")
    repo_root = Path(__file__).resolve().parents[1]
    database_path, evidence_path = assert_safe_demo_target(
        database_url=settings.database_url, environment=settings.environment,
        storage_backend=settings.storage_backend, storage_path=settings.local_storage_path,
        repo_root=repo_root, allow_nonlocal=not is_local,
    )
    if args.verify:
        with SessionLocal() as db:
            expected_owner = (
                _configured_production_owner(db)
                if args.verify_configured_production_owner_access
                else None
            )
            result = verify_rivermere(
                db,
                organisation_slug=args.organisation_slug,
                expected_owner=expected_owner,
            )
        print(json.dumps({"action": "verified", "environment": settings.environment, "database": str(database_path) if database_path else "configured nonlocal database", "result": result}, indent=2))
        return 0 if result["valid"] else 1
    Base.metadata.create_all(engine)
    storage = build_storage(); storage.ensure_ready()
    with SessionLocal() as db:
        if args.remove:
            code = EVERYDAY_PROJECT_CODE if args.remove == "everyday-life" else CHAPEL_PROJECT_CODE
            result = remove_rivermere_project(db, storage, code, organisation_slug=args.organisation_slug)
            action = f"removed:{code}"
        else:
            replacement = replace_superseded_rivermere_demo(db, storage) if is_local else None
            result = seed_rivermere(
                db,
                storage,
                organisation_slug=args.organisation_slug,
                create_organisation=(
                    is_local
                    or args.create_staging_demo_organisation
                    or args.create_production_demo_organisation
                ),
                grant_sole_platform_admin_access=args.grant_sole_platform_admin_access,
                grant_configured_production_owner_access=args.grant_configured_production_owner_access,
                demo_owner_user_id=(settings.rivermere_demo_owner_user_id if args.grant_configured_production_owner_access else None),
                demo_owner_email=(settings.rivermere_demo_owner_email if args.grant_configured_production_owner_access else None),
            ).as_dict()
            if args.grant_configured_production_owner_access:
                update_rivermere_import_status("committed", "database_commit_completed")
                milestone("verification_started")
                owner = _configured_production_owner(db)
                verification = verify_rivermere(
                    db,
                    organisation_slug=args.organisation_slug,
                    expected_owner=owner,
                )
                if not verification["valid"]:
                    raise RuntimeError("Rivermere verification failed; no production completion record was written.")
                milestone("verification_completed")
                record_rivermere_verification(db, organisation_slug=args.organisation_slug)
                update_rivermere_import_status("verified", "durable_verification_record_written")
                milestone("durable_verification_record_written")
                result["verification_completed"] = True
            if replacement:
                result["superseded_v1_removed"] = replacement
            action = "seeded"
    print(json.dumps({
        "action": action, "environment": settings.environment,
        "database": str(database_path), "storage": str(evidence_path), "result": result,
    }, indent=2))
    return 0


def _configured_production_owner(db):
    """Use the seed gate for verification too, without exposing its selector."""
    return resolve_configured_production_owner(
        db,
        owner_user_id=settings.rivermere_demo_owner_user_id,
        owner_email=settings.rivermere_demo_owner_email,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        update_rivermere_import_status("failed", current_phase, error_category=exc.__class__.__name__)
        logger.error(json.dumps({
            "event": "rivermere_importer_failed",
            "phase": current_phase,
            "error_category": exc.__class__.__name__,
            "seed_transaction_committed": current_phase in {"database_commit_completed", "verification_started", "verification_completed", "durable_verification_record_written"},
            "rollback_completed": current_phase not in {"database_commit_completed", "verification_started", "verification_completed", "durable_verification_record_written"},
            "traceback": traceback.format_exc(limit=8).replace("\n", " | "),
        }, sort_keys=True))
        raise
