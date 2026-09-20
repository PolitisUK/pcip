"""Profile representative Analysis Workbench reads against synthetic data.

This is an explicit local QA utility. It refuses production and requires a
database name containing ``qa`` or ``test`` so it cannot be pointed at a live
customer database by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SEED_DEMO_DATA", "true")
os.environ.setdefault("STARTUP_VALIDATE_MIGRATIONS", "false")

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.db import SessionLocal, engine
from app.main import app
from app.models import (
    Activity,
    ActivityResponse,
    AnalysisCanvas,
    AnalysisCanvasNode,
    AnalysisTarget,
    AnalyticalRelationship,
    AuditEvent,
    CodeApplication,
    Participant,
    Project,
    ResearchAnnotation,
    ResearchCode,
    ResearchFinding,
    ResearchMemo,
    ResearchTheme,
    ResearchThemeCode,
    Study,
    StudyEnrolment,
    User,
)
from app.passage_coding import text_anchor


client = TestClient(app)


def assert_disposable_database() -> None:
    database_name = str(engine.url.database or "").lower()
    if os.environ.get("ENVIRONMENT", "").lower() == "production":
        raise RuntimeError("Analysis benchmark refuses the production environment")
    if not any(marker in database_name for marker in ("qa", "test")):
        raise RuntimeError("Analysis benchmark requires a qa/test database name")


@contextmanager
def query_counter():
    count = {"value": 0, "elapsed": 0.0, "slowest": []}

    def before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _many):
        count["value"] += 1
        context._analysis_benchmark_started = time.perf_counter()

    def after_cursor_execute(_conn, _cursor, statement, _parameters, context, _many):
        elapsed = time.perf_counter() - context._analysis_benchmark_started
        count["elapsed"] += elapsed
        count["slowest"].append((elapsed, " ".join(statement.split())[:180]))

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        event.remove(engine, "after_cursor_execute", after_cursor_execute)


def csrf_token() -> str:
    page = client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    if match is None:
        raise RuntimeError("CSRF token unavailable")
    return match.group(1)


def authenticate() -> None:
    response = client.post(
        "/login",
        data={
            "email": "admin@politis.local",
            "password": "PolitisDemo!",
            "csrf_token": csrf_token(),
        },
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise RuntimeError(f"Synthetic administrator login failed: {response.status_code}")


def seed_synthetic_analysis(participant_count: int) -> tuple[int, int, int]:
    with SessionLocal() as db:
        existing = db.scalar(select(Project).where(Project.code == "QA-PERF"))
        if existing is not None:
            study = db.scalar(select(Study).where(Study.project_id == existing.id))
            code = db.scalar(select(ResearchCode).where(ResearchCode.study_id == study.id))
            return existing.id, study.id, code.id

        owner = db.scalar(select(User).where(User.email == "admin@politis.local"))
        if owner is None:
            raise RuntimeError("Seeded synthetic administrator is unavailable")
        project = Project(
            organisation_id=owner.organisation_id,
            title="Synthetic Analysis Performance",
            code="QA-PERF",
            status="live",
            created_by_id=owner.id,
        )
        db.add(project)
        db.flush()
        study = Study(
            organisation_id=owner.organisation_id,
            project_id=project.id,
            title="Synthetic longitudinal study",
            code="QA-PERF-STUDY",
            methodology="diary",
            status="live",
            created_by_id=owner.id,
        )
        db.add(study)
        db.flush()
        activities = [
            Activity(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                title=f"Synthetic diary wave {wave + 1}",
                prompt="Describe access and change over time.",
                position=wave + 1,
            )
            for wave in range(4)
        ]
        codes = [
            ResearchCode(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                name=f"Synthetic code {index + 1:02d}",
                definition="Synthetic performance-test code.",
                created_by_id=owner.id,
            )
            for index in range(20)
        ]
        themes = [
            ResearchTheme(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                name=f"Synthetic theme {index + 1:02d}",
                description="Synthetic researcher interpretation.",
                created_by_id=owner.id,
            )
            for index in range(10)
        ]
        db.add_all([*activities, *codes, *themes])
        db.flush()
        db.add_all(
            ResearchThemeCode(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                research_theme_id=themes[index % len(themes)].id,
                research_code_id=code.id,
                linked_by_id=owner.id,
            )
            for index, code in enumerate(codes)
        )

        participants = [
            Participant(
                organisation_id=owner.organisation_id,
                reference=f"QA-{index + 1:04d}",
                name=f"Synthetic participant {index + 1:04d}",
                status="active",
                consent_status="granted",
                created_by_id=owner.id,
            )
            for index in range(participant_count)
        ]
        db.add_all(participants)
        db.flush()
        db.add_all(
            StudyEnrolment(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                participant_id=participant.id,
            )
            for participant in participants
        )
        responses: list[ActivityResponse] = []
        bodies: dict[int, str] = {}
        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for participant_index, participant in enumerate(participants):
            for wave, activity in enumerate(activities):
                body = (
                    f"Participant {participant_index + 1} describes changing access "
                    f"during wave {wave + 1} 😀 with context and a negative case."
                )
                response = ActivityResponse(
                    organisation_id=owner.organisation_id,
                    study_id=study.id,
                    activity_id=activity.id,
                    participant_id=participant.id,
                    value_json=json.dumps({
                        "text": body,
                        "researcher_codes": ["legacy synthetic label"],
                        "place": f"Area {(participant_index % 12) + 1}",
                    }),
                    status="submitted",
                    submitted_at=base_time + timedelta(days=wave * 30 + participant_index % 20),
                )
                responses.append(response)
                bodies[id(response)] = body
        db.add_all(responses)
        db.flush()
        targets = [
            AnalysisTarget(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                target_type="activity_response",
                activity_response_id=response.id,
                authorship="researcher",
                created_by_id=owner.id,
            )
            for response in responses
        ]
        db.add_all(targets)
        db.flush()
        applications: list[CodeApplication] = []
        for index, (response, target) in enumerate(zip(responses, targets, strict=True)):
            body = bodies[id(response)]
            for code_offset in (0, 1):
                applications.append(CodeApplication(
                    organisation_id=owner.organisation_id,
                    study_id=study.id,
                    analysis_target_id=target.id,
                    research_code_id=codes[(index + code_offset) % len(codes)].id,
                    applied_by_id=owner.id,
                    anchor_json=text_anchor(body, 0, len(body)),
                ))
        db.add_all(applications)
        db.flush()
        db.add_all(
            ResearchAnnotation(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                analysis_target_id=target.id,
                author_id=owner.id,
                anchor_json=text_anchor(bodies[id(response)], 0, len(bodies[id(response)])),
                body="Synthetic reflexive annotation.",
            )
            for response, target in list(zip(responses, targets, strict=True))[::10]
        )
        memos = [
            ResearchMemo(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                scope_type="study",
                title=f"Synthetic memo {index + 1:03d}",
                body="Synthetic analytical memo for performance QA.",
                author_id=owner.id,
            )
            for index in range(100)
        ]
        findings = [
            ResearchFinding(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                title=f"Synthetic finding {index + 1:03d}",
                body="Synthetic researcher-authored conclusion for performance QA.",
                created_by_id=owner.id,
            )
            for index in range(100)
        ]
        db.add_all([*memos, *findings])
        db.flush()
        relationships = [
            AnalyticalRelationship(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                source_type="code_application",
                source_id=applications[index].id,
                relationship_type="qualifies" if index % 2 else "supports",
                target_type="finding",
                target_id=finding.id,
                rationale="Synthetic explicit researcher relationship.",
                created_by_id=owner.id,
            )
            for index, finding in enumerate(findings)
        ]
        canvas = AnalysisCanvas(
            organisation_id=owner.organisation_id,
            study_id=study.id,
            owner_id=owner.id,
        )
        db.add(canvas)
        db.flush()
        db.add_all(
            AnalysisCanvasNode(
                organisation_id=owner.organisation_id,
                study_id=study.id,
                canvas_id=canvas.id,
                object_type="code_application",
                object_id=application.id,
                x=float((index % 10) * 200),
                y=float((index // 10) * 160),
                added_by_id=owner.id,
            )
            for index, application in enumerate(applications[:100])
        )
        db.add_all(relationships)
        db.add_all(
            AuditEvent(
                organisation_id=owner.organisation_id,
                project_id=project.id,
                study_id=study.id,
                actor_user_id=owner.id,
                action="code_application.created",
                entity_type="code_application",
                entity_id=str(application.id),
                detail="synthetic benchmark event",
            )
            for application in applications[:500]
        )
        db.commit()
        return project.id, study.id, codes[0].id


def benchmark_get(path: str, rounds: int) -> dict[str, object]:
    with query_counter() as queries:
        started = time.perf_counter()
        for _ in range(rounds):
            response = client.get(path)
            if response.status_code != 200:
                raise RuntimeError(f"{path} returned {response.status_code}")
        elapsed = time.perf_counter() - started
    return {
        "path": path,
        "average_ms": round(elapsed * 1000 / rounds, 2),
        "queries": round(queries["value"] / rounds, 1),
        "database_ms": round(queries["elapsed"] * 1000 / rounds, 2),
        "slowest_query": max(queries["slowest"], default=(0.0, ""))[1],
    }


def benchmark_export(project_id: int, study_id: int, rounds: int) -> dict[str, object]:
    token = csrf_token()
    path = f"/projects/{project_id}/workspace/export"
    with query_counter() as queries:
        started = time.perf_counter()
        for _ in range(rounds):
            response = client.post(
                path,
                data={"study_id": str(study_id), "csrf_token": token},
            )
            if response.status_code != 200:
                raise RuntimeError(f"{path} returned {response.status_code}")
        elapsed = time.perf_counter() - started
    return {
        "path": f"POST {path}",
        "average_ms": round(elapsed * 1000 / rounds, 2),
        "queries": round(queries["value"] / rounds, 1),
        "database_ms": round(queries["elapsed"] * 1000 / rounds, 2),
        "slowest_query": max(queries["slowest"], default=(0.0, ""))[1],
        "response_bytes": len(response.content),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participants", type=int, default=250)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    assert_disposable_database()
    with client:
        authenticate()
        project_id, study_id, code_id = seed_synthetic_analysis(args.participants)
        paths = [
            f"/projects/{project_id}/workspace/entries",
            f"/projects/{project_id}/workspace/coding?study_id={study_id}",
            f"/projects/{project_id}/workspace/matrices?study_id={study_id}&dimension=code",
            f"/projects/{project_id}/workspace/longitudinal?study_id={study_id}",
            f"/projects/{project_id}/workspace/queries?study_id={study_id}&include_code_id={code_id}",
            f"/studies/{study_id}/relationships",
            f"/studies/{study_id}/canvas",
            f"/studies/{study_id}/findings",
        ]
        results = [benchmark_get(path, args.rounds) for path in paths]
        results.append(benchmark_export(project_id, study_id, args.rounds))
    print(json.dumps({
        "dataset": {
            "participants": args.participants,
            "responses": args.participants * 4,
            "code_applications": args.participants * 8,
        },
        "rounds": args.rounds,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
