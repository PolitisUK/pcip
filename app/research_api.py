"""Stable researcher-facing Research Intelligence API contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    participant_id: int
    participant_reference: str
    activity_id: int
    activity_title: str
    source_type: Literal["activity_response"] = "activity_response"
    source_excerpt: str
    source_truncated: bool
    submitted_at: datetime | None = None
    updated_at: datetime
    suggested_codes: list[str] = Field(default_factory=list)
    analysis_status: str | None = None


class EvidenceExplorerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    data: list[EvidenceItemResponse]
    total: int = Field(ge=0)
    returned: int = Field(ge=0)


class QuoteFinderResponse(EvidenceExplorerResponse):
    """Quotes are exact excerpts from participant source material, never AI text."""


class ThemeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: int
    name: str
    description: str
    status: Literal["researcher_draft"]
    source_suggestion_ids: list[int] = Field(default_factory=list)
    source_response_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class ThemeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    data: list[ThemeResponse]
