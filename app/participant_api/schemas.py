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
    options: list[str] | None = None
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


class EvidenceUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


class EvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: int = Field(ge=1)
    activity_id: int = Field(ge=1)
    original_name: str
    content_type: str
    size_bytes: int = Field(ge=0)
    scan_status: Literal["pending", "clean", "infected", "scan_failed"]
    created_at: datetime


class EvidenceUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: EvidenceMetadata


class EvidenceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: EvidenceMetadata
    downloadable: bool


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


class ParticipantProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    communication_preference: Literal["email", "sms", "phone", "none"]
    consent_status: str


class UpdateParticipantProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    communication_preference: Literal["email", "sms", "phone", "none"]


class ConsentAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent: Literal[True]


class ConsentAcceptanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_status: Literal["granted"]
    accepted_at: datetime


class LegalDocumentReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["participant_information", "privacy_notice", "consent_text"]
    version: str
    reference: str
    effective_date: str


class StudyLegalDocumentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    documents: list[LegalDocumentReference]


class SubmissionHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    activity_id: int
    activity_title: str
    status: Literal["draft", "submitted"]
    submitted_at: datetime | None = None
    updated_at: datetime


class SubmissionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    data: list[SubmissionHistoryItem]
    pagination: Pagination


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoked: bool = True
    revoked_at: datetime | None = None


class ActivityResponseValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None = None
    choices: list[str] = Field(default_factory=list)
    evidence_id: int | None = None


class ActivityDetailResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    status: Literal["draft", "submitted"]
    value: ActivityResponseValue | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class ActivityDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity: ActivitySummary
    response: ActivityDetailResponseItem | None = None


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


class MessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ParticipantMessageSummary]
    pagination: Pagination


class CreateMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)


class CreateMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: ParticipantMessageSummary


class PrivacyRequestAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int
    request_type: Literal["withdrawal", "deletion"]
    status: Literal["received", "in_progress", "completed", "failed_retrying", "requires_controller_review"]
    submitted_at: datetime
    message: str | None = None


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["study", "all"] = "study"
    study_id: int | None = Field(default=None, ge=1)
    confirmed: Literal[True]


class DeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode_preference: Literal["delete"] = "delete"
    study_id: int | None = Field(default=None, ge=1)
    scope: Literal["study", "account"] = "study"
    confirmed: Literal[True]


class PortalSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study: StudySummary
    participant: ParticipantSummary
    activities: list[ActivitySummary]
    responses: list[PortalResponseItem]
    messages: list[ParticipantMessageSummary]


class ParticipantSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: int
    server_time: datetime
    activities: list[ActivitySummary]
    responses: list[PortalResponseItem]
    evidence: list[EvidenceMetadata]
    messages: list[ParticipantMessageSummary]
    next_sync_token: datetime
