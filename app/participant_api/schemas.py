from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str | None = None
    app_version: str | None = None


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


class ParticipantSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: int
    display_name: str
    consent_status: str


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
