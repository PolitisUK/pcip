from pathlib import Path


def test_rivermere_startup_runner_is_explicit_and_staging_only():
    entrypoint = Path("entrypoint.sh").read_text()
    deployment = Path(".github/workflows/deploy-azure.yml").read_text()
    importer = Path("scripts/seed_rivermere_demo.py").read_text()
    dockerignore = Path(".dockerignore").read_text()
    dockerfile = Path("Dockerfile").read_text()

    assert "${RUN_RIVERMERE_DEMO_SEED:-false}" in entrypoint
    assert '[ "${ENVIRONMENT:-}" != "staging" ]' in entrypoint
    assert "--create-staging-demo-organisation" in entrypoint
    assert "--verify" in entrypoint
    assert 'requested_environment != "staging"' in importer
    assert "is_local" in importer
    assert "args.create_staging_demo_organisation" in importer
    assert "type: boolean" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=true" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=false" in deployment
    assert deployment.count("always() && inputs.seed_rivermere_demo") == 3
    assert "!scripts/seed_rivermere_demo.py" in dockerignore
    assert "RUN test -f /app/scripts/seed_rivermere_demo.py" in dockerfile


def test_production_rivermere_runner_preserves_release_and_cleanup_gates():
    entrypoint = Path("entrypoint.sh").read_text()
    promotion = Path(".github/workflows/promote-release.yml").read_text()
    importer = Path("scripts/seed_rivermere_demo.py").read_text()

    assert "${RUN_RIVERMERE_PRODUCTION_DEMO_SEED:-false}" in entrypoint
    assert '[ "${ENVIRONMENT:-}" != "production" ]' in entrypoint
    assert "--confirm-production-demo" in entrypoint
    assert "--create-production-demo-organisation" in entrypoint
    assert "--grant-configured-production-owner-access" in entrypoint
    assert "--verify-configured-production-owner-access" in entrypoint
    assert "--grant-sole-platform-admin-access" not in entrypoint
    assert "--verify" in entrypoint
    assert 'requested_environment != "production"' in importer
    assert "args.create_production_demo_organisation" in importer
    assert "grant_sole_platform_admin_access=args.grant_sole_platform_admin_access" in importer
    assert "The production Rivermere import requires promote_to_production=true." in promotion
    assert "RUN_RIVERMERE_PRODUCTION_DEMO_SEED=true" in promotion
    assert promotion.count("RUN_RIVERMERE_PRODUCTION_DEMO_SEED=false") == 2
    assert promotion.count("always() && inputs.seed_rivermere_demo") == 2
    assert "secrets.RIVERMERE_DEMO_OWNER_EMAIL" in promotion
    assert "secrets.RIVERMERE_DEMO_OWNER_USER_ID" in promotion
    assert "RIVERMERE_DEMO_OWNER_EMAIL=\"$RIVERMERE_DEMO_OWNER_EMAIL\"" in promotion
    assert "--setting-names RIVERMERE_DEMO_OWNER_USER_ID RIVERMERE_DEMO_OWNER_EMAIL" in promotion
    assert "RIVERMERE_DEMO_VERIFICATION_NOT_BEFORE" in promotion
    assert "Wait for durable production Rivermere verification" in promotion
    assert "/api/v1/rivermere/verification" in promotion
    assert "for attempt in {1..90}" in promotion
    assert "for final_check in {1..3}" in promotion
    assert "echo \"$RIVERMERE_DEMO_OWNER_EMAIL\"" not in promotion
    assert "echo \"$RIVERMERE_DEMO_OWNER_USER_ID\"" not in promotion
    assert "RIVERMERE_DEMO_OWNER_EMAIL" not in entrypoint
    assert "RIVERMERE_DEMO_OWNER_EMAIL" not in importer.split("print(json.dumps", 1)[1]
    assert "Restart production for the Rivermere import" not in promotion
    assert "Restart production after clearing the Rivermere runner" not in promotion
    assert "backup_recovery_point" in promotion
    assert "rollback_digest" in promotion
