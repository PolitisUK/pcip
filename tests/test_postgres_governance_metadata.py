"""PostgreSQL regression coverage for governance metadata validation.

This file is run separately by the CI migration job, whose database URL points
at its PostgreSQL service.  It deliberately does not use the SQLite fixture in
``tests/test_app.py``.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import StudyConsentDocument, StudyGovernance


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="requires the CI PostgreSQL service",
)


def _csrf_token(client: TestClient) -> str:
    page = client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def _post(client: TestClient, path: str, data: dict[str, str]):
    return client.post(
        path, data={**data, "csrf_token": _csrf_token(client)}, follow_redirects=False
    )


def _governance_payload() -> dict[str, str]:
    return {
        "controller_name": "Test controller",
        "controller_privacy_contact": "privacy@example.test",
        "sponsor_name": "",
        "research_contact": "research@example.test",
        "participant_population": "Synthetic pilot participants",
        "data_categories": "Contact details and diary responses",
        "special_category_data": "no",
        "article_6_lawful_basis": "Controller-approved lawful basis",
        "article_9_condition": "",
        "participation_consent_configured": "true",
        "participant_information_available": "true",
        "privacy_information_available": "true",
        "participant_information_reference": "PI-POSTGRES",
        "participant_information_version": "1.0",
        "participant_information_effective_date": "d" * 31,
        "participant_information_body": "Synthetic participant information.",
        "privacy_notice_reference": "PN-POSTGRES",
        "privacy_notice_version": "1.0",
        "privacy_notice_effective_date": "15 August 2026",
        "privacy_notice_body": "Synthetic privacy notice.",
        "consent_text_reference": "CT-POSTGRES",
        "consent_text_version": "1.0",
        "consent_text_effective_date": "15 August 2026",
        "consent_text_body": "Synthetic consent text.",
        "retention_description": "Controller-approved study retention schedule",
        "deletion_retention_exception": "None",
        "withdrawal_process_defined": "true",
        "deletion_handling_defined": "true",
        "features_assessed": "true",
        "international_transfer_assessment": "recorded",
        "ethics_status": "recorded",
        "dpia_status": "not_required",
        "security_considerations": "Access is limited to authorised study users.",
    }


def test_postgres_governance_metadata_rejection_precedes_writes():
    assert engine.dialect.name == "postgresql"
    original_seed_demo_data = settings.seed_demo_data
    settings.seed_demo_data = True
    try:
        with TestClient(app) as client:
            login = _post(
                client,
                "/login",
                {"email": "admin@politis.local", "password": "PolitisDemo!"},
            )
            assert login.status_code == 303
            client.cookies.update(login.cookies)
            project = _post(
                client,
                "/projects",
                {
                    "title": "PostgreSQL validation project",
                    "code": "POSTGRES-VALIDATION",
                    "description": "",
                    "status_value": "draft",
                },
            )
            project_id = int(project.headers["location"].rsplit("/", 1)[-1])
            study = _post(
                client,
                f"/projects/{project_id}/studies",
                {
                    "title": "PostgreSQL validation study",
                    "code": "POSTGRES-GOVERNANCE",
                    "description": "",
                    "methodology": "diary",
                    "status_value": "draft",
                },
            )
            study_id = int(study.headers["location"].rsplit("/", 1)[-1])

            rejected = _post(
                client, f"/studies/{study_id}/governance", _governance_payload()
            )
            assert rejected.status_code == 400
            assert rejected.json()["detail"] == (
                "Participant information effective date must be 30 characters or fewer."
            )
            with SessionLocal() as db:
                assert (
                    db.scalar(
                        select(func.count(StudyGovernance.id)).where(
                            StudyGovernance.study_id == study_id
                        )
                    )
                    == 0
                )
                assert (
                    db.scalar(
                        select(func.count(StudyConsentDocument.id)).where(
                            StudyConsentDocument.study_id == study_id
                        )
                    )
                    == 0
                )
    finally:
        settings.seed_demo_data = original_seed_demo_data
