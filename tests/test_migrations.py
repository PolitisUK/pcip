import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_accepts_percent_encoded_database_url(tmp_path):
    database_path = tmp_path / "pcip%2Fstaging.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_canonical_methodology_dimensions_upgrade_from_0020(tmp_path):
    """0021 is additive and does not reinterpret the 0020 provenance fields."""
    database_path = tmp_path / "methodology-0020.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    schema = (
        "CREATE TABLE study_methodology_configurations ("
        "id INTEGER PRIMARY KEY, organisation_id INTEGER NOT NULL, study_id INTEGER NOT NULL, "
        "research_approaches_json TEXT NOT NULL DEFAULT '[]', evidence_methods_json TEXT NOT NULL DEFAULT '[]', "
        "analysis_approaches_json TEXT NOT NULL DEFAULT '[]', theoretical_orientations_json TEXT NOT NULL DEFAULT '[]'"
        ");"
    )
    created = subprocess.run(["sqlite3", str(database_path), schema], capture_output=True, text=True, check=False)
    assert created.returncode == 0, created.stderr
    for command in ([sys.executable, "-m", "alembic", "stamp", "0020"], [sys.executable, "-m", "alembic", "upgrade", "head"]):
        result = subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    columns = subprocess.run(["sqlite3", str(database_path), "PRAGMA table_info(study_methodology_configurations);"], capture_output=True, text=True, check=False)
    assert columns.returncode == 0, columns.stderr
    assert "research_philosophy" in columns.stdout
    assert "research_design" in columns.stdout
    assert "secondary_design" in columns.stdout


def test_optional_participant_location_upgrade_downgrade_and_reupgrade(tmp_path):
    database_path = tmp_path / "location-0021.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    for command in (
        [sys.executable, "-m", "alembic", "upgrade", "0021"],
        [sys.executable, "-m", "alembic", "upgrade", "0022"],
        [sys.executable, "-m", "alembic", "downgrade", "0021"],
        [sys.executable, "-m", "alembic", "upgrade", "0022"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "alembic", "check"],
    ):
        result = subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    revision = subprocess.run([sys.executable, "-m", "alembic", "current"], cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)
    assert revision.returncode == 0, revision.stderr
    assert "0023" in revision.stdout
    columns = subprocess.run(["sqlite3", str(database_path), "PRAGMA table_info(activity_responses);"], capture_output=True, text=True, check=False)
    assert columns.returncode == 0, columns.stderr
    assert "location_latitude" in columns.stdout


def test_organisation_archiving_upgrade_preserves_existing_rows_and_downgrade_is_safe(tmp_path):
    database_path = tmp_path / "organisation-archiving-0022.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"

    upgrade_0022 = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0022"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade_0022.returncode == 0, upgrade_0022.stderr
    inserted = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "INSERT INTO organisations (name, slug, created_at) VALUES ('Existing organisation', 'existing-organisation', CURRENT_TIMESTAMP);",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inserted.returncode == 0, inserted.stderr

    for command in (
        [sys.executable, "-m", "alembic", "upgrade", "0023"],
        [sys.executable, "-m", "alembic", "current"],
        [sys.executable, "-m", "alembic", "check"],
    ):
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        if command[-1] == "current":
            assert "0023" in result.stdout

    active = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "SELECT name || ':' || COALESCE(archived_at, 'active') FROM organisations WHERE slug = 'existing-organisation';",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert active.returncode == 0, active.stderr
    assert active.stdout.strip() == "Existing organisation:active"

    for command in (
        [sys.executable, "-m", "alembic", "downgrade", "0022"],
        [sys.executable, "-m", "alembic", "upgrade", "0023"],
    ):
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    archived = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "UPDATE organisations SET archived_at = CURRENT_TIMESTAMP WHERE slug = 'existing-organisation';",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert archived.returncode == 0, archived.stderr
    refused = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0022"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "Cannot downgrade 0023 while archived organisations exist." in refused.stderr
