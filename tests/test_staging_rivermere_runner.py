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
    assert "is_local or args.create_staging_demo_organisation" in importer
    assert "type: boolean" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=true" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=false" in deployment
    assert deployment.count("always() && inputs.seed_rivermere_demo") == 3
    assert "!scripts/seed_rivermere_demo.py" in dockerignore
    assert "RUN test -f /app/scripts/seed_rivermere_demo.py" in dockerfile
