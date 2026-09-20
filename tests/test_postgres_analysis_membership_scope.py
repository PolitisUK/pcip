"""PostgreSQL regression coverage for multi-organisation Workbench writes.

The CI migration job runs this file against its disposable PostgreSQL service.
It exercises the same request/flush boundary that failed in production.
"""

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import (
    AnalysisCanvas,
    AnalyticalRelationship,
    Organisation,
    OrganisationMembership,
    Project,
    ResearchCode,
    ResearchMemo,
    Study,
    StudyAccess,
    User,
)

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
        path,
        data={**data, "csrf_token": _csrf_token(client)},
        follow_redirects=False,
    )


def test_multi_organisation_researcher_can_create_workbench_records():
    original_seed_demo_data = settings.seed_demo_data
    settings.seed_demo_data = True
    marker = uuid4().hex[:10]
    try:
        with TestClient(app) as client:
            login = _post(
                client,
                "/login",
                {"email": "admin@politis.local", "password": "PolitisDemo!"},
            )
            assert login.status_code == 303
            client.cookies.update(login.cookies)

            with SessionLocal() as db:
                researcher = db.scalar(
                    select(User).where(User.email == "admin@politis.local")
                )
                organisation = Organisation(
                    name=f"Membership scope {marker}",
                    slug=f"membership-scope-{marker}",
                )
                db.add(organisation)
                db.flush()
                db.add(
                    OrganisationMembership(
                        user_id=researcher.id,
                        organisation_id=organisation.id,
                        role="researcher",
                        is_active=True,
                    )
                )
                project = Project(
                    organisation_id=organisation.id,
                    title="Synthetic PostgreSQL project",
                    code=f"PG-{marker}",
                    status="draft",
                    created_by_id=researcher.id,
                )
                db.add(project)
                db.flush()
                study = Study(
                    organisation_id=organisation.id,
                    project_id=project.id,
                    title="Synthetic PostgreSQL study",
                    code=f"PGS-{marker}",
                    methodology="diary",
                    status="draft",
                    created_by_id=researcher.id,
                )
                db.add(study)
                db.flush()
                db.add(
                    StudyAccess(
                        organisation_id=organisation.id,
                        study_id=study.id,
                        user_id=researcher.id,
                        permission="edit",
                        created_by_id=researcher.id,
                    )
                )
                source_code = ResearchCode(
                    organisation_id=organisation.id,
                    study_id=study.id,
                    name="Source code",
                    definition="",
                    created_by_id=researcher.id,
                )
                target_code = ResearchCode(
                    organisation_id=organisation.id,
                    study_id=study.id,
                    name="Target code",
                    definition="",
                    created_by_id=researcher.id,
                )
                db.add_all((source_code, target_code))
                db.commit()
                organisation_id = organisation.id
                study_id = study.id
                researcher_id = researcher.id
                source_code_id = source_code.id
                target_code_id = target_code.id

            switched = _post(
                client,
                "/organisations/switch",
                {"organisation_id": str(organisation_id)},
            )
            assert switched.status_code == 303
            client.cookies.update(switched.cookies)

            code_response = _post(
                client,
                f"/studies/{study_id}/codebook",
                {
                    "name": "Created through second membership",
                    "definition": "Synthetic regression record",
                    "parent_code_id": "",
                },
            )
            memo_response = _post(
                client,
                f"/studies/{study_id}/memos",
                {
                    "scope_ref": "study",
                    "title": "Second-membership memo",
                    "body": "Synthetic regression memo",
                },
            )
            relationship_response = _post(
                client,
                f"/studies/{study_id}/relationships",
                {
                    "source_ref": f"code:{source_code_id}",
                    "relationship_type": "supports",
                    "target_ref": f"code:{target_code_id}",
                    "rationale": "Synthetic regression relationship",
                },
            )
            canvas_response = _post(
                client,
                f"/studies/{study_id}/canvas/nodes",
                {"object_ref": f"code:{source_code_id}"},
            )

            assert code_response.status_code == 303
            assert memo_response.status_code == 303
            assert relationship_response.status_code == 303
            assert canvas_response.status_code == 303

            with SessionLocal() as db:
                assert db.scalar(
                    select(ResearchCode).where(
                        ResearchCode.study_id == study_id,
                        ResearchCode.name == "Created through second membership",
                    )
                )
                assert db.scalar(
                    select(ResearchMemo).where(
                        ResearchMemo.study_id == study_id,
                        ResearchMemo.title == "Second-membership memo",
                    )
                )
                assert db.scalar(
                    select(AnalyticalRelationship).where(
                        AnalyticalRelationship.study_id == study_id,
                        AnalyticalRelationship.rationale
                        == "Synthetic regression relationship",
                    )
                )
                assert db.scalar(
                    select(AnalysisCanvas).where(
                        AnalysisCanvas.study_id == study_id,
                        AnalysisCanvas.owner_id == researcher_id,
                    )
                )
    finally:
        settings.seed_demo_data = original_seed_demo_data


def test_workbench_actor_guard_rejects_user_without_active_membership():
    marker = uuid4().hex[:10]
    with SessionLocal() as db:
        organisation = Organisation(
            name=f"Guard target {marker}",
            slug=f"guard-target-{marker}",
        )
        foreign_organisation = Organisation(
            name=f"Guard foreign {marker}",
            slug=f"guard-foreign-{marker}",
        )
        db.add_all((organisation, foreign_organisation))
        db.flush()
        actor = User(
            organisation_id=foreign_organisation.id,
            name="Foreign synthetic actor",
            email=f"foreign-{marker}@example.test",
            role="researcher",
        )
        db.add(actor)
        db.flush()
        project = Project(
            organisation_id=organisation.id,
            title="Guard project",
            code=f"GP-{marker}",
            status="draft",
            created_by_id=actor.id,
        )
        db.add(project)
        db.flush()
        study = Study(
            organisation_id=organisation.id,
            project_id=project.id,
            title="Guard study",
            code=f"GS-{marker}",
            methodology="diary",
            status="draft",
            created_by_id=actor.id,
        )
        db.add(study)
        db.flush()

        db.add(
            ResearchCode(
                organisation_id=organisation.id,
                study_id=study.id,
                name="Must be rejected",
                definition="",
                created_by_id=actor.id,
            )
        )
        with pytest.raises(ProgrammingError, match="creator is outside organisation"):
            db.flush()
