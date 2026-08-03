import type {
  ActivityListResponse,
  ParticipantSessionResponse,
  StudyListResponse,
} from "../api/participantApi";

export type StudySummary = StudyListResponse["data"][number];
export type ActivitySummary = ActivityListResponse["data"][number];

export type ParticipantHomeData = {
  participantDisplayName?: string;
  studies: StudySummary[];
  activeStudyId: number | null;
  requiresStudySelection: boolean;
  activities: ActivitySummary[];
  isRefreshing: boolean;
};

export type ParticipantHomeErrorKind = "access_lost" | "rate_limited" | "temporary_service";

export type ParticipantHomeState =
  | { status: "initialising" }
  | ({ status: "loading" } & ParticipantHomeData)
  | ({ status: "ready" } & ParticipantHomeData)
  | {
      status: "empty";
      participantDisplayName?: string;
      studies: StudySummary[];
      isRefreshing: boolean;
    }
  | ({
      status: "offline";
      message: string;
    } & ParticipantHomeData)
  | ({
      status: "recoverable_error";
      errorKind: ParticipantHomeErrorKind;
      message: string;
      retryAfterSeconds: number | null;
    } & ParticipantHomeData)
  | {
      status: "session_expired";
    };

export type LoadParticipantHomeArgs = {
  accessToken: string;
  session: ParticipantSessionResponse;
  preferredStudyId?: number;
};
