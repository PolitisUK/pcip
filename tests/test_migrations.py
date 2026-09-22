import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_store_reviewer_designation_upgrade_downgrade_and_fresh_schema(tmp_path):
    database_path = tmp_path / "store-reviewer-0037.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"

    def run_alembic(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result

    def participant_columns():
        result = subprocess.run(
            ["sqlite3", str(database_path), "PRAGMA table_info(participants);"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    run_alembic("upgrade", "0036")
    # 0001 uses current ORM metadata when building a fresh rehearsal schema.
    assert "is_store_reviewer" in participant_columns()
    removed = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "ALTER TABLE participants DROP COLUMN is_store_reviewer;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert removed.returncode == 0, removed.stderr
    assert "is_store_reviewer" not in participant_columns()

    run_alembic("upgrade", "0037")
    columns = participant_columns()
    assert "is_store_reviewer" in columns
    assert "is_store_reviewer|BOOLEAN|1|0" in columns
    assert "0037" in run_alembic("current").stdout

    run_alembic("downgrade", "0036")
    assert "is_store_reviewer" not in participant_columns()
    run_alembic("upgrade", "head")
    assert "is_store_reviewer" in participant_columns()
    run_alembic("check")


def test_analysis_actor_guards_use_active_organisation_memberships(tmp_path):
    database_path = tmp_path / "analysis-actor-memberships.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr

    valid = """
      PRAGMA foreign_keys=ON;
      INSERT INTO organisations (id,name,slug,created_at) VALUES
        (1,'Primary','actor-primary',CURRENT_TIMESTAMP),
        (2,'Research','actor-research',CURRENT_TIMESTAMP);
      INSERT INTO users (id,organisation_id,name,email,session_version,failed_login_count,role,is_platform_admin,is_active,created_at) VALUES
        (1,1,'Multi-org researcher','multi-org@example.test',1,0,'researcher',0,1,CURRENT_TIMESTAMP),
        (2,2,'Research owner','research-owner@example.test',1,0,'owner',0,1,CURRENT_TIMESTAMP);
      INSERT INTO organisation_memberships (user_id,organisation_id,role,is_active,created_at) VALUES
        (1,1,'researcher',1,CURRENT_TIMESTAMP),
        (1,2,'researcher',1,CURRENT_TIMESTAMP),
        (2,2,'owner',1,CURRENT_TIMESTAMP);
      INSERT INTO projects (id,organisation_id,title,code,description,status,created_by_id,created_at,updated_at)
        VALUES (1,2,'Synthetic project','ACTOR-PROJECT','','draft',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO studies (id,organisation_id,project_id,title,code,description,methodology,status,demographics_schema_json,created_by_id,created_at,updated_at)
        VALUES (1,2,1,'Synthetic study','ACTOR-STUDY','','diary','draft','[]',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO research_codes (id,organisation_id,study_id,name,definition,created_by_id,created_at,updated_at) VALUES
        (1,2,1,'Source','',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
        (2,2,1,'Target','',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
        (3,2,1,'Created through membership','',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO research_memos (id,organisation_id,study_id,scope_type,title,body,author_id,created_at,updated_at)
        VALUES (1,2,1,'study','Membership memo','Synthetic body',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO analytical_relationships (id,organisation_id,study_id,source_type,source_id,relationship_type,target_type,target_id,rationale,created_by_id,created_at)
        VALUES (1,2,1,'code',1,'supports','code',2,'Synthetic rationale',1,CURRENT_TIMESTAMP);
      INSERT INTO analysis_canvases (id,organisation_id,study_id,owner_id,view_metadata_json,created_at,updated_at)
        VALUES (1,2,1,1,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
    """
    inserted = subprocess.run(
        ["sqlite3", str(database_path), valid],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inserted.returncode == 0, inserted.stderr

    disabled = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "UPDATE organisation_memberships SET is_active=0 WHERE user_id=1 AND organisation_id=2;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert disabled.returncode == 0, disabled.stderr

    historic_update = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "UPDATE research_codes SET definition='Historic record retained' WHERE id=3;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert historic_update.returncode == 0, historic_update.stderr

    rejected_writes = (
        (
            "INSERT INTO research_codes (organisation_id,study_id,name,definition,created_by_id,created_at,updated_at) VALUES (2,1,'Blocked','',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);",
            "research code creator is outside organisation",
        ),
        (
            "INSERT INTO research_memos (organisation_id,study_id,scope_type,title,body,author_id,created_at,updated_at) VALUES (2,1,'study','Blocked','Synthetic body',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);",
            "research memo author scope",
        ),
        (
            "INSERT INTO analytical_relationships (organisation_id,study_id,source_type,source_id,relationship_type,target_type,target_id,rationale,created_by_id,created_at) VALUES (2,1,'code',1,'contradicts','code',2,'Blocked',1,CURRENT_TIMESTAMP);",
            "analytical relationship author scope",
        ),
        (
            "DELETE FROM analysis_canvases WHERE id=1; INSERT INTO analysis_canvases (id,organisation_id,study_id,owner_id,view_metadata_json,created_at,updated_at) VALUES (2,2,1,1,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);",
            "analysis canvas owner scope",
        ),
    )
    for statement, expected_error in rejected_writes:
        rejected = subprocess.run(
            ["sqlite3", str(database_path), statement],
            capture_output=True,
            text=True,
            check=False,
        )
        assert rejected.returncode != 0
        assert expected_error in rejected.stderr


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
    assert "0037" in revision.stdout
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
            assert "0037" in result.stdout

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
            INSERT INTO organisation_memberships (user_id,organisation_id,role,is_active,created_at) VALUES (1,1,'researcher',1,CURRENT_TIMESTAMP),(2,2,'researcher',1,CURRENT_TIMESTAMP);
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
    codebook = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_codes (id, organisation_id, study_id, name, definition, created_by_id, created_at, updated_at) VALUES (1, 1, 1, 'Trust', 'Institutional trust', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP); INSERT INTO research_codes (id, organisation_id, study_id, name, definition, parent_code_id, created_by_id, created_at, updated_at) VALUES (2, 1, 1, 'Trust in officers', '', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert codebook.returncode == 0, codebook.stderr
    foreign_code_creator = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_codes (organisation_id, study_id, name, definition, created_by_id, created_at, updated_at) VALUES (1, 1, 'Foreign', '', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_code_creator.returncode != 0
    assert "creator is outside organisation" in foreign_code_creator.stderr
    circular_code = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_codes SET parent_code_id = 2 WHERE id = 1;"],
        capture_output=True, text=True, check=False,
    )
    assert circular_code.returncode != 0
    assert "hierarchy is circular" in circular_code.stderr
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
    valid_annotation = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO studies (id, organisation_id, project_id, title, code, description, methodology, status, demographics_schema_json, created_by_id, created_at, updated_at) VALUES (2, 1, 1, 'Other study', 'S2', '', 'diary', 'draft', '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP); INSERT INTO research_annotations (id, organisation_id, study_id, analysis_target_id, author_id, anchor_json, body, created_at, updated_at) VALUES (1, 1, 1, 1, 1, '{\"version\":1}', 'Analytical note', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert valid_annotation.returncode == 0, valid_annotation.stderr
    foreign_author = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_annotations (organisation_id, study_id, analysis_target_id, author_id, anchor_json, body, created_at, updated_at) VALUES (1, 1, 1, 2, '{}', 'Forged', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_author.returncode != 0
    assert "research annotation author scope" in foreign_author.stderr
    foreign_study_target = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_annotations SET study_id = 2 WHERE id = 1;"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_study_target.returncode != 0
    assert "research annotation target scope" in foreign_study_target.stderr
    forged_scope_update = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_annotations SET organisation_id = 2 WHERE id = 1;"],
        capture_output=True, text=True, check=False,
    )
    assert forged_scope_update.returncode != 0
    assert "research annotation study scope" in forged_scope_update.stderr
    valid_memo = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_memos (id, organisation_id, study_id, scope_type, title, body, author_id, created_at, updated_at) VALUES (1, 1, 1, 'study', 'Reflexive note', 'Analytical text', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert valid_memo.returncode == 0, valid_memo.stderr
    forged_memo_scope = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_memos SET scope_type='code', research_code_id=999 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert forged_memo_scope.returncode != 0
    assert "research memo code scope" in forged_memo_scope.stderr
    foreign_memo_author = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_memos SET author_id=2 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_memo_author.returncode != 0
    assert "research memo author scope" in foreign_memo_author.stderr
    valid_relationship = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO analytical_relationships (id, organisation_id, study_id, source_type, source_id, relationship_type, target_type, target_id, rationale, created_by_id, created_at) VALUES (1, 1, 1, 'analysis_target', 1, 'supports', 'code', 1, 'Researcher assertion', 1, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert valid_relationship.returncode == 0, valid_relationship.stderr
    forged_relationship_target = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analytical_relationships SET target_id=999 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert forged_relationship_target.returncode != 0
    assert "analytical relationship target scope" in forged_relationship_target.stderr
    foreign_relationship_author = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analytical_relationships SET created_by_id=2 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_relationship_author.returncode != 0
    assert "analytical relationship author scope" in foreign_relationship_author.stderr
    valid_theme_link = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_themes (id, organisation_id, study_id, name, description, source_suggestion_ids_json, status, created_by_id, created_at, updated_at) VALUES (1, 1, 1, 'Access', 'Researcher definition', '[]', 'researcher_draft', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP); INSERT INTO research_theme_codes (id, organisation_id, study_id, research_theme_id, research_code_id, linked_by_id, created_at) VALUES (1, 1, 1, 1, 1, 1, CURRENT_TIMESTAMP);"],
        capture_output=True, text=True, check=False,
    )
    assert valid_theme_link.returncode == 0, valid_theme_link.stderr
    forged_theme_code = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_theme_codes SET research_code_id=999 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert forged_theme_code.returncode != 0
    assert "theme code code scope" in forged_theme_code.stderr
    foreign_theme_linker = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE research_theme_codes SET linked_by_id=2 WHERE id=1;"],
        capture_output=True, text=True, check=False,
    )
    assert foreign_theme_linker.returncode != 0
    assert "theme code researcher scope" in foreign_theme_linker.stderr


def test_analysis_canvas_migration_enforces_canvas_and_object_scope(tmp_path):
    database_path = tmp_path / "analysis-canvas.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    baseline = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0031"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stderr
    removed = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "DROP TABLE analysis_canvas_nodes; DROP TABLE analysis_canvases;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert removed.returncode == 0, removed.stderr
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    schema = """
      PRAGMA foreign_keys=ON;
          INSERT INTO organisations (id,name,slug,created_at) VALUES (1,'One','canvas-one',CURRENT_TIMESTAMP),(2,'Two','canvas-two',CURRENT_TIMESTAMP);
          INSERT INTO users (id,organisation_id,name,email,session_version,failed_login_count,role,is_platform_admin,is_active,created_at) VALUES (1,1,'One','canvas-one@example.test',1,0,'researcher',0,1,CURRENT_TIMESTAMP),(2,2,'Two','canvas-two@example.test',1,0,'researcher',0,1,CURRENT_TIMESTAMP);
          INSERT INTO organisation_memberships (user_id,organisation_id,role,is_active,created_at) VALUES (1,1,'researcher',1,CURRENT_TIMESTAMP),(2,2,'researcher',1,CURRENT_TIMESTAMP);
          INSERT INTO projects (id,organisation_id,title,code,description,status,created_by_id,created_at,updated_at) VALUES (1,1,'One','CP1','','draft',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,'Two','CP2','','draft',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO studies (id,organisation_id,project_id,title,code,description,methodology,status,demographics_schema_json,created_by_id,created_at,updated_at) VALUES (1,1,1,'One','CS1','','diary','draft','[]',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,2,'Two','CS2','','diary','draft','[]',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO research_codes (id,organisation_id,study_id,name,definition,created_by_id,created_at,updated_at) VALUES (1,1,1,'Local','',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,2,'Foreign','',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO analysis_canvases (id,organisation_id,study_id,owner_id,view_metadata_json,created_at,updated_at) VALUES (1,1,1,1,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO analysis_canvas_nodes (id,organisation_id,study_id,canvas_id,object_type,object_id,x,y,added_by_id,created_at,updated_at) VALUES (1,1,1,1,'code',1,20,30,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
    """
    inserted = subprocess.run(
        ["sqlite3", str(database_path), schema],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inserted.returncode == 0, inserted.stderr
    foreign_owner = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "INSERT INTO analysis_canvases (organisation_id,study_id,owner_id,view_metadata_json,created_at,updated_at) VALUES (1,1,2,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert foreign_owner.returncode != 0
    assert "analysis canvas owner scope" in foreign_owner.stderr
    foreign_object = subprocess.run(
        [
            "sqlite3",
            str(database_path),
            "INSERT INTO analysis_canvas_nodes (organisation_id,study_id,canvas_id,object_type,object_id,x,y,added_by_id,created_at,updated_at) VALUES (1,1,1,'code',2,20,30,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert foreign_object.returncode != 0
    assert "analysis canvas code scope" in foreign_object.stderr
    forged_update = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analysis_canvas_nodes SET object_id=2 WHERE id=1;"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert forged_update.returncode != 0
    assert "analysis canvas code scope" in forged_update.stderr
    checked = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    for command in (
        [sys.executable, "-m", "alembic", "downgrade", "0031"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "alembic", "check"],
    ):
        rehearsed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rehearsed.returncode == 0, rehearsed.stderr


def test_research_findings_migration_extends_relationship_and_canvas_scope(tmp_path):
    database_path = tmp_path / "research-findings.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    baseline = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0032"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stderr
    legacy_schema = """
      PRAGMA foreign_keys=OFF;
      DROP TABLE analytical_relationships;
      DROP TABLE analysis_canvas_nodes;
      DROP TABLE research_findings;
      CREATE TABLE analytical_relationships (
        id INTEGER PRIMARY KEY, organisation_id INTEGER NOT NULL REFERENCES organisations(id), study_id INTEGER NOT NULL REFERENCES studies(id),
        source_type VARCHAR(40) NOT NULL, source_id INTEGER NOT NULL, relationship_type VARCHAR(30) NOT NULL,
        target_type VARCHAR(40) NOT NULL, target_id INTEGER NOT NULL, rationale TEXT NOT NULL DEFAULT '', created_by_id INTEGER NOT NULL REFERENCES users(id), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_analytical_relationship_type CHECK (relationship_type IN ('supports','contradicts','explains','relates_to','precedes','follows','refines')),
        CONSTRAINT ck_analytical_relationship_source_type CHECK (source_type IN ('analysis_target','code_application','annotation','memo','code','theme')),
        CONSTRAINT ck_analytical_relationship_target_type CHECK (target_type IN ('analysis_target','code_application','annotation','memo','code','theme')),
        CONSTRAINT ck_analytical_relationship_not_self CHECK (source_type <> target_type OR source_id <> target_id),
        CONSTRAINT uq_analytical_relationship_assertion UNIQUE (organisation_id,study_id,source_type,source_id,relationship_type,target_type,target_id)
      );
      CREATE TABLE analysis_canvas_nodes (
        id INTEGER PRIMARY KEY, organisation_id INTEGER NOT NULL REFERENCES organisations(id), study_id INTEGER NOT NULL REFERENCES studies(id), canvas_id INTEGER NOT NULL REFERENCES analysis_canvases(id) ON DELETE CASCADE,
        object_type VARCHAR(40) NOT NULL, object_id INTEGER NOT NULL, x FLOAT NOT NULL, y FLOAT NOT NULL, added_by_id INTEGER NOT NULL REFERENCES users(id), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_analysis_canvas_node_type CHECK (object_type IN ('analysis_target','code_application','annotation','memo','code','theme')),
        CONSTRAINT ck_analysis_canvas_node_coordinates CHECK (x >= 0 AND x <= 4000 AND y >= 0 AND y <= 4000),
        CONSTRAINT uq_analysis_canvas_node_object UNIQUE (canvas_id,object_type,object_id)
      );
      PRAGMA foreign_keys=ON;
    """
    legacy = subprocess.run(
        ["sqlite3", str(database_path), legacy_schema],
        capture_output=True,
        text=True,
        check=False,
    )
    assert legacy.returncode == 0, legacy.stderr
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    valid = """
      PRAGMA foreign_keys=ON;
      INSERT INTO organisations (id,name,slug,created_at) VALUES (1,'One','finding-one',CURRENT_TIMESTAMP),(2,'Two','finding-two',CURRENT_TIMESTAMP);
      INSERT INTO users (id,organisation_id,name,email,session_version,failed_login_count,role,is_platform_admin,is_active,created_at) VALUES (1,1,'One','finding-one@example.test',1,0,'researcher',0,1,CURRENT_TIMESTAMP),(2,2,'Two','finding-two@example.test',1,0,'researcher',0,1,CURRENT_TIMESTAMP);
      INSERT INTO organisation_memberships (user_id,organisation_id,role,is_active,created_at) VALUES (1,1,'researcher',1,CURRENT_TIMESTAMP),(2,2,'researcher',1,CURRENT_TIMESTAMP);
      INSERT INTO projects (id,organisation_id,title,code,description,status,created_by_id,created_at,updated_at) VALUES (1,1,'One','FP1','','draft',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,'Two','FP2','','draft',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO studies (id,organisation_id,project_id,title,code,description,methodology,status,demographics_schema_json,created_by_id,created_at,updated_at) VALUES (1,1,1,'One','FS1','','diary','draft','[]',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,2,'Two','FS2','','diary','draft','[]',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO research_codes (id,organisation_id,study_id,name,definition,created_by_id,created_at,updated_at) VALUES (1,1,1,'Local','',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(2,2,2,'Foreign','',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO analysis_canvases (id,organisation_id,study_id,owner_id,view_metadata_json,created_at,updated_at) VALUES (1,1,1,1,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      PRAGMA foreign_keys=OFF;
      INSERT INTO research_analysis_suggestions (id,organisation_id,study_id,source_response_id,source_snapshot,suggested_codes_json,provisional_insight,confidence,status,reviewer_note,methodology_id,methodology_variant,methodology_library_version,methodology_rule_references_json,protocol_version,evidence_item_ids_json,model_provider,model_deployment,prompt_template_version,human_review_required,created_at) VALUES (1,1,1,999,'Bounded source','[]','Candidate finding',0.5,'accepted','','M01','','1.0.0','[]','','[]','approved','model-v1','research-analysis-v1',1,CURRENT_TIMESTAMP);
      PRAGMA foreign_keys=ON;
      INSERT INTO research_findings (id,organisation_id,study_id,title,body,created_by_id,created_at,updated_at) VALUES (1,1,1,'Access finding','Substantive researcher conclusion',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO research_findings (id,organisation_id,study_id,title,body,created_by_id,originating_suggestion_id,created_at,updated_at) VALUES (2,1,1,'Converted finding','Researcher-authored conversion',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
      INSERT INTO audit_events (organisation_id,project_id,study_id,actor_user_id,action,entity_type,entity_id,detail,created_at) VALUES (1,1,1,1,'research_finding.created','research_finding','1','finding created',CURRENT_TIMESTAMP);
      INSERT INTO analytical_relationships (organisation_id,study_id,source_type,source_id,relationship_type,target_type,target_id,rationale,created_by_id,created_at) VALUES (1,1,'finding',1,'qualifies','code',1,'Qualified interpretation',1,CURRENT_TIMESTAMP);
      INSERT INTO analysis_canvas_nodes (organisation_id,study_id,canvas_id,object_type,object_id,x,y,added_by_id,created_at,updated_at) VALUES (1,1,1,'finding',1,20,30,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
    """
    inserted = subprocess.run(
        ["sqlite3", str(database_path), valid],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inserted.returncode == 0, inserted.stderr
    foreign_creator = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_findings (organisation_id,study_id,title,body,created_by_id,created_at,updated_at) VALUES (1,1,'Forged','Foreign creator',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert foreign_creator.returncode != 0
    assert "research finding creator scope" in foreign_creator.stderr
    foreign_suggestion = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO research_findings (organisation_id,study_id,title,body,created_by_id,originating_suggestion_id,created_at,updated_at) VALUES (2,2,'Forged origin','Cross-study suggestion',2,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert foreign_suggestion.returncode != 0
    assert "research finding suggestion scope" in foreign_suggestion.stderr
    foreign_audit_context = subprocess.run(
        ["sqlite3", str(database_path), "INSERT INTO audit_events (organisation_id,project_id,study_id,actor_user_id,action,entity_type,entity_id,detail,created_at) VALUES (1,2,1,1,'research_finding.created','research_finding','1','forged context',CURRENT_TIMESTAMP);"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert foreign_audit_context.returncode != 0
    assert "audit project scope" in foreign_audit_context.stderr
    forged_relationship = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analytical_relationships SET source_id=999 WHERE source_type='finding';"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert forged_relationship.returncode != 0
    assert "analytical relationship source scope" in forged_relationship.stderr
    forged_canvas = subprocess.run(
        ["sqlite3", str(database_path), "UPDATE analysis_canvas_nodes SET object_id=999 WHERE object_type='finding';"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert forged_canvas.returncode != 0
    assert "analysis canvas finding scope" in forged_canvas.stderr
    for command in (
        [sys.executable, "-m", "alembic", "downgrade", "0032"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
    ):
        rehearsed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rehearsed.returncode == 0, rehearsed.stderr
