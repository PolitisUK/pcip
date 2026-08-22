from pathlib import Path


def test_rivermere_startup_runner_is_explicit_and_staging_only():
    entrypoint = Path("entrypoint.sh").read_text()
    deployment = Path(".github/workflows/deploy-azure.yml").read_text()
    importer = Path("scripts/seed_rivermere_demo.py").read_text()

    assert "${RUN_RIVERMERE_DEMO_SEED:-false}" in entrypoint
    assert '[ "${ENVIRONMENT:-}" != "staging" ]' in entrypoint
    assert "--create-staging-demo-organisation" in entrypoint
    assert "--verify" in entrypoint
    assert 'requested_environment != "staging"' in importer
    assert "is_local or args.create_staging_demo_organisation" in importer
    assert "type: boolean" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=true" in deployment
    assert "RUN_RIVERMERE_DEMO_SEED=false" in deployment
    assert "always() && inputs.seed_rivermere_demo" in deployment
