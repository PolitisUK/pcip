"""Bounded, source-traceable advanced qualitative query projections."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis_projections import CodedPassageProjection, coded_passage_projections
from .models import AnalyticalRelationship, ResearchThemeCode, User

MAX_QUERY_SOURCES = 5000
QUERY_PAGE_SIZE = 30


@dataclass(frozen=True)
class AdvancedQueryFilters:
    study_ids: tuple[int, ...]
    include_code_ids: frozenset[int] = frozenset()
    exclude_code_ids: frozenset[int] = frozenset()
    operator: str = "and"
    theme_id: int | None = None
    researcher_id: int | None = None
    participant_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    relationship_type: str | None = None


@dataclass(frozen=True)
class CoOccurrence:
    left_code_id: int
    right_code_id: int
    source_entries: int
    participant_cases: int


@dataclass(frozen=True)
class AdvancedQueryPage:
    results: tuple[CodedPassageProjection, ...]
    total_applications: int
    participant_cases: int
    source_entries: int
    page: int
    pages: int
    truncated: bool
    co_occurrences: tuple[CoOccurrence, ...]


def _relationship_scope(
    db: Session,
    *,
    organisation_id: int,
    study_ids: tuple[int, ...],
    relationship_type: str,
) -> tuple[set[int], set[int], set[int]]:
    rows = db.scalars(
        select(AnalyticalRelationship)
        .where(
            AnalyticalRelationship.organisation_id == organisation_id,
            AnalyticalRelationship.study_id.in_(study_ids),
            AnalyticalRelationship.relationship_type == relationship_type,
        )
        .limit(MAX_QUERY_SOURCES + 1)
    ).all()
    application_ids: set[int] = set()
    code_ids: set[int] = set()
    theme_ids: set[int] = set()
    for row in rows[:MAX_QUERY_SOURCES]:
        for object_type, object_id in (
            (row.source_type, row.source_id),
            (row.target_type, row.target_id),
        ):
            if object_type == "code_application":
                application_ids.add(object_id)
            elif object_type == "code":
                code_ids.add(object_id)
            elif object_type == "theme":
                theme_ids.add(object_id)
    if theme_ids:
        code_ids.update(
            db.scalars(
                select(ResearchThemeCode.research_code_id).where(
                    ResearchThemeCode.organisation_id == organisation_id,
                    ResearchThemeCode.study_id.in_(study_ids),
                    ResearchThemeCode.research_theme_id.in_(theme_ids),
                )
            ).all()
        )
    return application_ids, code_ids, theme_ids


def advanced_query(
    db: Session,
    user: User,
    filters: AdvancedQueryFilters,
    *,
    page: int = 1,
) -> AdvancedQueryPage:
    """Query researcher coding without accepting SQL-like user input.

    Boolean code logic is evaluated at participant/case level. Returned rows remain
    individual, verified CodeApplications so every match is traceable to its source.
    """
    if filters.operator not in {"and", "or"}:
        raise ValueError("Query operator must be 'and' or 'or'")
    projections, truncated = coded_passage_projections(
        db,
        organisation_id=user.organisation_id,
        study_ids=list(filters.study_ids),
        limit=MAX_QUERY_SOURCES,
    )

    def comparable_timestamp(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    base = [
        item
        for item in projections
        if (filters.participant_id is None or item.participant.id == filters.participant_id)
        and (filters.researcher_id is None or item.researcher.id == filters.researcher_id)
        and (
            filters.date_from is None
            or comparable_timestamp(item.application.created_at) >= filters.date_from
        )
        and (
            filters.date_to is None
            or comparable_timestamp(item.application.created_at) < filters.date_to
        )
    ]

    theme_code_ids: set[int] | None = None
    if filters.theme_id is not None:
        theme_code_ids = set(
            db.scalars(
                select(ResearchThemeCode.research_code_id).where(
                    ResearchThemeCode.organisation_id == user.organisation_id,
                    ResearchThemeCode.study_id.in_(filters.study_ids),
                    ResearchThemeCode.research_theme_id == filters.theme_id,
                )
            ).all()
        )

    relationship_application_ids: set[int] | None = None
    relationship_code_ids: set[int] | None = None
    if filters.relationship_type is not None:
        relationship_application_ids, relationship_code_ids, _ = _relationship_scope(
            db,
            organisation_id=user.organisation_id,
            study_ids=filters.study_ids,
            relationship_type=filters.relationship_type,
        )

    case_codes: dict[int, set[int]] = defaultdict(set)
    for item in base:
        case_codes[item.participant.id].add(item.code.id)
    selected_cases: set[int] = set()
    for participant_id, code_ids in case_codes.items():
        includes = (
            not filters.include_code_ids
            or (
                filters.include_code_ids <= code_ids
                if filters.operator == "and"
                else bool(filters.include_code_ids & code_ids)
            )
        )
        excludes = bool(filters.exclude_code_ids & code_ids)
        if includes and not excludes:
            selected_cases.add(participant_id)

    result_rows = []
    for item in base:
        if item.participant.id not in selected_cases:
            continue
        if filters.include_code_ids and item.code.id not in filters.include_code_ids:
            continue
        if theme_code_ids is not None and item.code.id not in theme_code_ids:
            continue
        if relationship_application_ids is not None and not (
            item.application.id in relationship_application_ids
            or item.code.id in (relationship_code_ids or set())
        ):
            continue
        result_rows.append(item)

    entry_codes: dict[int, set[int]] = defaultdict(set)
    entry_participants: dict[int, int] = {}
    for item in result_rows:
        entry_codes[item.response.id].add(item.code.id)
        entry_participants[item.response.id] = item.participant.id
    pair_entries: dict[tuple[int, int], set[int]] = defaultdict(set)
    pair_cases: dict[tuple[int, int], set[int]] = defaultdict(set)
    for response_id, code_ids in entry_codes.items():
        for pair in combinations(sorted(code_ids), 2):
            pair_entries[pair].add(response_id)
            pair_cases[pair].add(entry_participants[response_id])
    co_occurrences = tuple(
        CoOccurrence(left, right, len(entries), len(pair_cases[(left, right)]))
        for (left, right), entries in sorted(
            pair_entries.items(), key=lambda item: (-len(item[1]), item[0])
        )[:20]
    )

    total = len(result_rows)
    pages = max(1, (total + QUERY_PAGE_SIZE - 1) // QUERY_PAGE_SIZE)
    safe_page = min(max(page, 1), pages)
    start = (safe_page - 1) * QUERY_PAGE_SIZE
    return AdvancedQueryPage(
        results=tuple(result_rows[start : start + QUERY_PAGE_SIZE]),
        total_applications=total,
        participant_cases=len({item.participant.id for item in result_rows}),
        source_entries=len({item.response.id for item in result_rows}),
        page=safe_page,
        pages=pages,
        truncated=truncated,
        co_occurrences=co_occurrences,
    )
