from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvidenceFile


def build_evidence_file(
    organisation_id: int,
    study_id: int,
    activity_id: int,
    participant_id: int,
    response_id: int | None,
    original_name: str,
    stored_name: str,
    content_type: str,
    size_bytes: int,
    sha256_hex: str,
    scan_status: str,
    scan_detail: str,
    storage_provider: str,
    blob_uri: str,
) -> EvidenceFile:
    return EvidenceFile(
        organisation_id=organisation_id,
        study_id=study_id,
        activity_id=activity_id,
        participant_id=participant_id,
        response_id=response_id,
        original_name=original_name,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256_hex=sha256_hex,
        scan_status=scan_status,
        scan_detail=scan_detail,
        storage_provider=storage_provider,
        blob_uri=blob_uri,
    )


def resolve_org_scoped_evidence(
    db: Session,
    organisation_id: int,
    evidence_id: int,
) -> EvidenceFile | None:
    return db.scalar(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_id,
            EvidenceFile.organisation_id == organisation_id,
        )
    )


def is_evidence_downloadable(scan_status: str | None) -> bool:
    token = (scan_status or "").strip().lower().replace(" ", "_")
    mapping = {
        "scan_failed": "failed",
        "not_scanned": "not_scanned",
    }
    return mapping.get(token, token) == "clean"
