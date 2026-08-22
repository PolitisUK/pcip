"""Safe, idempotent import for the authored Rivermere v1.1 demo pack.

The JSON files beside this module are the source of truth.  They are content,
not a database dump: this importer deliberately maps them to the platform's
existing organisation, project, study, activity, participant, response,
evidence and researcher-theme models.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityResponse,
    AuditEvent,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Organisation,
    OrganisationMembership,
    Participant,
    ParticipantInvitation,
    ParticipantMessage,
    Project,
    PublicAuthSession,
    ResearchAnalysisSuggestion,
    ResearchTheme,
    Study,
    StudyAccess,
    StudyEnrolment,
    StudyGovernance,
    StudyMethodologyConfiguration,
    User,
)

RIVERMERE_SLUG = "rivermere-town-council"
RIVERMERE_NAME = "Rivermere Town Council"
EVERYDAY_PROJECT_CODE = "RIV-2035"
EVERYDAY_STUDY_CODE = "RIV2035-ETH"
CHAPEL_PROJECT_CODE = "RIV-CHAPEL-LANE"
CHAPEL_STUDY_CODE = "RIV-CHAPEL-LANE-ETH"
CONTENT_VERSION = "1.1.0"
CONTENT_ROOT = Path(__file__).with_name("content")
SAFE_ENVIRONMENTS = {"development", "dev", "test", "testing"}
LEGACY_RIVERMERE_SLUG = "rivermere-town-council-demo"
LEGACY_RIVERMERE_NAME = "Rivermere Town Council (Fictional Demo)"
LEGACY_PROJECT_CODES = {EVERYDAY_PROJECT_CODE, "RIV-CHAPEL"}


class UnsafeDemoTarget(RuntimeError):
    """Raised before a command can modify an unsuitable target."""


@dataclass
class SeedCounts:
    projects: int = 0
    studies: int = 0
    participants: int = 0
    enrolments: int = 0
    prompts: int = 0
    entries: int = 0
    media: int = 0
    code_assignments: int = 0
    memos: int = 0
    memberships: int = 0
    created_project_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _content_file(name: str) -> Path:
    path = CONTENT_ROOT / name
    if not path.is_file():
        raise RuntimeError(f"Missing bundled Rivermere v{CONTENT_VERSION} source file: {path.name}")
    return path


def _load_json(name: str) -> dict[str, Any]:
    with _content_file(name).open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise TypeError(f"Rivermere source file {name} must contain an object.")
    return value


def rivermere_datasets() -> dict[str, dict[str, Any]]:
    datasets = {
        EVERYDAY_PROJECT_CODE: _load_json("rivermere_2035.v1_1.json"),
        CHAPEL_PROJECT_CODE: _load_json("chapel_lane.v1_1.json"),
    }
    for code, dataset in datasets.items():
        if dataset.get("dataset_version") != CONTENT_VERSION or dataset.get("fictional_demo") is not True:
            raise RuntimeError(f"Rivermere {code} is not the expected fictional v{CONTENT_VERSION} content.")
        if dataset.get("project", {}).get("code") != code:
            raise RuntimeError(f"Rivermere project source is not mapped to {code}.")
        if dataset.get("organisation", {}).get("slug") != RIVERMERE_SLUG:
            raise RuntimeError("Both Rivermere sources must use the designated fictional organisation.")
    return datasets


def quality_report() -> dict[str, Any]:
    return _load_json("quality_report.v1_1.json")


def cross_project_analysis() -> dict[str, Any]:
    return _load_json("cross_project_analysis.v1_1.json")


def assert_safe_demo_target(
    *, database_url: str, environment: str, storage_backend: str, storage_path: str,
    repo_root: Path, allow_nonlocal: bool = False,
) -> tuple[Path | None, Path | None]:
    """Require checkout-local SQLite by default; nonlocal use is explicit only."""
    env = environment.strip().lower()
    if env not in SAFE_ENVIRONMENTS and not allow_nonlocal:
        raise UnsafeDemoTarget("Rivermere seeding refuses staging and production unless explicitly confirmed.")
    parsed = urlsplit(database_url.strip())
    if allow_nonlocal:
        if not database_url.strip() or not storage_backend.strip():
            raise UnsafeDemoTarget("A configured database and storage backend are required for an explicit nonlocal demo import.")
        return None, None
    if env not in SAFE_ENVIRONMENTS:
        raise UnsafeDemoTarget("Rivermere seeding requires an explicit development or test environment.")
    if parsed.scheme.lower() != "sqlite" or parsed.netloc:
        raise UnsafeDemoTarget("Rivermere local seeding requires a file-backed local SQLite database.")
    if storage_backend.strip().lower() != "local":
        raise UnsafeDemoTarget("Rivermere local seeding requires local evidence storage.")
    raw_database_path = database_url.removeprefix("sqlite:///")
    if not raw_database_path or raw_database_path == ":memory:":
        raise UnsafeDemoTarget("Rivermere seeding requires a file-backed local SQLite database.")
    root = repo_root.resolve()
    database_path = (root / raw_database_path).resolve() if not Path(raw_database_path).is_absolute() else Path(raw_database_path).resolve()
    evidence_path = (root / storage_path).resolve() if not Path(storage_path).is_absolute() else Path(storage_path).resolve()
    if root not in database_path.parents or root not in evidence_path.parents:
        raise UnsafeDemoTarget("Database and evidence storage must both resolve inside the current checkout.")
    if database_path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise UnsafeDemoTarget("Configured SQLite target does not have an expected local database suffix.")
    return database_path, evidence_path


def _find_or_create_organisation(db: Session, slug: str, *, create: bool) -> Organisation:
    if slug != RIVERMERE_SLUG:
        raise UnsafeDemoTarget("The Rivermere importer is restricted to its designated fictional organisation slug.")
    organisation = db.scalar(select(Organisation).where(Organisation.slug == slug))
    if organisation:
        if organisation.name != RIVERMERE_NAME:
            raise UnsafeDemoTarget("The designated Rivermere slug is already owned by a non-demo organisation.")
        return organisation
    if not create:
        raise UnsafeDemoTarget("The designated fictional Rivermere organisation must already exist outside local development.")
    organisation = Organisation(name=RIVERMERE_NAME, slug=slug, created_at=_parse_datetime("2025-08-01T09:00:00Z"))
    db.add(organisation)
    db.flush()
    return organisation


def _ensure_operator(db: Session, organisation: Organisation, counts: SeedCounts, *, create: bool) -> User:
    email = "rivermere-demo-researcher@participants.rivermere.demo.invalid"
    operator = db.scalar(select(User).where(func.lower(User.email) == email))
    if not operator:
        if not create:
            raise UnsafeDemoTarget("A Rivermere demo researcher must already exist outside local development.")
        operator = User(
            organisation_id=organisation.id, name="Rivermere Demo Researcher", email=email,
            password_hash=None, role="owner", is_active=True,
        )
        db.add(operator)
        db.flush()
    membership = db.scalar(select(OrganisationMembership).where(
        OrganisationMembership.user_id == operator.id,
        OrganisationMembership.organisation_id == organisation.id,
    ))
    if not membership:
        db.add(OrganisationMembership(user_id=operator.id, organisation_id=organisation.id, role="owner", is_active=True))
        counts.memberships += 1
    return operator


def _get_or_create_project(db: Session, organisation_id: int, user_id: int, data: dict[str, Any], counts: SeedCounts) -> Project:
    project_data = data["project"]
    code = project_data["code"]
    project = db.scalar(select(Project).where(Project.organisation_id == organisation_id, Project.code == code))
    if project:
        return project
    project = Project(
        organisation_id=organisation_id, created_by_id=user_id, code=code,
        title=project_data["title"], description=project_data["description"], status="live",
    )
    db.add(project)
    db.flush()
    counts.projects += 1
    counts.created_project_codes.append(code)
    return project


def _study_code(project_code: str) -> str:
    return EVERYDAY_STUDY_CODE if project_code == EVERYDAY_PROJECT_CODE else CHAPEL_STUDY_CODE


def _get_or_create_study(db: Session, organisation_id: int, user_id: int, project: Project, data: dict[str, Any], counts: SeedCounts) -> Study:
    project_data = data["project"]
    code = _study_code(project_data["code"])
    study = db.scalar(select(Study).where(Study.organisation_id == organisation_id, Study.code == code))
    if study:
        return study
    timeline = project_data["timeline"]
    start = _parse_datetime(f"{timeline['start']}T00:00:00Z")
    end = _parse_datetime(f"{timeline['end']}T23:59:59Z")
    study = Study(
        organisation_id=organisation_id, project_id=project.id, created_by_id=user_id, code=code,
        title=project_data["title"], description=project_data["description"], methodology=project_data["methodology"],
        status="closed", start_at=start, end_at=end,
        demographics_schema_json=json.dumps(["age", "relationship_to_place", "routine", "voice", "starting_position", "trajectory"]),
        created_at=start, updated_at=end,
    )
    db.add(study)
    db.flush()
    db.add(StudyMethodologyConfiguration(
        organisation_id=organisation_id, study_id=study.id, primary_methodology_id="M03",
        methodology_variant=project_data["methodology"], secondary_methodologies_json=json.dumps(["longitudinal diary", "photo elicitation"]),
        research_questions="Fictional demonstration of situated civic experience over time; not a measure of prevalence or legal fact.",
        protocol_reference="RIVERMERE-DEMO-V1.1 (fictional demonstration only)", protocol_version=CONTENT_VERSION,
        sampling_approach="Authored fictional maximum-variation demonstration sample.",
        data_collection_plan="Retrospective fictional diary and media-manifest entries. Prompts do not direct reporting or monitoring.",
        ai_enabled=False, allowed_ai_tasks_json="[]", human_review_required=True, library_version="1.0.0",
        researcher_notes="Codes and analytical memos are researcher-authored v1.1 demo material. No AI output or completed AI job is represented.",
        researcher_confirmed_by_id=user_id, researcher_confirmed_at=start,
    ))
    counts.studies += 1
    return study


def _participants(db: Session, organisation_id: int, user_id: int, study: Study, data: dict[str, Any], counts: SeedCounts) -> dict[str, Participant]:
    rows: dict[str, Participant] = {}
    for source in data["participants"]:
        reference = source["reference"]
        participant = db.scalar(select(Participant).where(Participant.organisation_id == organisation_id, Participant.reference == reference))
        if not participant:
            demographics = {key: value for key, value in source.items() if key not in {"reference", "name"}}
            participant = Participant(
                organisation_id=organisation_id, reference=reference, name=source["name"],
                email=f"{reference.lower()}@participants.rivermere.demo.invalid", status="completed", consent_status="granted",
                communication_preference="none", tags=f"fictional-demo,rivermere-v{CONTENT_VERSION},{study.code}",
                demographics_json=json.dumps(demographics, ensure_ascii=False),
                notes="Entirely fictional demo participant; each entry and media manifest is their own authored contribution.",
                created_by_id=user_id, created_at=study.start_at, updated_at=study.end_at,
            )
            db.add(participant)
            db.flush()
            counts.participants += 1
        enrolment = db.scalar(select(StudyEnrolment).where(StudyEnrolment.study_id == study.id, StudyEnrolment.participant_id == participant.id))
        if not enrolment:
            db.add(StudyEnrolment(organisation_id=organisation_id, study_id=study.id, participant_id=participant.id, status="completed", enrolled_at=study.start_at))
            counts.enrolments += 1
        rows[reference] = participant
    return rows


def _activities(db: Session, organisation_id: int, study: Study, data: dict[str, Any], counts: SeedCounts) -> dict[str, list[Activity]]:
    rows: dict[str, list[Activity]] = {}
    prompts = data["prompts"]
    total_days = max(1, (study.end_at - study.start_at).days)
    repeat_counts: dict[str, int] = {}
    participant_prompt_counts: dict[tuple[str, str], int] = {}
    for entry in data["entries"]:
        pair = (entry["participant"], entry["prompt"])
        participant_prompt_counts[pair] = participant_prompt_counts.get(pair, 0) + 1
    for (_, prompt_id), count in participant_prompt_counts.items():
        repeat_counts[prompt_id] = repeat_counts.get(prompt_id, 0) + max(0, count - 1)
    position = 0
    for index, source in enumerate(prompts, start=1):
        title = source.get("title") or f"Week {source.get('week', index)}"
        rows[source["id"]] = []
        for instance in range(1, repeat_counts.get(source["id"], 0) + 2):
            position += 1
            activity = db.scalar(select(Activity).where(Activity.organisation_id == organisation_id, Activity.study_id == study.id, Activity.position == position))
            if not activity:
                activity = Activity(
                    organisation_id=organisation_id, study_id=study.id,
                    title=title if instance == 1 else f"{title} · additional reflection {instance - 1}", prompt=source["prompt"],
                    activity_type="long_text", options_json=json.dumps({"source_prompt_id": source["id"], "source_prompt_instance": instance, "fictional_demo": True}),
                    position=position, required=False, release_offset_days=(index - 1) * total_days // len(prompts),
                    due_offset_days=index * total_days // len(prompts), created_at=study.start_at,
                )
                db.add(activity)
                db.flush()
                # The content-pack count is distinct authored prompts.  An extra
                # task instance is only needed where the schema's one-response
                # constraint would otherwise discard a second dated entry.
                if instance == 1:
                    counts.prompts += 1
            rows[source["id"]].append(activity)
    return rows


def _response_payload(source: dict[str, Any], manifest_ids: list[str]) -> dict[str, Any]:
    codes = source["codes"]
    return {
        "text": source["text"], "source_entry_id": source["id"], "source_prompt_id": source["prompt"],
        "observed_at": source["date"], "trajectory_stage": f"phase_{source.get('phase', source.get('week'))}",
        "researcher_codes": codes, "coding_assignments": [{"scope": "entry", "code": code} for code in codes],
        "media_manifest_ids": manifest_ids, "fictional_demo": True,
        "analysis_note": "Researcher-authored response-level coding from Rivermere v1.1; no AI analysis is claimed.",
    }


def _responses(
    db: Session, organisation_id: int, study: Study, data: dict[str, Any], participants: dict[str, Participant],
    activities: dict[str, list[Activity]], counts: SeedCounts,
) -> dict[str, ActivityResponse]:
    manifest_by_entry: dict[str, list[str]] = {}
    for media in data["media_manifest"]:
        manifest_by_entry.setdefault(media["entry"], []).append(media["id"])
    rows: dict[str, ActivityResponse] = {}
    instances: dict[tuple[str, str], int] = {}
    for source in data["entries"]:
        participant = participants[source["participant"]]
        pair = (source["participant"], source["prompt"])
        instance = instances.get(pair, 0)
        activity = activities[source["prompt"]][instance]
        instances[pair] = instance + 1
        response = db.scalar(select(ActivityResponse).where(ActivityResponse.activity_id == activity.id, ActivityResponse.participant_id == participant.id))
        if not response:
            observed_at = _parse_datetime(source["date"])
            response = ActivityResponse(
                organisation_id=organisation_id, study_id=study.id, activity_id=activity.id, participant_id=participant.id,
                value_json=json.dumps(_response_payload(source, manifest_by_entry.get(source["id"], [])), ensure_ascii=False),
                status="submitted", submitted_at=observed_at, updated_at=observed_at,
            )
            db.add(response)
            db.flush()
            counts.entries += 1
            counts.code_assignments += len(source["codes"])
        rows[source["id"]] = response
    return rows


def _manifest_bytes(project_code: str, source: dict[str, Any]) -> bytes:
    payload = {
        "classification": "FICTIONAL DEMONSTRATION MEDIA MANIFEST — NOT A REAL IMAGE, COUNCIL RECORD OR EXTERNAL URL",
        "project_code": project_code,
        "manifest": source,
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _save_evidence(db: Session, storage, *, organisation_id: int, study: Study, response: ActivityResponse, source: dict[str, Any], counts: SeedCounts) -> None:
    existing = db.scalar(select(EvidenceFile).where(
        EvidenceFile.organisation_id == organisation_id, EvidenceFile.study_id == study.id,
        EvidenceFile.response_id == response.id, EvidenceFile.original_name == f"{source['id']}.manifest.json",
    ))
    if existing:
        return
    stream: BinaryIO = io.BytesIO(_manifest_bytes(_project_code_for_study(study.code), source))
    stored = storage.save_stream(stream, f"{source['id']}.manifest.json", 25 * 1024 * 1024)
    db.add(EvidenceFile(
        organisation_id=organisation_id, study_id=study.id, activity_id=response.activity_id, participant_id=response.participant_id,
        response_id=response.id, original_name=f"{source['id']}.manifest.json", stored_name=stored.key,
        content_type="application/json", size_bytes=stored.size, sha256_hex=stored.sha256_hex, scan_status="clean",
        scan_detail="Fictional v1.1 media specification only; no generated image, external URL or council document is claimed.",
        storage_provider=stored.provider, blob_uri=stored.uri, scan_completed_at=response.submitted_at, created_at=response.submitted_at,
    ))
    counts.media += 1


def _project_code_for_study(study_code: str) -> str:
    return EVERYDAY_PROJECT_CODE if study_code == EVERYDAY_STUDY_CODE else CHAPEL_PROJECT_CODE


def _media(db: Session, storage, organisation_id: int, study: Study, data: dict[str, Any], responses: dict[str, ActivityResponse], counts: SeedCounts) -> None:
    for source in data["media_manifest"]:
        _save_evidence(db, storage, organisation_id=organisation_id, study=study, response=responses[source["entry"]], source=source, counts=counts)


def _memos(db: Session, organisation_id: int, user_id: int, study: Study, data: dict[str, Any], counts: SeedCounts) -> None:
    for source in data["memos"]:
        existing = db.scalar(select(ResearchTheme).where(
            ResearchTheme.organisation_id == organisation_id, ResearchTheme.study_id == study.id, ResearchTheme.name == source["title"],
        ))
        if existing:
            continue
        db.add(ResearchTheme(
            organisation_id=organisation_id, study_id=study.id, name=source["title"], description=source["text"],
            source_suggestion_ids_json=json.dumps([]), status="researcher_draft", created_by_id=user_id,
            created_at=study.end_at, updated_at=study.end_at,
        ))
        counts.memos += 1


def seed_rivermere(
    db: Session, storage, *, organisation_slug: str = RIVERMERE_SLUG, create_organisation: bool = True,
) -> SeedCounts:
    """Create the exact v1.1 data once; a repeat call only verifies existing rows."""
    datasets = rivermere_datasets()
    counts = SeedCounts()
    organisation = _find_or_create_organisation(db, organisation_slug, create=create_organisation)
    operator = _ensure_operator(db, organisation, counts, create=create_organisation)
    for code in (EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE):
        data = datasets[code]
        project = _get_or_create_project(db, organisation.id, operator.id, data, counts)
        study = _get_or_create_study(db, organisation.id, operator.id, project, data, counts)
        participants = _participants(db, organisation.id, operator.id, study, data, counts)
        activities = _activities(db, organisation.id, study, data, counts)
        responses = _responses(db, organisation.id, study, data, participants, activities, counts)
        _media(db, storage, organisation.id, study, data, responses, counts)
        _memos(db, organisation.id, operator.id, study, data, counts)
    db.add(AuditEvent(
        organisation_id=organisation.id, actor_user_id=operator.id, action="demo.rivermere.v1_1.seeded", entity_type="organisation",
        entity_id=str(organisation.id), detail=f"fictional_demo=true content_version={CONTENT_VERSION} {json.dumps(counts.as_dict(), sort_keys=True)}",
    ))
    db.commit()
    return counts


def project_analysis_manifest(project_code: str) -> dict[str, Any]:
    datasets = rivermere_datasets()
    if project_code not in datasets:
        raise ValueError("Unknown Rivermere project code")
    data = datasets[project_code]
    return {
        "project_code": project_code, "content_version": CONTENT_VERSION, "codebook": data["codebook"], "memos": data["memos"],
        "cross_project_analysis": cross_project_analysis(), "ai_analysis_records": 0,
    }


def verify_rivermere(db: Session, *, organisation_slug: str = RIVERMERE_SLUG) -> dict[str, Any]:
    """Read-only verification against the bundled v1.1 source pack."""
    datasets = rivermere_datasets()
    result: dict[str, Any] = {"valid": True, "projects": {}, "errors": []}
    organisation = db.scalar(select(Organisation).where(Organisation.slug == organisation_slug))
    if not organisation or organisation.name != RIVERMERE_NAME:
        return {"valid": False, "projects": {}, "errors": ["designated fictional organisation is missing or has an unexpected name"]}
    for code, data in datasets.items():
        errors: list[str] = []
        project = db.scalar(select(Project).where(Project.organisation_id == organisation.id, Project.code == code))
        if not project:
            result["projects"][code] = {"valid": False, "errors": ["project missing"]}
            result["valid"] = False
            continue
        study = db.scalar(select(Study).where(Study.project_id == project.id, Study.code == _study_code(code)))
        if not study:
            result["projects"][code] = {"valid": False, "errors": ["study missing"]}
            result["valid"] = False
            continue
        responses = db.scalars(select(ActivityResponse).where(ActivityResponse.study_id == study.id)).all()
        payloads = [_response_payload_row(row) for row in responses]
        source_entries = {entry["id"]: entry for entry in data["entries"]}
        response_entry_ids = {payload.get("source_entry_id") for payload in payloads}
        source_prompt_ids = {
            json.loads(row.options_json).get("source_prompt_id")
            for row in db.scalars(select(Activity).where(Activity.study_id == study.id))
        }
        participants = int(db.scalar(select(func.count(func.distinct(StudyEnrolment.participant_id))).where(StudyEnrolment.study_id == study.id)) or 0)
        evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.study_id == study.id)).all()
        memos = db.scalars(select(ResearchTheme).where(ResearchTheme.study_id == study.id)).all()
        if participants != len(data["participants"]): errors.append("participant count mismatch")
        if source_prompt_ids != {prompt["id"] for prompt in data["prompts"]}: errors.append("prompt mapping mismatch")
        if response_entry_ids != set(source_entries) or len(responses) != len(source_entries): errors.append("entry mapping mismatch")
        if sum(len(payload.get("coding_assignments", [])) for payload in payloads) != sum(len(entry["codes"]) for entry in data["entries"]): errors.append("coding assignment count mismatch")
        if {row.original_name for row in evidence} != {f"{item['id']}.manifest.json" for item in data["media_manifest"]}: errors.append("media manifest mismatch")
        if any(row.response_id is None or row.scan_status != "clean" or not row.stored_name for row in evidence): errors.append("media reference is incomplete")
        if {row.name for row in memos} != {memo["title"] for memo in data["memos"]}: errors.append("analytical memo mismatch")
        result["projects"][code] = {
            "valid": not errors, "participants": participants, "prompts": len(source_prompt_ids), "tasks": int(db.scalar(select(func.count(Activity.id)).where(Activity.study_id == study.id)) or 0),
            "entries": len(responses), "media": len(evidence), "memos": len(memos), "errors": errors,
        }
        if errors:
            result["valid"] = False
            result["errors"].extend(f"{code}: {error}" for error in errors)
    return result


def _response_payload_row(row: ActivityResponse) -> dict[str, Any]:
    try:
        value = json.loads(row.value_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _project_graph_delete(db: Session, storage, organisation_id: int, project: Project) -> tuple[int, int, int]:
    studies = db.scalars(select(Study).where(Study.organisation_id == organisation_id, Study.project_id == project.id)).all()
    study_ids = [study.id for study in studies]
    media_rows = db.scalars(select(EvidenceFile).where(EvidenceFile.organisation_id == organisation_id, EvidenceFile.study_id.in_(study_ids))).all() if study_ids else []
    for evidence in media_rows:
        storage.delete(evidence.stored_name)
    participant_ids = db.scalars(select(StudyEnrolment.participant_id).where(StudyEnrolment.study_id.in_(study_ids))).all() if study_ids else []
    if study_ids:
        invitation_ids = db.scalars(select(ParticipantInvitation.id).where(ParticipantInvitation.study_id.in_(study_ids))).all()
        if invitation_ids:
            db.execute(delete(PublicAuthSession).where(PublicAuthSession.participant_invitation_id.in_(invitation_ids)))
        for model in (EvidenceConfidenceAssessment, ResearchTheme, ResearchAnalysisSuggestion, EvidenceFile, ParticipantMessage,
                      ParticipantInvitation, ActivityResponse, StudyAccess, StudyMethodologyConfiguration, StudyGovernance,
                      StudyEnrolment, Activity):
            db.execute(delete(model).where(model.study_id.in_(study_ids)))
        db.execute(delete(Study).where(Study.id.in_(study_ids)))
    db.delete(project)
    db.flush()
    removed_participants = 0
    for participant_id in set(participant_ids):
        enrolled_elsewhere = db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.participant_id == participant_id))
        participant = db.get(Participant, participant_id)
        if participant and not enrolled_elsewhere and f"rivermere-v{CONTENT_VERSION}" in participant.tags:
            db.delete(participant)
            removed_participants += 1
    return len(studies), removed_participants, len(media_rows)


def replace_superseded_rivermere_demo(db: Session, storage) -> dict[str, int]:
    """Remove only the precisely identified pre-v1.1 fictional import.

    This is intentionally narrower than the normal project cleanup.  It can
    remove the two known legacy projects without touching another participant
    or user that happens to belong to the old demonstration organisation.
    """
    organisation = db.scalar(select(Organisation).where(Organisation.slug == LEGACY_RIVERMERE_SLUG))
    if not organisation:
        return {"organisations": 0, "projects": 0, "participants": 0, "media": 0}
    projects = db.scalars(select(Project).where(Project.organisation_id == organisation.id)).all()
    if not projects:
        return {"organisations": 0, "projects": 0, "participants": 0, "media": 0}
    primary_users = db.scalars(select(User).where(User.organisation_id == organisation.id)).all()
    if (
        organisation.name != LEGACY_RIVERMERE_NAME
        or {project.code for project in projects} != LEGACY_PROJECT_CODES
    ):
        raise UnsafeDemoTarget("A legacy Rivermere organisation was found but is not safe to replace automatically.")
    removed_projects = removed_participants = removed_media = 0
    for project in projects:
        _, participant_count, media_count = _project_graph_delete(db, storage, organisation.id, project)
        removed_projects += 1
        removed_participants += participant_count
        removed_media += media_count
    for participant in db.scalars(select(Participant).where(Participant.organisation_id == organisation.id)).all():
        if "fictional-demo" in participant.tags and not db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.participant_id == participant.id)):
            db.delete(participant)
            removed_participants += 1
    remaining_participants = db.scalar(select(func.count(Participant.id)).where(Participant.organisation_id == organisation.id)) or 0
    if not primary_users and not remaining_participants:
        db.execute(delete(OrganisationMembership).where(OrganisationMembership.organisation_id == organisation.id))
        db.delete(organisation)
        removed_organisations = 1
    else:
        removed_organisations = 0
    db.flush()
    return {"organisations": removed_organisations, "projects": removed_projects, "participants": removed_participants, "media": removed_media}


def remove_rivermere_project(db: Session, storage, project_code: str, *, organisation_slug: str = RIVERMERE_SLUG) -> dict[str, int]:
    """Delete exactly one known v1.1 project and its owned fictional records."""
    if project_code not in {EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE}:
        raise ValueError("Cleanup is restricted to a known Rivermere v1.1 project code.")
    if organisation_slug != RIVERMERE_SLUG:
        raise UnsafeDemoTarget("Cleanup is restricted to the designated fictional Rivermere organisation.")
    organisation = db.scalar(select(Organisation).where(Organisation.slug == organisation_slug))
    if not organisation:
        return {"projects": 0, "studies": 0, "participants": 0, "media": 0}
    project = db.scalar(select(Project).where(Project.organisation_id == organisation.id, Project.code == project_code))
    if not project:
        return {"projects": 0, "studies": 0, "participants": 0, "media": 0}
    studies, participants, media = _project_graph_delete(db, storage, organisation.id, project)
    db.add(AuditEvent(
        organisation_id=organisation.id, actor_user_id=None, action="demo.rivermere.v1_1.project_removed",
        entity_type="project", entity_id=project_code, detail="Project-specific fictional demo cleanup completed.",
    ))
    db.commit()
    return {"projects": 1, "studies": studies, "participants": participants, "media": media}
