import { ApiRequestError } from "../api/client";
import {
  getParticipantActivities,
  getParticipantStudies,
  type ParticipantSessionResponse,
} from "../api/participantApi";
import { ParticipantHomeController, chooseActiveStudyId } from "./participantHomeController";

jest.mock("../api/participantApi", () => ({
  getParticipantStudies: jest.fn(),
  getParticipantActivities: jest.fn(),
}));

const mockedGetParticipantStudies = jest.mocked(getParticipantStudies);
const mockedGetParticipantActivities = jest.mocked(getParticipantActivities);

const session: ParticipantSessionResponse = {
  session: {
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    revocable: true,
  },
  participant: {
    participant_id: 7,
    display_name: "Alex",
    consent_status: "granted",
  },
  study_scope: [11],
};

function deferredPromise<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const studyOne = {
  study_id: 11,
  title: "Study One",
  description: null,
  status: "active",
  methodology: "survey",
  enrolled: true,
} as const;

const studyTwo = {
  study_id: 22,
  title: "Study Two",
  description: null,
  status: "active",
  methodology: "survey",
  enrolled: true,
} as const;

const openActivity = {
  activity_id: 5,
  title: "Entry",
  prompt: null,
  activity_type: "short_text",
  required: true,
  position: 1,
  availability: { status: "open", release_at: null, due_at: null },
} as const;

describe("chooseActiveStudyId", () => {
  it("prefers explicit study selection when present", () => {
    expect(
      chooseActiveStudyId(
        [studyOne, studyTwo],
        [11, 22],
        { preferredStudyId: 22 },
      )
    ).toBe(22);
  });

  it("returns null when multiple studies require participant selection", () => {
    expect(chooseActiveStudyId([studyOne, studyTwo], [11, 22])).toBeNull();
  });
});

describe("ParticipantHomeController", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("automatically selects the only study", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [openActivity],
    });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [openActivity],
      isRefreshing: false,
    });
  });

  it("requires selection when multiple studies are available", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne, studyTwo],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] } });

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne, studyTwo],
      activeStudyId: null,
      requiresStudySelection: true,
      activities: [],
      isRefreshing: false,
    });
    expect(mockedGetParticipantActivities).not.toHaveBeenCalled();
  });

  it("restores the active study when it remains authorised", async () => {
    mockedGetParticipantStudies
      .mockResolvedValueOnce({
        data: [studyOne, studyTwo],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      })
      .mockResolvedValueOnce({
        data: [studyOne, studyTwo],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      });
    mockedGetParticipantActivities.mockResolvedValue({ data: [] });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] }, preferredStudyId: 22 });
    await controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] } });

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne, studyTwo],
      activeStudyId: 22,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    });
  });

  it("drops restored study when it is no longer authorised", async () => {
    mockedGetParticipantStudies
      .mockResolvedValueOnce({
        data: [studyOne, studyTwo],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      })
      .mockResolvedValueOnce({
        data: [studyOne, studyTwo],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      });
    mockedGetParticipantActivities.mockResolvedValue({ data: [] });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] }, preferredStudyId: 22 });
    await controller.load({ accessToken: "token", session: { ...session, study_scope: [11] } });

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne, studyTwo],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    });
  });

  it("surfaces empty state when no studies exist", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "empty",
      participantDisplayName: "Alex",
      studies: [],
      isRefreshing: false,
    });
    expect(mockedGetParticipantActivities).not.toHaveBeenCalled();
  });

  it("returns ready state with no activities when selected study is empty", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({ data: [] });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    });
  });

  it("maps network failure to offline state without expiring session", async () => {
    mockedGetParticipantStudies.mockRejectedValue(
      new ApiRequestError({ status: 0, kind: "network", message: "offline" })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "offline",
      participantDisplayName: undefined,
      studies: [],
      activeStudyId: null,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
      message: "You appear to be offline. Check your connection and try again.",
    });
  });

  it("maps activities network failure to offline state and keeps studies", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockRejectedValue(
      new ApiRequestError({ status: 0, kind: "network", message: "offline" })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "offline",
      participantDisplayName: "Alex",
      studies: [studyOne],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
      message: "You appear to be offline. Check your connection and try again.",
    });
  });

  it("maps studies 401 to session_expired", async () => {
    mockedGetParticipantStudies.mockRejectedValue(
      new ApiRequestError({ status: 401, message: "Unauthorized" })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({ status: "session_expired" });
  });

  it("maps activities 401 to session_expired", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockRejectedValue(
      new ApiRequestError({ status: 401, message: "Unauthorized" })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({ status: "session_expired" });
  });

  it("maps 403 to consent or enrolment loss error", async () => {
    mockedGetParticipantStudies.mockRejectedValue(
      new ApiRequestError({ status: 403, message: "Forbidden" })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "recoverable_error",
      participantDisplayName: undefined,
      studies: [],
      activeStudyId: null,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
      errorKind: "access_lost",
      retryAfterSeconds: null,
      message: "Your study access has changed. Contact your research team.",
    });
  });

  it("maps 429 to rate limit error", async () => {
    mockedGetParticipantStudies.mockRejectedValue(
      new ApiRequestError({ status: 429, message: "Rate limited", retryAfterSeconds: 60 })
    );

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });

    expect(controller.getState()).toEqual({
      status: "recoverable_error",
      participantDisplayName: undefined,
      studies: [],
      activeStudyId: null,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
      errorKind: "rate_limited",
      retryAfterSeconds: 60,
      message: "Too many requests were made. Please try again shortly.",
    });
  });

  it("refreshes successfully while preserving selected study", async () => {
    mockedGetParticipantStudies
      .mockResolvedValueOnce({
        data: [studyOne],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      })
      .mockResolvedValueOnce({
        data: [studyOne],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      });
    mockedGetParticipantActivities
      .mockResolvedValueOnce({ data: [openActivity] })
      .mockResolvedValueOnce({
        data: [
          {
            ...openActivity,
            activity_id: 9,
            title: "Follow-up",
            availability: { status: "upcoming", release_at: "2030-01-01T10:00:00Z", due_at: null },
          },
        ],
      });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });
    await controller.refresh();

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [
        {
          ...openActivity,
          activity_id: 9,
          title: "Follow-up",
          availability: { status: "upcoming", release_at: "2030-01-01T10:00:00Z", due_at: null },
        },
      ],
      isRefreshing: false,
    });
  });

  it("preserves existing content when refresh fails", async () => {
    mockedGetParticipantStudies
      .mockResolvedValueOnce({
        data: [studyOne],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      })
      .mockRejectedValueOnce(new ApiRequestError({ status: 0, kind: "network", message: "offline" }));
    mockedGetParticipantActivities.mockResolvedValue({ data: [openActivity] });

    const controller = new ParticipantHomeController();
    await controller.load({ accessToken: "token", session });
    await controller.refresh();

    expect(controller.getState()).toEqual({
      status: "offline",
      participantDisplayName: "Alex",
      studies: [studyOne],
      activeStudyId: 11,
      requiresStudySelection: false,
      activities: [openActivity],
      isRefreshing: false,
      message: "You appear to be offline. Check your connection and try again.",
    });
  });

  it("ignores stale results from a superseded load", async () => {
    const firstStudies = deferredPromise<Awaited<ReturnType<typeof getParticipantStudies>>>();
    mockedGetParticipantStudies
      .mockImplementationOnce(() => firstStudies.promise)
      .mockResolvedValueOnce({
        data: [studyTwo],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      });
    mockedGetParticipantActivities.mockResolvedValue({ data: [] });

    const controller = new ParticipantHomeController();
    const firstLoad = controller.load({ accessToken: "token", session });
    const secondLoad = controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] }, preferredStudyId: 22 });

    firstStudies.resolve({
      data: [
        {
          ...studyOne,
          title: "Old Study",
        },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    await Promise.all([firstLoad, secondLoad]);

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyTwo],
      activeStudyId: 22,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    });
  });

  it("handles rapid study switching with last selection winning", async () => {
    const firstActivities = deferredPromise<Awaited<ReturnType<typeof getParticipantActivities>>>();
    mockedGetParticipantStudies.mockResolvedValue({
      data: [studyOne, studyTwo],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockImplementation(async (_token, studyId) => {
      if (studyId === 11) {
        return firstActivities.promise;
      }

      return {
        data: [{ ...openActivity, activity_id: 99, title: "Latest" }],
      };
    });

    const controller = new ParticipantHomeController();
    const first = controller.load({ accessToken: "token", session: { ...session, study_scope: [11, 22] }, preferredStudyId: 11 });
    const second = controller.selectStudy(22);

    firstActivities.resolve({
      data: [{ ...openActivity, title: "Stale activity" }],
    });

    await Promise.all([first, second]);

    expect(controller.getState()).toEqual({
      status: "ready",
      participantDisplayName: "Alex",
      studies: [studyOne, studyTwo],
      activeStudyId: 22,
      requiresStudySelection: false,
      activities: [{ ...openActivity, activity_id: 99, title: "Latest" }],
      isRefreshing: false,
    });
  });

  it("stops state updates after destroy while request is pending", async () => {
    const studies = deferredPromise<Awaited<ReturnType<typeof getParticipantStudies>>>();
    mockedGetParticipantStudies.mockImplementationOnce(() => studies.promise);

    const controller = new ParticipantHomeController();
    const run = controller.load({ accessToken: "token", session });
    controller.destroy();

    studies.resolve({
      data: [studyOne],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    await run;
    expect(controller.getState()).toEqual({
      status: "loading",
      participantDisplayName: "Alex",
      studies: [],
      activeStudyId: null,
      requiresStudySelection: false,
      activities: [],
      isRefreshing: false,
    });
  });
});
