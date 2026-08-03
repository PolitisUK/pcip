import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { ApiRequestError } from "../api/client";
import {
  getCurrentSession,
  getParticipantActivities,
  getParticipantActivityDetail,
  getParticipantStudies,
  saveParticipantActivityDraft,
  submitParticipantActivityResponse,
  type ParticipantSessionResponse,
} from "../api/participantApi";
import { loadSessionMaterial } from "../services/sessionStore";
import { HomeScreen } from "./HomeScreen";

jest.mock("../services/sessionStore", () => ({
  loadSessionMaterial: jest.fn(),
}));

jest.mock("../api/participantApi", () => ({
  getCurrentSession: jest.fn(),
  getParticipantStudies: jest.fn(),
  getParticipantActivities: jest.fn(),
  getParticipantActivityDetail: jest.fn(),
  saveParticipantActivityDraft: jest.fn(),
  submitParticipantActivityResponse: jest.fn(),
}));

const mockedLoadSessionMaterial = jest.mocked(loadSessionMaterial);
const mockedGetCurrentSession = jest.mocked(getCurrentSession);
const mockedGetParticipantStudies = jest.mocked(getParticipantStudies);
const mockedGetParticipantActivities = jest.mocked(getParticipantActivities);
const mockedGetParticipantActivityDetail = jest.mocked(getParticipantActivityDetail);
const mockedSaveParticipantActivityDraft = jest.mocked(saveParticipantActivityDraft);
const mockedSubmitParticipantActivityResponse = jest.mocked(submitParticipantActivityResponse);

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

const sessionMaterial = {
  accessToken: "token",
  expiresAt: new Date(Date.now() + 60_000).toISOString(),
  participantId: 7,
  participantDisplayName: "Alex",
  consentStatus: "granted" as const,
  studyScope: [11],
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

async function renderHome(overrides?: {
  onSignOut?: () => void;
  onSessionExpired?: () => void;
}) {
  const onSignOut = overrides?.onSignOut || jest.fn();
  const onSessionExpired = overrides?.onSessionExpired || jest.fn();

  const screen = render(
    <HomeScreen
      participantDisplayName="Alex"
      onSignOut={onSignOut}
      onSessionExpired={onSessionExpired}
    />,
  );

  return { ...screen, onSignOut, onSessionExpired };
}

describe("HomeScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedLoadSessionMaterial.mockResolvedValue(sessionMaterial);
    mockedGetCurrentSession.mockResolvedValue(session);
    mockedSaveParticipantActivityDraft.mockResolvedValue({
      response_id: 44,
      status: "draft",
      updated_at: "2030-01-01T10:00:00Z",
    });
    mockedSubmitParticipantActivityResponse.mockResolvedValue({
      response_id: 44,
      status: "submitted",
      submitted_at: "2030-01-01T11:00:00Z",
      updated_at: "2030-01-01T11:00:00Z",
    });
  });

  it("shows loading copy while studies are being fetched", async () => {
    const studies = deferredPromise<Awaited<ReturnType<typeof getParticipantStudies>>>();
    mockedGetParticipantStudies.mockImplementationOnce(() => studies.promise);

    const { getByText } = await renderHome();

    await waitFor(() => {
      expect(getByText("Loading your studies")).toBeTruthy();
    });
  });

  it("renders authenticated compact logo", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    const { getByTestId } = await renderHome();

    await waitFor(() => {
      expect(getByTestId("citizen-centric-logo-compact")).toBeTruthy();
    });
  });

  it("renders multiple-study selection when selection is required", async () => {
    mockedGetCurrentSession.mockResolvedValue({ ...session, study_scope: [11, 22] });
    mockedLoadSessionMaterial.mockResolvedValue({ ...sessionMaterial, studyScope: [11, 22] });
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
        { study_id: 22, title: "Study Two", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    const { getByText, getByLabelText } = await renderHome();

    await waitFor(() => {
      expect(getByText("Choose a study")).toBeTruthy();
      expect(getByLabelText("Select study Study One")).toBeTruthy();
      expect(getByLabelText("Select study Study Two")).toBeTruthy();
    });
  });

  it("renders grouped activity sections", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 1,
          title: "Available task",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
        {
          activity_id: 2,
          title: "Upcoming task",
          prompt: null,
          activity_type: "short_text",
          required: false,
          position: 2,
          availability: { status: "upcoming", release_at: "2030-01-01T10:00:00Z", due_at: null },
        },
        {
          activity_id: 3,
          title: "Completed task",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 3,
          availability: { status: "closed", release_at: null, due_at: "2030-01-02T10:00:00Z" },
        },
      ],
    });

    const { getByText } = await renderHome();

    await waitFor(() => {
      expect(getByText("Available")).toBeTruthy();
      expect(getByText("Upcoming")).toBeTruthy();
      expect(getByText("Completed")).toBeTruthy();
    });
  });

  it("shows empty studies copy", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });

    const { getByText } = await renderHome();

    await waitFor(() => {
      expect(getByText("No studies are available yet.")).toBeTruthy();
    });
  });

  it("shows empty activities copy", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({ data: [] });

    const { getByText } = await renderHome();

    await waitFor(() => {
      expect(getByText("There are no activities in this study yet.")).toBeTruthy();
    });
  });

  it("shows offline copy and retries", async () => {
    mockedGetParticipantStudies
      .mockRejectedValueOnce(new ApiRequestError({ status: 0, kind: "network", message: "offline" }))
      .mockResolvedValueOnce({
        data: [],
        pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
      });

    const { getByText, getByLabelText } = await renderHome();

    await waitFor(() => {
      expect(getByText("You appear to be offline.")).toBeTruthy();
    });

    fireEvent.press(getByLabelText("Retry"));

    await waitFor(() => {
      expect(getByText("No studies are available yet.")).toBeTruthy();
    });
  });

  it("uses a combined accessibility label on activity cards", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
          response: { status: "draft", updated_at: "2030-01-01T10:00:00Z" },
        },
      ],
    });

    const { getByLabelText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available. Draft saved./)).toBeTruthy();
    });
  });

  it("opens activity detail and renders successful detail response", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });

    const detail = deferredPromise<Awaited<ReturnType<typeof getParticipantActivityDetail>>>();
    mockedGetParticipantActivityDetail.mockImplementationOnce(() => detail.promise);

    const { getByLabelText, getByText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));

    await waitFor(() => {
      expect(getByText("Loading activity details.")).toBeTruthy();
    });

    detail.resolve({
      activity: {
        activity_id: 5,
        title: "Mood check",
        prompt: "Tell us how your week was.",
        activity_type: "short_text",
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });

    await waitFor(() => {
      expect(getByText("Activity details")).toBeTruthy();
      expect(getByText("Mood check")).toBeTruthy();
      expect(getByText("Tell us how your week was.")).toBeTruthy();
      expect(getByText(/Response:\s*Not started/)).toBeTruthy();
    });
  });

  it("saves a text response draft explicitly", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Mood check",
        prompt: "Tell us how your week was.",
        activity_type: "short_text",
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });

    const { getByLabelText, getByText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));

    await waitFor(() => {
      expect(getByLabelText("Response for Mood check")).toBeTruthy();
    });

    fireEvent.changeText(getByLabelText("Response for Mood check"), "A calmer journey");
    fireEvent.press(getByLabelText("Save draft response"));

    await waitFor(() => {
      expect(mockedSaveParticipantActivityDraft).toHaveBeenCalledWith(
        "token",
        5,
        { answer: "A calmer journey", choices: [], evidence_id: undefined },
        expect.objectContaining({ idempotencyKey: expect.any(String) }),
      );
      expect(getByText("Draft saved.")).toBeTruthy();
    });
  });

  it("renders single-choice options and submits after confirmation", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Travel mode",
          prompt: null,
          activity_type: "single_choice",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Travel mode",
        prompt: "Choose one option.",
        activity_type: "single_choice",
        options: ["Bus", "Train", "Walk"],
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });

    const { getByLabelText, getByText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Travel mode. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Travel mode. Available./));

    await waitFor(() => {
      expect(getByLabelText("Select option Train")).toBeTruthy();
    });

    fireEvent.press(getByLabelText("Select option Train"));
    fireEvent.press(getByLabelText("Review response before submitting"));

    await waitFor(() => {
      expect(getByText("You will not be able to edit this response after submission.")).toBeTruthy();
    });

    fireEvent.press(getByLabelText("Confirm submit response"));

    await waitFor(() => {
      expect(mockedSubmitParticipantActivityResponse).toHaveBeenCalledWith(
        "token",
        5,
        { answer: "", choices: ["Train"], evidence_id: undefined },
        expect.objectContaining({ idempotencyKey: expect.any(String) }),
      );
      expect(getByText("Submitted response")).toBeTruthy();
      expect(getByText("Selected: Train")).toBeTruthy();
    });
  });

  it("renders multiple-choice options and saves selected choices in option order", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Street issues",
          prompt: null,
          activity_type: "multiple_choice",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Street issues",
        prompt: "Choose all that apply.",
        activity_type: "multiple_choice",
        options: ["Lighting", "Crossing", "Pavement width"],
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });

    const { getByLabelText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Street issues. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Street issues. Available./));

    await waitFor(() => {
      expect(getByLabelText("Toggle option Pavement width")).toBeTruthy();
    });

    fireEvent.press(getByLabelText("Toggle option Pavement width"));
    fireEvent.press(getByLabelText("Toggle option Lighting"));
    fireEvent.press(getByLabelText("Save draft response"));

    await waitFor(() => {
      expect(mockedSaveParticipantActivityDraft).toHaveBeenCalledWith(
        "token",
        5,
        { answer: "", choices: ["Lighting", "Pavement width"], evidence_id: undefined },
        expect.objectContaining({ idempotencyKey: expect.any(String) }),
      );
    });
  });

  it("keeps submitted responses read-only", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
          response: { status: "submitted", updated_at: "2030-01-01T10:00:00Z", submitted_at: "2030-01-01T10:00:00Z" },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Mood check",
        prompt: "Tell us how your week was.",
        activity_type: "short_text",
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
      response: {
        response_id: 33,
        status: "submitted",
        submitted_at: "2030-01-01T10:00:00Z",
        updated_at: "2030-01-01T10:00:00Z",
        value: { answer: "Already sent" },
      },
    });

    const { getByLabelText, getByText, queryByLabelText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));

    await waitFor(() => {
      expect(getByText("Submitted response")).toBeTruthy();
      expect(getByText("Already sent")).toBeTruthy();
    });

    expect(queryByLabelText("Save draft response")).toBeNull();
    expect(queryByLabelText("Review response before submitting")).toBeNull();
  });

  it("shows offline save errors and keeps the draft editable", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Mood check",
        prompt: "Tell us how your week was.",
        activity_type: "short_text",
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });
    mockedSaveParticipantActivityDraft.mockRejectedValueOnce(
      new ApiRequestError({ status: 0, kind: "network", message: "offline" }),
    );

    const { getByLabelText, getByText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));
    await waitFor(() => {
      expect(getByLabelText("Response for Mood check")).toBeTruthy();
    });

    fireEvent.changeText(getByLabelText("Response for Mood check"), "Still editing");
    fireEvent.press(getByLabelText("Save draft response"));

    await waitFor(() => {
      expect(getByText("You appear to be offline. Check your connection and try again.")).toBeTruthy();
      expect(getByText("Unsaved changes")).toBeTruthy();
    });
  });

  it("returns control to auth flow when saving a draft gets 401", async () => {
    const onSessionExpired = jest.fn();
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockResolvedValue({
      activity: {
        activity_id: 5,
        title: "Mood check",
        prompt: "Tell us how your week was.",
        activity_type: "short_text",
        required: true,
        position: 1,
        availability: { status: "open", release_at: null, due_at: null },
      },
    });
    mockedSaveParticipantActivityDraft.mockRejectedValueOnce(
      new ApiRequestError({ status: 401, message: "Unauthorized" }),
    );

    const { getByLabelText } = await renderHome({ onSessionExpired });

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));
    await waitFor(() => {
      expect(getByLabelText("Response for Mood check")).toBeTruthy();
    });

    fireEvent.changeText(getByLabelText("Response for Mood check"), "Will expire");
    fireEvent.press(getByLabelText("Save draft response"));

    await waitFor(() => {
      expect(onSessionExpired).toHaveBeenCalledTimes(1);
    });
  });

  it("shows detail failure state", async () => {
    mockedGetParticipantStudies.mockResolvedValue({
      data: [
        { study_id: 11, title: "Study One", description: null, status: "active", methodology: "survey", enrolled: true },
      ],
      pagination: { cursor: null, next_cursor: null, limit: 25, has_more: false },
    });
    mockedGetParticipantActivities.mockResolvedValue({
      data: [
        {
          activity_id: 5,
          title: "Mood check",
          prompt: null,
          activity_type: "short_text",
          required: true,
          position: 1,
          availability: { status: "open", release_at: null, due_at: null },
        },
      ],
    });
    mockedGetParticipantActivityDetail.mockRejectedValueOnce(
      new ApiRequestError({ status: 0, kind: "network", message: "offline" }),
    );

    const { getByLabelText, getByText } = await renderHome();

    await waitFor(() => {
      expect(getByLabelText(/Mood check. Available./)).toBeTruthy();
    });

    fireEvent.press(getByLabelText(/Mood check. Available./));

    await waitFor(() => {
      expect(getByText("You appear to be offline. Check your connection and try again.")).toBeTruthy();
    });
  });

  it("returns control to auth flow when session is expired", async () => {
    const onSessionExpired = jest.fn();
    mockedGetCurrentSession.mockRejectedValueOnce(
      new ApiRequestError({ status: 401, message: "Unauthorized" }),
    );

    await renderHome({ onSessionExpired });

    await waitFor(() => {
      expect(onSessionExpired).toHaveBeenCalledTimes(1);
    });
  });
});
