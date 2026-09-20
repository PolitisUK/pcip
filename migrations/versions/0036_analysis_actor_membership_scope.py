"""Use active organisation memberships for Analysis Workbench actor scope.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

import importlib

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


RELATIONSHIP_OBJECTS = {
    "analysis_target": "analysis_targets",
    "code_application": "code_applications",
    "annotation": "research_annotations",
    "memo": "research_memos",
    "code": "research_codes",
    "theme": "research_themes",
    "finding": "research_findings",
}


def _postgres_member(actor: str) -> str:
    return (
        "analysis_actor_has_active_organisation_membership("
        f"NEW.{actor}, NEW.organisation_id)"
    )


def _sqlite_member(actor: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM organisation_memberships m "
        f"WHERE m.user_id=NEW.{actor} "
        "AND m.organisation_id=NEW.organisation_id AND m.is_active=1)"
    )


def _postgres_actor_guard(actor: str) -> str:
    return (
        "(TG_OP='INSERT' OR "
        f"NEW.{actor} IS DISTINCT FROM OLD.{actor} OR "
        "NEW.organisation_id IS DISTINCT FROM OLD.organisation_id) "
        f"AND NOT {_postgres_member(actor)}"
    )


def _sqlite_actor_guard(action: str, actor: str) -> str:
    changed = ""
    if action == "UPDATE":
        changed = (
            f"(NEW.{actor} IS NOT OLD.{actor} OR "
            "NEW.organisation_id IS NOT OLD.organisation_id) AND "
        )
    return f"{changed}NOT {_sqlite_member(actor)}"


def _sqlite_analysis_target_actor_guard(action: str) -> str:
    changed = ""
    if action == "UPDATE":
        changed = (
            "(NEW.authorship IS NOT OLD.authorship OR "
            "NEW.created_by_id IS NOT OLD.created_by_id OR "
            "NEW.organisation_id IS NOT OLD.organisation_id) AND "
        )
    return f"{changed}NOT {_sqlite_member('created_by_id')}"


def _drop_actor_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for trigger, table in (
            ("trg_analysis_targets_scope", "analysis_targets"),
            ("trg_research_codes_scope", "research_codes"),
            ("trg_code_applications_scope", "code_applications"),
            ("trg_research_annotations_scope", "research_annotations"),
            ("trg_research_memos_scope", "research_memos"),
            ("trg_analytical_relationships_scope", "analytical_relationships"),
            ("trg_research_themes_scope", "research_themes"),
            ("trg_research_theme_codes_scope", "research_theme_codes"),
            ("trg_analysis_canvases_scope", "analysis_canvases"),
            ("trg_research_findings_scope", "research_findings"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        for function in (
            "validate_analysis_target_scope",
            "validate_research_code_scope",
            "validate_code_application_scope",
            "validate_research_annotation_scope",
            "validate_research_memo_scope",
            "validate_analytical_relationship_scope",
            "validate_research_theme_scope",
            "validate_research_theme_code_scope",
            "validate_analysis_canvas_scope",
            "validate_research_finding_scope",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    else:
        for table in (
            "analysis_targets",
            "research_codes",
            "code_applications",
            "research_annotations",
            "research_memos",
            "analytical_relationships",
            "research_themes",
            "research_theme_codes",
            "analysis_canvases",
            "research_findings",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_insert")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_update")


def _create_postgresql_guards() -> None:
    op.execute("""
    CREATE FUNCTION analysis_actor_has_active_organisation_membership(
      actor_user_id integer,
      actor_organisation_id integer
    ) RETURNS boolean AS $$
      SELECT EXISTS (
        SELECT 1 FROM organisation_memberships
        WHERE user_id=actor_user_id
          AND organisation_id=actor_organisation_id
          AND is_active=true
      );
    $$ LANGUAGE sql STABLE;
    """)

    op.execute(f"""
    CREATE FUNCTION validate_analysis_target_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analysis target study is outside organisation'; END IF;
      IF NEW.authorship='researcher' AND (TG_OP='INSERT' OR NEW.authorship IS DISTINCT FROM OLD.authorship OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id OR NEW.organisation_id IS DISTINCT FROM OLD.organisation_id) AND NOT {_postgres_member("created_by_id")} THEN RAISE EXCEPTION 'analysis target researcher is outside organisation'; END IF;
      IF NEW.target_type='activity_response' AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis target response is outside study scope'; END IF;
      IF NEW.target_type='evidence_file' AND NOT EXISTS (SELECT 1 FROM evidence_files WHERE id=NEW.evidence_file_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis target evidence is outside study scope'; END IF;
      IF NEW.target_type='participant_case' AND NOT EXISTS (SELECT 1 FROM study_enrolments WHERE organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND participant_id=NEW.participant_id) THEN RAISE EXCEPTION 'analysis target participant is outside study scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_analysis_targets_scope BEFORE INSERT OR UPDATE ON analysis_targets FOR EACH ROW EXECUTE FUNCTION validate_analysis_target_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_code_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research code study is outside organisation'; END IF;
      IF {_postgres_actor_guard("created_by_id")} THEN RAISE EXCEPTION 'research code creator is outside organisation'; END IF;
      IF NEW.parent_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.parent_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research code parent is outside study scope'; END IF;
      IF NEW.parent_code_id IS NOT NULL AND EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.parent_code_id AND archived_at IS NOT NULL) THEN RAISE EXCEPTION 'research code parent is archived'; END IF;
      IF NEW.parent_code_id=NEW.id THEN RAISE EXCEPTION 'research code cannot be its own parent'; END IF;
      IF NEW.parent_code_id IS NOT NULL AND EXISTS (WITH RECURSIVE ancestors(id,parent_code_id) AS (SELECT id,parent_code_id FROM research_codes WHERE id=NEW.parent_code_id UNION ALL SELECT c.id,c.parent_code_id FROM research_codes c JOIN ancestors a ON c.id=a.parent_code_id WHERE a.parent_code_id IS NOT NULL) SELECT 1 FROM ancestors WHERE id=NEW.id) THEN RAISE EXCEPTION 'research code hierarchy is circular'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_codes_scope BEFORE INSERT OR UPDATE ON research_codes FOR EACH ROW EXECUTE FUNCTION validate_research_code_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_code_application_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'code application study scope'; END IF;
      IF NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'code application target scope'; END IF;
      IF NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'code application code scope'; END IF;
      IF {_postgres_actor_guard("applied_by_id")} THEN RAISE EXCEPTION 'code application researcher scope'; END IF;
      IF TG_OP='INSERT' AND EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND archived_at IS NOT NULL) THEN RAISE EXCEPTION 'code application code archived'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_code_applications_scope BEFORE INSERT OR UPDATE ON code_applications FOR EACH ROW EXECUTE FUNCTION validate_code_application_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_annotation_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research annotation study scope'; END IF;
      IF NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research annotation target scope'; END IF;
      IF {_postgres_actor_guard("author_id")} THEN RAISE EXCEPTION 'research annotation author scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_annotations_scope BEFORE INSERT OR UPDATE ON research_annotations FOR EACH ROW EXECUTE FUNCTION validate_research_annotation_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_memo_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research memo study scope'; END IF;
      IF {_postgres_actor_guard("author_id")} THEN RAISE EXCEPTION 'research memo author scope'; END IF;
      IF NEW.archived_by_id IS NOT NULL AND {_postgres_actor_guard("archived_by_id")} THEN RAISE EXCEPTION 'research memo archiver scope'; END IF;
      IF NEW.participant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM participants p JOIN study_enrolments e ON e.participant_id=p.id WHERE p.id=NEW.participant_id AND p.organisation_id=NEW.organisation_id AND e.organisation_id=NEW.organisation_id AND e.study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo participant scope'; END IF;
      IF NEW.activity_response_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo response scope'; END IF;
      IF NEW.analysis_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo target scope'; END IF;
      IF NEW.research_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo code scope'; END IF;
      IF NEW.research_theme_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo theme scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_memos_scope BEFORE INSERT OR UPDATE ON research_memos FOR EACH ROW EXECUTE FUNCTION validate_research_memo_scope();
    """)

    relationship_checks = []
    for side in ("source", "target"):
        for object_type, table in RELATIONSHIP_OBJECTS.items():
            relationship_checks.append(
                f"IF NEW.{side}_type='{object_type}' AND NOT EXISTS "
                f"(SELECT 1 FROM {table} WHERE id=NEW.{side}_id "
                "AND organisation_id=NEW.organisation_id "
                "AND study_id=NEW.study_id) THEN RAISE EXCEPTION "
                f"'analytical relationship {side} scope'; END IF;"
            )
    op.execute(f"""
    CREATE FUNCTION validate_analytical_relationship_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analytical relationship study scope'; END IF;
      IF {_postgres_actor_guard("created_by_id")} THEN RAISE EXCEPTION 'analytical relationship author scope'; END IF;
      {" ".join(relationship_checks)}
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_analytical_relationships_scope BEFORE INSERT OR UPDATE ON analytical_relationships FOR EACH ROW EXECUTE FUNCTION validate_analytical_relationship_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_theme_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research theme study scope'; END IF;
      IF {_postgres_actor_guard("created_by_id")} THEN RAISE EXCEPTION 'research theme creator scope'; END IF;
      IF (NEW.archived_at IS NULL) <> (NEW.archived_by_id IS NULL) THEN RAISE EXCEPTION 'research theme archive pair'; END IF;
      IF NEW.archived_by_id IS NOT NULL AND {_postgres_actor_guard("archived_by_id")} THEN RAISE EXCEPTION 'research theme archiver scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_themes_scope BEFORE INSERT OR UPDATE ON research_themes FOR EACH ROW EXECUTE FUNCTION validate_research_theme_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_theme_code_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'theme code study scope'; END IF;
      IF NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'theme code theme scope'; END IF;
      IF NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'theme code code scope'; END IF;
      IF {_postgres_actor_guard("linked_by_id")} THEN RAISE EXCEPTION 'theme code researcher scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_theme_codes_scope BEFORE INSERT OR UPDATE ON research_theme_codes FOR EACH ROW EXECUTE FUNCTION validate_research_theme_code_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_analysis_canvas_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analysis canvas study scope'; END IF;
      IF {_postgres_actor_guard("owner_id")} THEN RAISE EXCEPTION 'analysis canvas owner scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_analysis_canvases_scope BEFORE INSERT OR UPDATE ON analysis_canvases FOR EACH ROW EXECUTE FUNCTION validate_analysis_canvas_scope();
    """)

    op.execute(f"""
    CREATE FUNCTION validate_research_finding_scope() RETURNS trigger AS $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding study scope'; END IF;
      IF {_postgres_actor_guard("created_by_id")} THEN RAISE EXCEPTION 'research finding creator scope'; END IF;
      IF NEW.archived_by_id IS NOT NULL AND {_postgres_actor_guard("archived_by_id")} THEN RAISE EXCEPTION 'research finding archiver scope'; END IF;
      IF NEW.originating_suggestion_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_analysis_suggestions WHERE id=NEW.originating_suggestion_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research finding suggestion scope'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_research_findings_scope BEFORE INSERT OR UPDATE ON research_findings FOR EACH ROW EXECUTE FUNCTION validate_research_finding_scope();
    """)


def _create_sqlite_guards() -> None:
    relationship_checks = []
    for side in ("source", "target"):
        for object_type, table in RELATIONSHIP_OBJECTS.items():
            relationship_checks.append(
                f"SELECT RAISE(ABORT,'analytical relationship {side} scope') "
                f"WHERE NEW.{side}_type='{object_type}' AND NOT EXISTS "
                f"(SELECT 1 FROM {table} WHERE id=NEW.{side}_id "
                "AND organisation_id=NEW.organisation_id "
                "AND study_id=NEW.study_id);"
            )

    for action in ("INSERT", "UPDATE"):
        suffix = action.lower()
        op.execute(f"""
        CREATE TRIGGER trg_analysis_targets_scope_{suffix} BEFORE {action} ON analysis_targets BEGIN
          SELECT RAISE(ABORT,'analysis target study is outside organisation') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'analysis target researcher is outside organisation') WHERE NEW.authorship='researcher' AND {_sqlite_analysis_target_actor_guard(action)};
          SELECT RAISE(ABORT,'analysis target response is outside study scope') WHERE NEW.target_type='activity_response' AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis target evidence is outside study scope') WHERE NEW.target_type='evidence_file' AND NOT EXISTS (SELECT 1 FROM evidence_files WHERE id=NEW.evidence_file_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis target participant is outside study scope') WHERE NEW.target_type='participant_case' AND NOT EXISTS (SELECT 1 FROM study_enrolments WHERE organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND participant_id=NEW.participant_id);
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_codes_scope_{suffix} BEFORE {action} ON research_codes BEGIN
          SELECT RAISE(ABORT,'research code study is outside organisation') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'research code creator is outside organisation') WHERE {_sqlite_actor_guard(action, "created_by_id")};
          SELECT RAISE(ABORT,'research code parent is outside study scope') WHERE NEW.parent_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.parent_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research code parent is archived') WHERE NEW.parent_code_id IS NOT NULL AND EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.parent_code_id AND archived_at IS NOT NULL);
          SELECT RAISE(ABORT,'research code cannot be its own parent') WHERE NEW.parent_code_id=NEW.id;
          SELECT RAISE(ABORT,'research code hierarchy is circular') WHERE NEW.id IS NOT NULL AND NEW.parent_code_id IS NOT NULL AND EXISTS (WITH RECURSIVE ancestors(id,parent_code_id) AS (SELECT id,parent_code_id FROM research_codes WHERE id=NEW.parent_code_id UNION ALL SELECT c.id,c.parent_code_id FROM research_codes c JOIN ancestors a ON c.id=a.parent_code_id WHERE a.parent_code_id IS NOT NULL) SELECT 1 FROM ancestors WHERE id=NEW.id);
        END
        """)
        archived_check = (
            "EXISTS (SELECT 1 FROM research_codes WHERE "
            "id=NEW.research_code_id AND archived_at IS NOT NULL)"
            if action == "INSERT"
            else "0"
        )
        op.execute(f"""
        CREATE TRIGGER trg_code_applications_scope_{suffix} BEFORE {action} ON code_applications BEGIN
          SELECT RAISE(ABORT,'code application study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'code application target scope') WHERE NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'code application code scope') WHERE NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'code application researcher scope') WHERE {_sqlite_actor_guard(action, "applied_by_id")};
          SELECT RAISE(ABORT,'code application code archived') WHERE {archived_check};
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_annotations_scope_{suffix} BEFORE {action} ON research_annotations BEGIN
          SELECT RAISE(ABORT,'research annotation study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'research annotation target scope') WHERE NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research annotation author scope') WHERE {_sqlite_actor_guard(action, "author_id")};
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_memos_scope_{suffix} BEFORE {action} ON research_memos BEGIN
          SELECT RAISE(ABORT,'research memo study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'research memo author scope') WHERE {_sqlite_actor_guard(action, "author_id")};
          SELECT RAISE(ABORT,'research memo archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND {_sqlite_actor_guard(action, "archived_by_id")};
          SELECT RAISE(ABORT,'research memo participant scope') WHERE NEW.participant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM participants p JOIN study_enrolments e ON e.participant_id=p.id WHERE p.id=NEW.participant_id AND p.organisation_id=NEW.organisation_id AND e.organisation_id=NEW.organisation_id AND e.study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research memo response scope') WHERE NEW.activity_response_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research memo target scope') WHERE NEW.analysis_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research memo code scope') WHERE NEW.research_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'research memo theme scope') WHERE NEW.research_theme_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_analytical_relationships_scope_{suffix} BEFORE {action} ON analytical_relationships BEGIN
          SELECT RAISE(ABORT,'analytical relationship study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'analytical relationship author scope') WHERE {_sqlite_actor_guard(action, "created_by_id")};
          {" ".join(relationship_checks)}
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_themes_scope_{suffix} BEFORE {action} ON research_themes BEGIN
          SELECT RAISE(ABORT,'research theme study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'research theme creator scope') WHERE {_sqlite_actor_guard(action, "created_by_id")};
          SELECT RAISE(ABORT,'research theme archive pair') WHERE (NEW.archived_at IS NULL)<>(NEW.archived_by_id IS NULL);
          SELECT RAISE(ABORT,'research theme archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND {_sqlite_actor_guard(action, "archived_by_id")};
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_theme_codes_scope_{suffix} BEFORE {action} ON research_theme_codes BEGIN
          SELECT RAISE(ABORT,'theme code study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'theme code theme scope') WHERE NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'theme code code scope') WHERE NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'theme code researcher scope') WHERE {_sqlite_actor_guard(action, "linked_by_id")};
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_analysis_canvases_scope_{suffix} BEFORE {action} ON analysis_canvases BEGIN
          SELECT RAISE(ABORT,'analysis canvas study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'analysis canvas owner scope') WHERE {_sqlite_actor_guard(action, "owner_id")};
        END
        """)
        op.execute(f"""
        CREATE TRIGGER trg_research_findings_scope_{suffix} BEFORE {action} ON research_findings BEGIN
          SELECT RAISE(ABORT,'research finding study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
          SELECT RAISE(ABORT,'research finding creator scope') WHERE {_sqlite_actor_guard(action, "created_by_id")};
          SELECT RAISE(ABORT,'research finding archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND {_sqlite_actor_guard(action, "archived_by_id")};
          SELECT RAISE(ABORT,'research finding suggestion scope') WHERE NEW.originating_suggestion_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_analysis_suggestions WHERE id=NEW.originating_suggestion_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
        END
        """)


def upgrade() -> None:
    # Some historical migration rehearsals intentionally stamp a deliberately
    # partial schema. There is no actor scope to update until the membership
    # table exists; complete released and fresh schemas always include it.
    if "organisation_memberships" not in sa.inspect(op.get_bind()).get_table_names():
        return
    _drop_actor_guards()
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS analysis_actor_has_active_organisation_membership(integer, integer)"
        )
        _create_postgresql_guards()
    else:
        _create_sqlite_guards()


def downgrade() -> None:
    if "organisation_memberships" not in sa.inspect(op.get_bind()).get_table_names():
        return
    _drop_actor_guards()

    # Restore the exact guards supplied by the revisions immediately below
    # this one. Migration modules are already the repository's canonical
    # fresh-schema definitions for those guards.
    target = importlib.import_module("migrations.versions.0025_analysis_targets")
    if op.get_bind().dialect.name == "postgresql":
        target._postgres_scope_trigger()
    else:
        target._sqlite_scope_triggers()

    codebook = importlib.import_module("migrations.versions.0026_research_codebook")
    codebook._install_triggers()
    importlib.import_module("migrations.versions.0027_code_applications")._triggers()
    importlib.import_module(
        "migrations.versions.0028_research_annotations"
    )._create_guards()
    importlib.import_module("migrations.versions.0029_research_memos")._create_guards()
    importlib.import_module(
        "migrations.versions.0031_theme_development"
    )._create_guards()
    canvas = importlib.import_module("migrations.versions.0032_analysis_canvas")
    canvas._drop_guards()
    canvas._create_guards()

    findings = importlib.import_module("migrations.versions.0033_research_findings")
    findings._drop_guards()
    findings._create_guards()
    finding_provenance = importlib.import_module(
        "migrations.versions.0034_ai_suggestion_finding_provenance"
    )
    finding_provenance._drop_guard()
    finding_provenance._create_guard(provenance=True)

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP FUNCTION IF EXISTS analysis_actor_has_active_organisation_membership(integer, integer)"
        )
