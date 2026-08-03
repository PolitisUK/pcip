import { ApiRequestError } from "../api/client";
import {
  getParticipantActivities,
  getParticipantStudies,
  type ActivityListResponse,
  type ParticipantSessionResponse,
  type StudyListResponse,
} from "../api/participantApi";
import type {
  LoadParticipantHomeArgs,
  ParticipantHomeData,
  ParticipantHomeState,
} from "./types";

type StateListener = (state: ParticipantHomeState) => void;

export class ParticipantHomeController {
  private state: ParticipantHomeState = { status: "initialising" };
  private readonly listeners = new Set<StateListener>();
  private disposed = false;
  private operationVersion = 0;
  private abortController: AbortController | null = null;
  private accessToken: string | null = null;
  private session: ParticipantSessionResponse | null = null;
  private snapshot: ParticipantHomeData = {
    participantDisplayName: undefined,
    studies: [],
    activeStudyId: null,
    requiresStudySelection: false,
    activities: [],
    isRefreshing: false,
  };

  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);

    return () => {
      this.listeners.delete(listener);
    };
  }

  getState(): ParticipantHomeState {
    return this.state;
  }

  async load(args: LoadParticipantHomeArgs): Promise<void> {
    this.accessToken = args.accessToken;
    this.session = args.session;

    const operationVersion = this.beginOperation();
    const participantDisplayName = args.session.participant.display_name;

    const shouldPreserve = this.snapshot.studies.length > 0 || this.snapshot.activities.length > 0;
    if (shouldPreserve) {
      this.setState({
        status: "loading",
        ...this.snapshot,
        participantDisplayName,
        isRefreshing: true,
      });
    } else {
      this.setState({
        status: "loading",
        participantDisplayName,
        studies: [],
        activeStudyId: null,
        requiresStudySelection: false,
        activities: [],
        isRefreshing: false,
      });
    }

    try {
      const studiesResponse = await getParticipantStudies(args.accessToken, {
        signal: this.abortController?.signal,
      });
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      const activeStudyId = chooseActiveStudyId(studiesResponse.data, args.session.study_scope, {
        preferredStudyId: args.preferredStudyId,
        restoredStudyId: this.snapshot.activeStudyId,
      });
      const requiresStudySelection = studiesResponse.data.length > 1 && activeStudyId === null;

      this.snapshot = {
        participantDisplayName,
        studies: studiesResponse.data,
        activeStudyId,
        requiresStudySelection,
        activities: this.snapshot.activeStudyId === activeStudyId ? this.snapshot.activities : [],
        isRefreshing: false,
      };

      const activitiesResponse = activeStudyId === null
        ? { data: [] as ActivityListResponse["data"] }
        : await getParticipantActivities(args.accessToken, activeStudyId, {
            signal: this.abortController?.signal,
          });
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      this.snapshot.activities = activitiesResponse.data;

      if (studiesResponse.data.length === 0) {
        this.setState({
          status: "empty",
          participantDisplayName,
          studies: [],
          isRefreshing: false,
        });
        return;
      }

      this.setState({
        status: "ready",
        ...this.snapshot,
      });
    } catch (error) {
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      this.setState(mapLoadError(error, this.snapshot));
    }
  }

  async refresh(): Promise<void> {
    if (!this.accessToken || !this.session) {
      return;
    }

    await this.load({
      accessToken: this.accessToken,
      session: this.session,
      preferredStudyId: this.snapshot.activeStudyId ?? undefined,
    });
  }

  async selectStudy(studyId: number): Promise<void> {
    if (!this.accessToken || !this.session) {
      return;
    }

    await this.load({
      accessToken: this.accessToken,
      session: this.session,
      preferredStudyId: studyId,
    });
  }

  clear(): void {
    this.operationVersion += 1;
    this.abortController?.abort();
    this.abortController = null;
    this.accessToken = null;
    this.session = null;
    this.snapshot = {
      participantDisplayName: undefined,
      studies: [],
      activeStudyId: null,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    };
    this.setState({ status: "initialising" });
  }

  destroy(): void {
    this.disposed = true;
    this.clear();
    this.listeners.clear();
  }

  private setState(state: ParticipantHomeState): void {
    if (this.disposed) {
      return;
    }

    this.state = state;
    for (const listener of this.listeners) {
      listener(state);
    }
  }

  private beginOperation(): number {
    this.operationVersion += 1;
    this.abortController?.abort();
    this.abortController = new AbortController();
    return this.operationVersion;
  }

  private isCurrentOperation(operationVersion: number): boolean {
    return !this.disposed && this.operationVersion === operationVersion;
  }
}

function chooseActiveStudyId(
  studies: StudyListResponse["data"],
  studyScope: number[],
  options?: {
    preferredStudyId?: number;
    restoredStudyId?: number | null;
  },
): number | null {
  const preferredStudyId = options?.preferredStudyId;
  if (
    typeof preferredStudyId === "number" &&
    studies.some((study) => study.study_id === preferredStudyId) &&
    isAuthorisedStudy(preferredStudyId, studyScope)
  ) {
    return preferredStudyId;
  }

  const restoredStudyId = options?.restoredStudyId;
  if (
    typeof restoredStudyId === "number" &&
    studies.some((study) => study.study_id === restoredStudyId) &&
    isAuthorisedStudy(restoredStudyId, studyScope)
  ) {
    return restoredStudyId;
  }

  if (studies.length === 1) {
    return studies[0]?.study_id ?? null;
  }

  const authorisedStudies = studies.filter((study) => isAuthorisedStudy(study.study_id, studyScope));
  if (authorisedStudies.length === 1) {
    return authorisedStudies[0]?.study_id ?? null;
  }

  if (studies.length > 1) {
    return null;
  }

  return studies[0]?.study_id ?? null;
}

function isAuthorisedStudy(studyId: number, studyScope: number[]): boolean {
  if (!studyScope.length) {
    return true;
  }
  return studyScope.includes(studyId);
}

function mapLoadError(error: unknown, snapshot: ParticipantHomeData): ParticipantHomeState {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return { status: "session_expired" };
    }

    if (error.status === 403) {
      return {
        status: "recoverable_error",
        ...snapshot,
        isRefreshing: false,
        errorKind: "access_lost",
        retryAfterSeconds: null,
        message: "Your study access has changed. Contact your research team.",
      };
    }

    if (error.status === 429) {
      return {
        status: "recoverable_error",
        ...snapshot,
        isRefreshing: false,
        errorKind: "rate_limited",
        retryAfterSeconds: error.retryAfterSeconds,
        message: "Too many requests were made. Please try again shortly.",
      };
    }

    if (error.kind === "network" || error.kind === "timeout") {
      return {
        status: "offline",
        ...snapshot,
        isRefreshing: false,
        message: "You appear to be offline. Check your connection and try again.",
      };
    }
  }

  return {
    status: "recoverable_error",
    ...snapshot,
    isRefreshing: false,
    errorKind: "temporary_service",
    retryAfterSeconds: null,
    message: "The service is temporarily unavailable. Please try again.",
  };
}

export { chooseActiveStudyId };
