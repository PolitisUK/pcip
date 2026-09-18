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
    assert "0025" in revision.stdout
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
            [sys.executable, "-m", "alembic", "upgrade", "head"],
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
            assert "0025" in result.stdout

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
    credentials = subprocess.run(
        ["sqlite3", str(database_path), "PRAGMA table_info(participant_password_credentials);"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert credentials.returncode == 0, credentials.stderr
    assert "password_hash" in credentials.stdout
    assert "login_identifier_normalised" in credentials.stdout

    for command in (
        [sys.executable, "-m", "alembic", "downgrade", "0022"],
        [sys.executable, "-m", "alembic", "upgrade", "0024"],
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


def test_analysis_targets_migration_enforces_concrete_sources_and_tenant_scope(tmp_path):
    database_path = tmp_path / "analysis-targets.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0024"],
        cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    # 0001's historical metadata bootstraps an empty database with current
    # tables. Remove this AW-01 table after stopping at the released baseline
    # to exercise the production-shaped 0024 -> 0025 path explicitly.
    removed = subprocess.run(
        ["sqlite3", str(database_path), "DROP TABLE analysis_targets;"],
        capture_output=True, text=True, check=False,
    )
    assert removed.returncode == 0, removed.stderr
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    schema = """
        PRAGMA foreign_keys = ON;
        INSERT INTO organisations (id, name, slug, created_at) VALUES (1, 'One', 'one', CURRENT_TIMESTAMP), (2, 'Two', 'two', CURRENT_TIMESTAMP);
        INSERT INTO users (id, organisation_id, name, email, session_version, failed_login_count, role, is_platform_admin, is_active, created_at) VALUES (1, 1, 'Researcher', 'one@example.test', 1, 0, 'researcher', 0, 1, CURRENT_TIMESTAMP), (2, 2, 'Foreign Researcher', 'two@example.test', 1, 0, 'researcher', 0, 1, CURRENT_TIMESTAMP);
        INSERT INTO projects (id, organisation_id, title, code, description, status, created_by_id, created_at, updated_at) VALUES (1, 1, 'Project', 'P1', '', 'draft', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO studies (id, organisation_id, project_id, title, code, description, methodology, status, demographics_schema_json, created_by_id, created_at, updated_at) VALUES (1, 1, 1, 'Study', 'S1', '', 'diary', 'draft', '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO participants (id, organisation_id, reference, name, status, consent_status, communication_preference, tags, demographics_json, notes, created_by_id, created_at, updated_at) VALUES (1, 1, 'Case 1', 'Participant', 'active', 'granted', 'email', '', '{}', '', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        INSERT INTO study_enrolments (organisation_id, study_id, participant_id, status, enrolled_at) VALUES (1, 1, 1, 'enrolled', CURRENT_TIMESTAMP);
        INSERT INTO activities (id, organisation_id, study_id, title, prompt, activity_type, options_json, position, required, allow_multiple_entries, allow_participant_location, release_offset_days, created_at) VALUES (1, 1, 1, 'Activity', '', 'long_text', '[]', 1, 1, 0, 0, 0, CURRENT_TIMESTAMP);
        INSERT INTO activity_responses (id, organisation_id, study_id, activity_id, participant_id, value_json, status, repeatable, updated_at) VALUES (1, 1, 1, 1, 1, '{}', 'submitted', 0, CURRENT_TIMESTAMP);
        INSERT INTO analysis_targets (organisation_id, study_id, target_type, activity_response_id, anchor_json, authorship, created_by_id, created_at) VALUES (1, 1, 'activity_response', 1, '{"start":0,"end":1}', 'researcher', 1, CURRENT_TIMESTAMP);
    """
    inserted = subprocess.run(["sqlite3", str(database_path), schema], capture_output=True, text=True, check=False)
    assert inserted.returncode == 0, inserted.stderr
    system_target = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO analysis_targets (organisation_id, study_id, target_type, activity_response_id, anchor_json, authorship, created_at) VALUES (1, 1, 'activity_response', 1, '{}', 'system', CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert system_target.returncode == 0, system_target.stderr
    foreign_creator = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO analysis_targets (organisation_id, study_id, target_type, activity_response_id, anchor_json, authorship, created_by_id, created_at) VALUES (1, 1, 'activity_response', 1, '{}', 'researcher', 2, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_creator.returncode != 0
    assert "researcher is outside organisation" in foreign_creator.stderr
    foreign_creator_update = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analysis_targets SET created_by_id = 2 WHERE id = 1;"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_creator_update.returncode != 0
    assert "researcher is outside organisation" in foreign_creator_update.stderr
    invalid_scope = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO analysis_targets (organisation_id, study_id, target_type, activity_response_id, anchor_json, authorship, created_by_id, created_at) VALUES (2, 1, 'activity_response', 1, '{}', 'researcher', 1, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert invalid_scope.returncode != 0
    assert "outside organisation" in invalid_scope.stderr
    invalid_shape = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO analysis_targets (organisation_id, study_id, target_type, anchor_json, authorship, created_by_id, created_at) VALUES (1, 1, 'activity_response', '{}', 'researcher', 1, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert invalid_shape.returncode != 0
