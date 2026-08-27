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
        [sys.executable, "-m", "alembic", "check"],
    ):
        result = subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    revision = subprocess.run([sys.executable, "-m", "alembic", "current"], cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)
    assert revision.returncode == 0, revision.stderr
    assert "0022" in revision.stdout
    columns = subprocess.run(["sqlite3", str(database_path), "PRAGMA table_info(activity_responses);"], capture_output=True, text=True, check=False)
    assert columns.returncode == 0, columns.stderr
    assert "location_latitude" in columns.stdout
