from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["ios", "android"] | None = None
    app_version: str | None = Field(default=None, max_length=40)


class SessionExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=1, max_length=512)
    device_hint: DeviceHint | None = None


class BearerSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    revocable: bool = True


class InvitationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    invitation_status: str
    expires_at: datetime
    accepted_at: datetime | None


class StudySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    title: str
    description: str | None = None
    status: str
    methodology: str
    enrolled: bool


class ParticipantSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: int
    display_name: str
    consent_status: str


class Pagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str | None = None
    next_cursor: str | None = None
    limit: int
    has_more: bool


class StudyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[StudySummary]
    pagination: Pagination


class ActivityAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    release_at: datetime | None = None
    due_at: datetime | None = None


class ActivityResponseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class ActivitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: int
    title: str
    prompt: str | None = None
    activity_type: str
    required: bool
    position: int
    availability: ActivityAvailability
    response: ActivityResponseSummary | None = None


class ActivityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ActivitySummary]


class DraftResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None = None
    choices: list[str] = Field(default_factory=list)
    evidence_id: int | None = Field(default=None, ge=1)


class SubmitResponseRequest(DraftResponseRequest):
    model_config = ConfigDict(extra="forbid")


class DraftResponseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    status: Literal["draft"]
    updated_at: datetime


class SubmittedResponseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    status: Literal["submitted"]
    submitted_at: datetime
    updated_at: datetime


class SessionExchangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: BearerSession
    participant: ParticipantSummary
    invitation: InvitationContext
    next_action: str


class SessionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: datetime
    revocable: bool = True


class ParticipantSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: SessionInfo
    participant: ParticipantSummary
    study_scope: list[int]


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoked: bool = True
    revoked_at: datetime | None = None


class ActivityResponseValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None = None
    choices: list[str] = Field(default_factory=list)
    evidence_id: int | None = None


class PortalResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: int
    status: str
    value: ActivityResponseValue | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class ParticipantMessageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: int
    sender_type: str
    body: str
    created_at: datetime


class PortalSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study: StudySummary
    participant: ParticipantSummary
    activities: list[ActivitySummary]
    responses: list[PortalResponseItem]
    messages: list[ParticipantMessageSummary]
