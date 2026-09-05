"""Immutable study-specific consent document bundles.

Platform policies are deliberately not used here.  A controller supplies the
three study documents and each invitation receives an immutable binding to
their exact versions and contents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ParticipantInvitation,
    Study,
    StudyConsentBundle,
    StudyConsentBundleDocument,
    StudyConsentDocument,
    StudyGovernance,
)

DOCUMENT_TYPES = ("participant_information", "privacy_notice", "consent_text")
DOCUMENT_TITLES = {
    "participant_information": "Participant information",
    "privacy_notice": "Study privacy notice",
    "consent_text": "Consent statement",
}
DOCUMENT_METADATA_LIMITS = {
    "reference": 500,
    "version": 80,
    "effective_date": 30,
}
DOCUMENT_METADATA_LABELS = {
    "reference": "reference",
    "version": "version",
    "effective_date": "effective date",
}


@dataclass(frozen=True)
class BoundStudyDocument:
    document_type: str
    title: str
    version: str
    reference: str
    effective_date: str
    body: str
    content_sha256: str


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def document_digest(
    document_type: str, version: str, reference: str, effective_date: str, body: str
) -> str:
    return _digest(
        {
            "document_type": document_type,
            "version": version,
            "reference": reference,
            "effective_date": effective_date,
            "body": body,
        }
    )


def validate_document_metadata(metadata: dict[str, dict[str, str]]) -> None:
    """Validate controller-supplied document metadata before persistence.

    Blank values remain valid here because incomplete governance records are
    supported.  Completeness is checked separately when creating a bundle.
    """
    for document_type in DOCUMENT_TYPES:
        values = metadata[document_type]
        for field, maximum in DOCUMENT_METADATA_LIMITS.items():
            if len(values[field]) > maximum:
                raise ValueError(
                    f"{DOCUMENT_TITLES[document_type]} {DOCUMENT_METADATA_LABELS[field]} "
                    f"must be {maximum} characters or fewer."
                )


def governance_document_metadata(
    governance: StudyGovernance,
) -> dict[str, dict[str, str]]:
    return {
        document_type: {
            field: getattr(governance, f"{document_type}_{field}").strip()
            for field in DOCUMENT_METADATA_LIMITS
        }
        for document_type in DOCUMENT_TYPES
    }


def bundle_documents(
    db: Session, bundle_id: int | None
) -> tuple[BoundStudyDocument, ...]:
    if not bundle_id:
        return ()
    rows = db.execute(
        select(StudyConsentBundleDocument, StudyConsentDocument)
        .join(
            StudyConsentDocument,
            StudyConsentDocument.id == StudyConsentBundleDocument.document_id,
        )
        .where(StudyConsentBundleDocument.bundle_id == bundle_id)
    ).all()
    documents = {
        membership.document_type: BoundStudyDocument(
            document_type=document.document_type,
            title=document.title,
            version=document.version,
            reference=document.reference,
            effective_date=document.effective_date,
            body=document.body,
            content_sha256=document.content_sha256,
        )
        for membership, document in rows
    }
    return tuple(documents[item] for item in DOCUMENT_TYPES if item in documents)


def current_bundle_documents(
    db: Session, governance: StudyGovernance | None
) -> tuple[BoundStudyDocument, ...]:
    return bundle_documents(
        db, governance.current_consent_bundle_id if governance else None
    )


def has_complete_bundle(db: Session, governance: StudyGovernance | None) -> bool:
    return len(current_bundle_documents(db, governance)) == len(DOCUMENT_TYPES)


def create_or_reuse_current_bundle(
    db: Session,
    study: Study,
    governance: StudyGovernance,
    document_bodies: dict[str, str],
) -> StudyConsentBundle:
    """Persist immutable versions and point governance at their exact bundle.

    Re-submitting the same documents is idempotent.  Any changed reference,
    version, date or body creates a different document/bundle without changing
    prior invitations or accepted consent.
    """
    metadata = governance_document_metadata(governance)
    validate_document_metadata(metadata)
    specifications = []
    for document_type in DOCUMENT_TYPES:
        version = metadata[document_type]["version"]
        reference = metadata[document_type]["reference"]
        effective_date = metadata[document_type]["effective_date"]
        body = document_bodies.get(document_type, "").strip()
        if not (version and reference and effective_date and body):
            raise ValueError(
                "Every study consent document needs a reference, version, effective date and body."
            )
        if len(body) > 100_000:
            raise ValueError("A study consent document is too long.")
        specifications.append((document_type, version, reference, effective_date, body))

    document_rows: list[StudyConsentDocument] = []
    for document_type, version, reference, effective_date, body in specifications:
        content_sha256 = document_digest(
            document_type, version, reference, effective_date, body
        )
        document = db.scalar(
            select(StudyConsentDocument).where(
                StudyConsentDocument.study_id == study.id,
                StudyConsentDocument.document_type == document_type,
                StudyConsentDocument.content_sha256 == content_sha256,
            )
        )
        if document is None:
            document = StudyConsentDocument(
                organisation_id=study.organisation_id,
                study_id=study.id,
                document_type=document_type,
                title=DOCUMENT_TITLES[document_type],
                version=version,
                reference=reference,
                effective_date=effective_date,
                body=body,
                content_sha256=content_sha256,
            )
            db.add(document)
            db.flush()
        document_rows.append(document)

    bundle_sha256 = _digest(
        [
            (document.document_type, document.content_sha256)
            for document in document_rows
        ]
    )
    bundle = db.scalar(
        select(StudyConsentBundle).where(
            StudyConsentBundle.study_id == study.id,
            StudyConsentBundle.bundle_sha256 == bundle_sha256,
        )
    )
    if bundle is None:
        bundle = StudyConsentBundle(
            organisation_id=study.organisation_id,
            study_id=study.id,
            bundle_sha256=bundle_sha256,
        )
        db.add(bundle)
        db.flush()
        for document in document_rows:
            db.add(
                StudyConsentBundleDocument(
                    bundle_id=bundle.id,
                    document_id=document.id,
                    document_type=document.document_type,
                )
            )
    governance.current_consent_bundle_id = bundle.id
    return bundle


def bind_invitation_to_current_bundle(
    db: Session,
    invitation: ParticipantInvitation,
    governance: StudyGovernance | None,
) -> None:
    """Bind an invitation once, before it is sent; never overwrite it."""
    if invitation.consent_bundle_id or governance is None:
        return
    if not (
        governance.participant_information_available
        or governance.privacy_information_available
        or governance.participation_consent_configured
    ):
        return
    if not has_complete_bundle(db, governance):
        raise ValueError(
            "Study-specific consent documents must be published before inviting participants."
        )
    invitation.consent_bundle_id = governance.current_consent_bundle_id
    # Keep the legacy evidence columns populated for existing audit/export
    # consumers, but source them from the immutable bundle at send time.
    for document in invitation_documents(db, invitation):
        setattr(invitation, f"{document.document_type}_reference", document.reference)
        setattr(invitation, f"{document.document_type}_version", document.version)
        setattr(
            invitation,
            f"{document.document_type}_effective_date",
            document.effective_date,
        )


def invitation_documents(
    db: Session, invitation: ParticipantInvitation
) -> tuple[BoundStudyDocument, ...]:
    return bundle_documents(db, invitation.consent_bundle_id)


def require_bound_documents(
    db: Session, invitation: ParticipantInvitation, governance: StudyGovernance | None
) -> tuple[BoundStudyDocument, ...]:
    """Fail closed for governed studies if their invitation lacks a bundle."""
    documents = invitation_documents(db, invitation)
    if documents:
        if len(documents) != len(DOCUMENT_TYPES):
            raise ValueError(
                "The invitation's study consent document binding is incomplete."
            )
        return documents
    if governance and (
        governance.participant_information_available
        or governance.privacy_information_available
        or governance.participation_consent_configured
    ):
        raise ValueError(
            "This invitation was not bound to study-specific consent documents. Ask the research team for a new invitation."
        )
    return ()
