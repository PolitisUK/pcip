"""Bounded, traceable Analysis Workbench exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis_audit import analysis_audit_page
from .models import (
    ActivityResponse,
    AnalysisTarget,
    AnalyticalRelationship,
    CodeApplication,
    Participant,
    Project,
    ResearchAnalysisSuggestion,
    ResearchAnnotation,
    ResearchCode,
    ResearchFinding,
    ResearchMemo,
    ResearchTheme,
    ResearchThemeCode,
    Study,
    User,
)
from .passage_coding import verified_passage
from .research_workspace import response_body

MAX_EXPORT_ROWS = 5000
EXPORT_SCHEMA_VERSION = "analysis-workbench-export-v1"
LOOKUP_CHUNK_SIZE = 500


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json(value: str, fallback):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed


def _bounded(db: Session, statement):
    rows = db.scalars(statement.limit(MAX_EXPORT_ROWS + 1)).all()
    return rows[:MAX_EXPORT_ROWS], len(rows) > MAX_EXPORT_ROWS


def _by_ids(db: Session, model, identifiers: set[int], *scope):
    """Avoid database parameter limits when resolving bounded export references."""
    ordered = sorted(identifiers)
    rows = []
    for offset in range(0, len(ordered), LOOKUP_CHUNK_SIZE):
        rows.extend(db.scalars(
            select(model).where(
                model.id.in_(ordered[offset:offset + LOOKUP_CHUNK_SIZE]), *scope
            )
        ).all())
    return {row.id: row for row in rows}


def _person(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.name}


def build_analysis_export(
    db: Session,
    *,
    user: User,
    project: Project,
    studies: list[Study],
) -> tuple[bytes, dict]:
    """Build a fixed-name ZIP of JSON components for already-authorised studies."""
    study_ids = [row.id for row in studies]
    files: dict[str, list[dict]] = {}
    truncation: dict[str, bool] = {}

    def rows_for(model, order_by):
        if not study_ids:
            return [], False
        return _bounded(
            db,
            select(model).where(
                model.organisation_id == user.organisation_id,
                model.study_id.in_(study_ids),
            ).order_by(order_by),
        )

    codes, truncation["codebook.json"] = rows_for(ResearchCode, ResearchCode.id)
    code_map = {row.id: row for row in codes}
    creator_ids = {
        row.created_by_id for row in codes
    }

    applications, truncation["coded_passages.json"] = rows_for(
        CodeApplication, CodeApplication.id
    )
    annotations, truncation["annotations.json"] = rows_for(
        ResearchAnnotation, ResearchAnnotation.id
    )
    memos, truncation["memos.json"] = rows_for(ResearchMemo, ResearchMemo.id)
    themes, truncation["themes.json"] = rows_for(ResearchTheme, ResearchTheme.id)
    theme_links, theme_links_truncated = rows_for(
        ResearchThemeCode, ResearchThemeCode.id
    )
    truncation["themes.json"] = truncation["themes.json"] or theme_links_truncated
    relationships, truncation["relationships.json"] = rows_for(
        AnalyticalRelationship, AnalyticalRelationship.id
    )
    findings, truncation["findings.json"] = rows_for(
        ResearchFinding, ResearchFinding.id
    )
    suggestions, truncation["ai_suggestions.json"] = rows_for(
        ResearchAnalysisSuggestion, ResearchAnalysisSuggestion.id
    )

    referenced_code_ids = {
        row.research_code_id for row in applications
    } | {row.research_code_id for row in theme_links}
    code_map.update(_by_ids(
        db,
        ResearchCode,
        referenced_code_ids - set(code_map),
        ResearchCode.organisation_id == user.organisation_id,
        ResearchCode.study_id.in_(study_ids),
    ))

    creator_ids.update(row.applied_by_id for row in applications)
    creator_ids.update(row.author_id for row in annotations)
    creator_ids.update(row.author_id for row in memos)
    creator_ids.update(row.created_by_id for row in themes)
    creator_ids.update(row.linked_by_id for row in theme_links)
    creator_ids.update(row.created_by_id for row in relationships)
    creator_ids.update(row.created_by_id for row in findings)
    creator_ids.update(
        row.reviewer_user_id for row in suggestions if row.reviewer_user_id is not None
    )
    users = _by_ids(
        db, User, creator_ids, User.organisation_id == user.organisation_id
    )

    target_ids = {
        row.analysis_target_id for row in applications
    } | {row.analysis_target_id for row in annotations}
    targets = _by_ids(
        db,
        AnalysisTarget,
        target_ids,
        AnalysisTarget.organisation_id == user.organisation_id,
        AnalysisTarget.study_id.in_(study_ids),
    ) if study_ids else {}
    response_ids = {
        row.activity_response_id
        for row in targets.values()
        if row.activity_response_id is not None
    }
    responses = _by_ids(
        db,
        ActivityResponse,
        response_ids,
        ActivityResponse.organisation_id == user.organisation_id,
        ActivityResponse.study_id.in_(study_ids),
    ) if study_ids else {}
    participant_ids = {row.participant_id for row in responses.values()}
    participants = _by_ids(
        db,
        Participant,
        participant_ids,
        Participant.organisation_id == user.organisation_id,
    )

    files["codebook.json"] = [
        {
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "name": row.name,
            "definition": row.definition,
            "parent_code_id": row.parent_code_id,
            "created_by": _person(users.get(row.created_by_id)),
            "archived_at": _iso(row.archived_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in codes
    ]

    coded_rows = []
    for row in applications:
        target = targets.get(row.analysis_target_id)
        response = responses.get(target.activity_response_id) if target else None
        passage = None
        source_status = "source_target_unavailable"
        participant = None
        if response is not None:
            passage = verified_passage(response_body(response.value_json), row.anchor_json)
            source_status = "verified" if passage is not None else "could_not_be_verified"
            participant = participants.get(response.participant_id)
        elif target is not None and target.target_type == "evidence_file":
            source_status = "image_region_reference"
        coded_rows.append({
            "content_origin": "participant_source_excerpt",
            "id": row.id,
            "study_id": row.study_id,
            "analysis_target_id": row.analysis_target_id,
            "target_type": target.target_type if target else None,
            "source_response_id": response.id if response else None,
            "source_evidence_file_id": target.evidence_file_id if target else None,
            "participant": (
                {"id": participant.id, "reference": participant.reference}
                if participant else None
            ),
            "anchor": _json(row.anchor_json, None),
            "source_verification": source_status,
            "passage": passage,
            "research_code": (
                {"id": code_map[row.research_code_id].id,
                 "name": code_map[row.research_code_id].name,
                 "archived_at": _iso(code_map[row.research_code_id].archived_at)}
                if row.research_code_id in code_map else None
            ),
            "applied_by": _person(users.get(row.applied_by_id)),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        })
    files["coded_passages.json"] = coded_rows

    annotation_rows = []
    for row in annotations:
        target = targets.get(row.analysis_target_id)
        response = responses.get(target.activity_response_id) if target else None
        passage = (
            verified_passage(response_body(response.value_json), row.anchor_json)
            if response is not None else None
        )
        annotation_rows.append({
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "analysis_target_id": row.analysis_target_id,
            "target_type": target.target_type if target else None,
            "source_response_id": response.id if response else None,
            "source_evidence_file_id": target.evidence_file_id if target else None,
            "source_anchor": _json(row.anchor_json, None),
            "source_verification": (
                "verified" if passage is not None else
                "image_region_reference" if target and target.target_type == "evidence_file" else
                "could_not_be_verified"
            ),
            "source_passage": passage,
            "body": row.body,
            "author": _person(users.get(row.author_id)),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        })
    files["annotations.json"] = annotation_rows

    files["memos.json"] = [
        {
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "scope_type": row.scope_type,
            "scope_id": (
                row.participant_id or row.activity_response_id or row.analysis_target_id
                or row.research_code_id or row.research_theme_id
            ),
            "title": row.title,
            "body": row.body,
            "author": _person(users.get(row.author_id)),
            "archived_at": _iso(row.archived_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in memos
    ]

    links_by_theme: dict[int, list[dict]] = {}
    for link in theme_links:
        code = code_map.get(link.research_code_id)
        links_by_theme.setdefault(link.research_theme_id, []).append({
            "code_id": link.research_code_id,
            "code_name": code.name if code else None,
            "linked_by": _person(users.get(link.linked_by_id)),
            "created_at": _iso(link.created_at),
        })
    files["themes.json"] = [
        {
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "name": row.name,
            "description": row.description,
            "status": row.status,
            "source_suggestion_ids": _json(row.source_suggestion_ids_json, []),
            "code_links": links_by_theme.get(row.id, []),
            "created_by": _person(users.get(row.created_by_id)),
            "archived_at": _iso(row.archived_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in themes
    ]

    files["relationships.json"] = [
        {
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "source": {"type": row.source_type, "id": row.source_id},
            "relationship_type": row.relationship_type,
            "target": {"type": row.target_type, "id": row.target_id},
            "rationale": row.rationale,
            "created_by": _person(users.get(row.created_by_id)),
            "created_at": _iso(row.created_at),
        }
        for row in relationships
    ]

    files["findings.json"] = [
        {
            "content_origin": "researcher_created",
            "id": row.id,
            "study_id": row.study_id,
            "title": row.title,
            "body": row.body,
            "originating_ai_suggestion_id": row.originating_suggestion_id,
            "created_by": _person(users.get(row.created_by_id)),
            "archived_at": _iso(row.archived_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in findings
    ]

    files["ai_suggestions.json"] = [
        {
            "content_origin": "ai_suggestion",
            "source_content_origin": "participant_source_snapshot",
            "id": row.id,
            "study_id": row.study_id,
            "source_response_id": row.source_response_id,
            "source_snapshot": row.source_snapshot,
            "suggested_codes": _json(row.suggested_codes_json, []),
            "provisional_insight": row.provisional_insight,
            "confidence": row.confidence,
            "status": row.status,
            "reviewer": _person(users.get(row.reviewer_user_id)),
            "reviewer_note": row.reviewer_note,
            "reviewed_at": _iso(row.reviewed_at),
            "model": {"provider": row.model_provider, "deployment": row.model_deployment},
            "prompt_template_version": row.prompt_template_version,
            "methodology": {
                "id": row.methodology_id,
                "variant": row.methodology_variant,
                "library_version": row.methodology_library_version,
                "rule_references": _json(row.methodology_rule_references_json, []),
                "protocol_version": row.protocol_version,
            },
            "human_review_required": row.human_review_required,
            "created_at": _iso(row.created_at),
        }
        for row in suggestions
    ]

    audit_rows, _, _, audit_truncated, _ = analysis_audit_page(
        db, user, project.id, studies, page=1, per_page=MAX_EXPORT_ROWS
    )
    truncation["analytical_audit.json"] = audit_truncated
    files["analytical_audit.json"] = [
        {
            "content_origin": "system_audit_metadata",
            "id": item["event"].id,
            "study_id": item["event"].study_id or item["study"].id,
            "actor": _person(item["actor"]),
            "action": item["event"].action,
            "entity_type": item["event"].entity_type,
            "entity_id": item["event"].entity_id,
            "bounded_detail": item["event"].detail,
            "created_at": _iso(item["event"].created_at),
        }
        for item in audit_rows
    ]

    generated_at = datetime.now(timezone.utc)
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "generated_by": _person(user),
        "project": {"id": project.id, "title": project.title},
        "studies": [
            {"id": row.id, "title": row.title} for row in studies
        ],
        "content_boundaries": {
            "participant_source_excerpt": "Verified excerpts or source references; no additional copy is persisted by the workbench.",
            "researcher_created": "Researcher-authored analytical material and provenance.",
            "ai_suggestion": "Untrusted AI output and provider provenance, distinct from accepted findings.",
            "system_audit_metadata": "Canonical analysis audit metadata; participant response bodies are excluded.",
        },
        "component_counts": {name: len(rows) for name, rows in files.items()},
        "truncated_components": sorted(
            name for name, was_truncated in truncation.items() if was_truncated
        ),
        "maximum_records_per_component": MAX_EXPORT_ROWS,
    }
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        output.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        for name, rows in files.items():
            output.writestr(name, json.dumps(rows, ensure_ascii=False, indent=2))
    return archive.getvalue(), manifest
