from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.demo_data.rivermere import (
    CHAPEL_MEMOS,
    CHAPEL_PROJECT_CODE,
    CHAPEL_STUDY_CODE,
    EVERYDAY_MEMOS,
    EVERYDAY_PROJECT_CODE,
    EVERYDAY_STUDY_CODE,
    UnsafeDemoTarget,
    assert_safe_demo_target,
    project_analysis_manifest,
    remove_rivermere_project,
    seed_rivermere,
)
from app.models import (
    Activity,
    ActivityResponse,
    EvidenceFile,
    Organisation,
    Participant,
    Project,
    Study,
    StudyEnrolment,
)
from app.storage import LocalStorage


@pytest.fixture
def rivermere_database(tmp_path):
    database_path = tmp_path / "rivermere-test.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    storage = LocalStorage(tmp_path / "uploads")
    yield factory, storage
    engine.dispose()


def _study(db, code):
    return db.scalar(select(Study).where(Study.code == code))


def _responses(db, study):
    return db.scalars(
        select(ActivityResponse)
        .where(ActivityResponse.study_id == study.id)
        .order_by(ActivityResponse.submitted_at, ActivityResponse.id)
    ).all()


def test_safety_gate_accepts_only_checkout_local_development(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    database, storage = assert_safe_demo_target(
        database_url="sqlite:///./data/app.db",
        environment="development",
        storage_backend="local",
        storage_path="./data/uploads",
        repo_root=repo,
    )
    assert database == repo / "data" / "app.db"
    assert storage == repo / "data" / "uploads"

    unsafe = [
        {"database_url": "postgresql://prod.example/civic", "environment": "development", "storage_backend": "local", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:///./data/app.db", "environment": "production", "storage_backend": "local", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:///./data/app.db", "environment": "development", "storage_backend": "azure_blob", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:////var/tmp/outside.db", "environment": "development", "storage_backend": "local", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:///./data/app.db", "environment": "development", "storage_backend": "local", "storage_path": "/var/tmp/uploads"},
    ]
    for values in unsafe:
        with pytest.raises(UnsafeDemoTarget):
            assert_safe_demo_target(repo_root=repo, **values)


def test_seed_is_idempotent_and_matches_requested_scale(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        first = seed_rivermere(db, storage)
        assert first.projects == 2
        assert first.studies == 2
        assert first.participants == 34
        assert first.prompts == 28
        assert first.entries == 252
        assert first.media == 84
        assert first.code_assignments > 700

    with factory() as db:
        second = seed_rivermere(db, storage)
        assert second.projects == 0
        assert second.studies == 0
        assert second.participants == 0
        assert second.prompts == 0
        assert second.entries == 0
        assert second.media == 0
        assert db.scalar(select(func.count(Project.id)).where(Project.code.in_([EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE]))) == 2

        everyday = _study(db, EVERYDAY_STUDY_CODE)
        chapel = _study(db, CHAPEL_STUDY_CODE)
        assert everyday.status == "closed"
        assert chapel.status == "closed"
        assert db.scalar(select(func.count(Activity.id)).where(Activity.study_id == everyday.id)) == 16
        assert db.scalar(select(func.count(Activity.id)).where(Activity.study_id == chapel.id)) == 12
        assert db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.study_id == everyday.id)) == 20
        assert db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.study_id == chapel.id)) == 14
        assert len(_responses(db, everyday)) == 112
        assert len(_responses(db, chapel)) == 140
        assert db.scalar(select(func.count(EvidenceFile.id)).where(EvidenceFile.study_id == everyday.id)) == 36
        assert db.scalar(select(func.count(EvidenceFile.id)).where(EvidenceFile.study_id == chapel.id)) == 48


def test_entries_are_dated_coded_contextual_and_keep_chapel_trajectory(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        everyday = _study(db, EVERYDAY_STUDY_CODE)
        chapel = _study(db, CHAPEL_STUDY_CODE)
        everyday_rows = _responses(db, everyday)
        chapel_rows = _responses(db, chapel)

        for row in [*everyday_rows, *chapel_rows]:
            payload = json.loads(row.value_json)
            assert payload["fictional_demo"] is True
            assert payload["observed_at"]
            assert payload["place"]
            assert len(payload["text"]) >= 450
            assert len(payload["researcher_codes"]) >= 2
            assert all(" > " in code for code in payload["researcher_codes"])
            assert row.participant_id
            assert row.submitted_at

        everyday_weeks = [
            db.get(Activity, row.activity_id).position for row in everyday_rows
        ]
        assert min(everyday_weeks) == 1
        assert max(everyday_weeks) == 16
        assert len(set(everyday_weeks)) == 16
        assert len({count for count in (everyday_weeks.count(week) for week in range(1, 17))}) > 1

        chapel_by_phase = {}
        for row in chapel_rows:
            payload = json.loads(row.value_json)
            chapel_by_phase.setdefault(payload["trajectory_stage"], []).append(payload["text"])
        expected = [
            "something_has_changed", "neighbours_compare_notes", "told_to_report", "active_reporting",
            "acknowledgement_and_waiting", "repetition_without_resolution", "evidence_burden",
            "frustration", "reporting_fatigue", "stopped_reporting", "normalisation_and_adaptation",
            "retrospective_reflection",
        ]
        assert list(chapel_by_phase) == expected
        assert any("route to action" in text for text in chapel_by_phase["told_to_report"])
        assert any("phone stayed on the kitchen table" in text for text in chapel_by_phase["reporting_fatigue"])
        assert any("stopped filing reports" in text for text in chapel_by_phase["stopped_reporting"])
        assert any("yard appeared no quieter" in text for text in chapel_by_phase["retrospective_reflection"])
        assert any("cannot see or claim" in json.loads(row.value_json)["text"] for row in chapel_rows)


def test_media_files_and_analysis_manifests_are_complete(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        media = db.scalars(select(EvidenceFile).order_by(EvidenceFile.id)).all()
        assert len(media) == 84
        assert sum(row.content_type == "image/jpeg" for row in media) == 4
        assert sum(row.content_type == "text/plain" for row in media) == 80
        for row in media:
            assert row.response_id is not None
            assert row.scan_status == "clean"
            assert storage.path(row.stored_name).is_file()
            assert storage.path(row.stored_name).stat().st_size == row.size_bytes

        everyday_manifest = project_analysis_manifest(EVERYDAY_PROJECT_CODE)
        chapel_manifest = project_analysis_manifest(CHAPEL_PROJECT_CODE)
        assert len(everyday_manifest["codebook"]) >= 25
        assert len(chapel_manifest["codebook"]) >= 30
        assert everyday_manifest["memos"] == EVERYDAY_MEMOS
        assert chapel_manifest["memos"] == CHAPEL_MEMOS
        assert everyday_manifest["ai_analysis_records"] == 0
        assert chapel_manifest["ai_analysis_records"] == 0


def test_cleanup_is_project_specific_and_leaves_no_orphans(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        result = remove_rivermere_project(db, storage, EVERYDAY_PROJECT_CODE)
        assert result == {"projects": 1, "studies": 1, "participants": 20, "media": 36}
        assert db.scalar(select(Project).where(Project.code == EVERYDAY_PROJECT_CODE)) is None
        assert db.scalar(select(Study).where(Study.code == EVERYDAY_STUDY_CODE)) is None
        assert db.scalar(select(Project).where(Project.code == CHAPEL_PROJECT_CODE)) is not None
        chapel = _study(db, CHAPEL_STUDY_CODE)
        assert len(_responses(db, chapel)) == 140
        assert db.scalar(select(func.count(Participant.id))) == 14
        assert db.scalar(select(func.count(EvidenceFile.id))) == 48
        assert len(list(Path(storage.root).iterdir())) == 48

        result = remove_rivermere_project(db, storage, CHAPEL_PROJECT_CODE)
        assert result == {"projects": 1, "studies": 1, "participants": 14, "media": 48}
        assert db.scalar(select(func.count(Project.id))) == 0
        assert db.scalar(select(func.count(Study.id))) == 0
        assert db.scalar(select(func.count(Participant.id))) == 0
        assert db.scalar(select(func.count(ActivityResponse.id))) == 0
        assert db.scalar(select(func.count(EvidenceFile.id))) == 0
        assert not list(Path(storage.root).iterdir())


def test_project_codes_exist_once_under_fictional_council(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        organisation = db.scalar(select(Organisation).where(Organisation.slug == "rivermere-town-council-demo"))
        assert organisation.name == "Rivermere Town Council (Fictional Demo)"
        rows = db.scalars(select(Project).where(Project.organisation_id == organisation.id).order_by(Project.code)).all()
        assert [row.code for row in rows] == [EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE]
