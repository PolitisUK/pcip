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
    assert "--grant-sole-platform-admin-access" in entrypoint
    assert "--verify" in entrypoint
    assert 'requested_environment != "production"' in importer
    assert "args.create_production_demo_organisation" in importer
    assert "grant_sole_platform_admin_access=args.grant_sole_platform_admin_access" in importer
    assert "The production Rivermere import requires promote_to_production=true." in promotion
    assert "RUN_RIVERMERE_PRODUCTION_DEMO_SEED=true" in promotion
    assert promotion.count("RUN_RIVERMERE_PRODUCTION_DEMO_SEED=false") == 2
    assert promotion.count("steps.rivermere_seed_control.outcome == 'success'") == 3
    assert "backup_recovery_point" in promotion
    assert "rollback_digest" in promotion
