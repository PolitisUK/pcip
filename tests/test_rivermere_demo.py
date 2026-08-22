from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.demo_data.rivermere import (
    CHAPEL_PROJECT_CODE,
    CHAPEL_STUDY_CODE,
    EVERYDAY_PROJECT_CODE,
    EVERYDAY_STUDY_CODE,
    RIVERMERE_SLUG,
    UnsafeDemoTarget,
    assert_safe_demo_target,
    project_analysis_manifest,
    quality_report,
    remove_rivermere_project,
    rivermere_datasets,
    seed_rivermere,
    verify_rivermere,
)
from app.models import (
    Activity,
    ActivityResponse,
    EvidenceFile,
    Organisation,
    Participant,
    Project,
    ResearchTheme,
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


def _payload(response):
    return json.loads(response.value_json)


def test_safety_gate_accepts_only_checkout_local_development(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    database, storage = assert_safe_demo_target(
        database_url="sqlite:///./data/app.db", environment="development", storage_backend="local",
        storage_path="./data/uploads", repo_root=repo,
    )
    assert database == repo / "data" / "app.db"
    assert storage == repo / "data" / "uploads"

    for values in (
        {"database_url": "postgresql://prod.example/civic", "environment": "development", "storage_backend": "local", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:///./data/app.db", "environment": "production", "storage_backend": "local", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:///./data/app.db", "environment": "development", "storage_backend": "azure_blob", "storage_path": "./data/uploads"},
        {"database_url": "sqlite:////var/tmp/outside.db", "environment": "development", "storage_backend": "local", "storage_path": "./data/uploads"},
    ):
        with pytest.raises(UnsafeDemoTarget):
            assert_safe_demo_target(repo_root=repo, **values)
    result = assert_safe_demo_target(
        database_url="postgresql://staging.example/civic", environment="staging", storage_backend="azure_blob",
        storage_path="unused", repo_root=repo, allow_nonlocal=True,
    )
    assert result == (None, None)


def test_source_pack_is_the_corrected_v1_1_content_and_preserves_safeguards():
    datasets = rivermere_datasets()
    report = quality_report()
    assert {key: value["dataset_version"] for key, value in datasets.items()} == {
        EVERYDAY_PROJECT_CODE: "1.1.0", CHAPEL_PROJECT_CODE: "1.1.0",
    }
    for data in datasets.values():
        safeguards = data["project"]["research_safeguards"]
        assert safeguards["individual_authorship"]
        assert safeguards["no_proxy_submission"]
        assert safeguards["ordinary_routines_only"] if "ordinary_routines_only" in safeguards else safeguards["no_reporting_direction"]
        references = {participant["reference"] for participant in data["participants"]}
        prompts = {prompt["id"] for prompt in data["prompts"]}
        entries = {entry["id"]: entry for entry in data["entries"]}
        assert all(entry["participant"] in references and entry["prompt"] in prompts for entry in entries.values())
        assert all(media["entry"] in entries for media in data["media_manifest"])
        assert all(media["id"] in entries[media["entry"]]["media"] for media in data["media_manifest"])
        assert all("submit material for another participant" not in entry["text"].lower() for entry in entries.values())
    audit = report["methodological_integrity_audit"]
    assert audit["proxy_research_submissions"] == 0
    assert audit["pooled_private_complaint_records"] == 0
    assert audit["researcher_directed_site_monitoring"] == 0
    assert audit["participant_entries_with_forbidden_researcher_register"] == 0


def test_seed_is_idempotent_and_matches_the_corrected_pack(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        first = seed_rivermere(db, storage)
        assert first.as_dict() | {"created_project_codes": sorted(first.created_project_codes)} == {
            "projects": 2, "studies": 2, "participants": 34, "enrolments": 34, "prompts": 31,
            "entries": 220, "media": 85, "code_assignments": 944, "memos": 26, "memberships": 1,
            "created_project_codes": [EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE],
        }
    with factory() as db:
        second = seed_rivermere(db, storage)
        assert second.projects == second.studies == second.participants == second.prompts == second.entries == second.media == second.memos == 0
        assert db.scalar(select(func.count(Project.id)).where(Project.code.in_([EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE]))) == 2
        assert db.scalar(select(func.count(StudyEnrolment.id))) == 34
        assert db.scalar(select(func.count(ActivityResponse.id))) == 220
        assert db.scalar(select(func.count(EvidenceFile.id))) == 85
        assert db.scalar(select(func.count(ResearchTheme.id))) == 26
        verification = verify_rivermere(db)
        assert verification["valid"] is True
        assert verification["projects"][EVERYDAY_PROJECT_CODE]["entries"] == 100
        assert verification["projects"][CHAPEL_PROJECT_CODE]["entries"] == 120


def test_projects_map_source_entries_codes_media_and_memos_to_real_models(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        datasets = rivermere_datasets()
        for project_code, study_code in ((EVERYDAY_PROJECT_CODE, EVERYDAY_STUDY_CODE), (CHAPEL_PROJECT_CODE, CHAPEL_STUDY_CODE)):
            data = datasets[project_code]
            study = _study(db, study_code)
            responses = db.scalars(select(ActivityResponse).where(ActivityResponse.study_id == study.id).order_by(ActivityResponse.submitted_at)).all()
            assert len(responses) == len(data["entries"])
            source_prompt_ids = {
                json.loads(row.options_json)["source_prompt_id"]
                for row in db.scalars(select(Activity).where(Activity.study_id == study.id))
            }
            assert source_prompt_ids == {prompt["id"] for prompt in data["prompts"]}
            assert db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.study_id == study.id)) == len(data["participants"])
            assert db.scalar(select(func.count(EvidenceFile.id)).where(EvidenceFile.study_id == study.id)) == len(data["media_manifest"])
            assert db.scalar(select(func.count(ResearchTheme.id)).where(ResearchTheme.study_id == study.id)) == len(data["memos"])
            source_entries = {row["id"]: row for row in data["entries"]}
            assert sum(len(_payload(response)["coding_assignments"]) for response in responses) == sum(len(entry["codes"]) for entry in data["entries"])
            for response in responses:
                payload = _payload(response)
                source = source_entries[payload["source_entry_id"]]
                assert payload["text"] == source["text"]
                assert payload["researcher_codes"] == source["codes"]
                assert payload["source_prompt_id"] == source["prompt"]
                assert all(item["scope"] == "entry" for item in payload["coding_assignments"])
            for evidence in db.scalars(select(EvidenceFile).where(EvidenceFile.study_id == study.id)):
                assert evidence.response_id is not None
                assert evidence.content_type == "application/json"
                assert evidence.scan_status == "clean"
                assert storage.path(evidence.stored_name).is_file()
                assert json.loads(storage.path(evidence.stored_name).read_text())["classification"].startswith("FICTIONAL DEMONSTRATION MEDIA MANIFEST")
            manifest = project_analysis_manifest(project_code)
            assert manifest["codebook"] == data["codebook"]
            assert manifest["memos"] == data["memos"]
            assert manifest["ai_analysis_records"] == 0


def test_chapel_lane_source_shows_the_full_longitudinal_trajectory(rivermere_database):
    factory, storage = rivermere_database
    checkpoints = quality_report()["chapel_lane_longitudinal_verification"]
    with factory() as db:
        seed_rivermere(db, storage)
        study = _study(db, CHAPEL_STUDY_CODE)
        responses = {_payload(row)["source_entry_id"]: _payload(row)["text"].lower() for row in db.scalars(select(ActivityResponse).where(ActivityResponse.study_id == study.id))}
        assert all(entry_id in responses for ids in checkpoints.values() for entry_id in ids)
        assert "what felt different" in responses["CL-E001"]
        assert "nobody present had seen" in responses["CL-E013"]
        assert "what anyone did with it was up to them" in responses["CL-E025"]
        assert "filled in the form" in responses["CL-E037"]
        assert "usual thank-you email" in responses["CL-E049"]
        assert "not get another report" in responses["CL-E073"]
        assert "do not report them anymore" in responses["CL-E085"]
        assert "nothing outside feels different" in responses["CL-E097"]


def test_cleanup_is_project_specific_and_leaves_no_orphans(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        assert remove_rivermere_project(db, storage, EVERYDAY_PROJECT_CODE) == {"projects": 1, "studies": 1, "participants": 20, "media": 40}
        assert db.scalar(select(Project).where(Project.code == EVERYDAY_PROJECT_CODE)) is None
        assert db.scalar(select(Project).where(Project.code == CHAPEL_PROJECT_CODE)) is not None
        assert db.scalar(select(func.count(ActivityResponse.id))) == 120
        assert db.scalar(select(func.count(EvidenceFile.id))) == 45
        assert remove_rivermere_project(db, storage, CHAPEL_PROJECT_CODE) == {"projects": 1, "studies": 1, "participants": 14, "media": 45}
        assert db.scalar(select(func.count(Participant.id))) == 0
        assert db.scalar(select(func.count(ActivityResponse.id))) == 0
        assert db.scalar(select(func.count(EvidenceFile.id))) == 0
        assert not list(Path(storage.root).iterdir())


def test_designated_organisation_and_projects_exist_once(rivermere_database):
    factory, storage = rivermere_database
    with factory() as db:
        seed_rivermere(db, storage)
        organisation = db.scalar(select(Organisation).where(Organisation.slug == RIVERMERE_SLUG))
        assert organisation.name == "Rivermere Town Council"
        projects = db.scalars(select(Project).where(Project.organisation_id == organisation.id).order_by(Project.code)).all()
        assert [project.code for project in projects] == [EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE]
