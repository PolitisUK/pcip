import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import * as Linking from "expo-linking";

import { ApiRequestError } from "../api/client";
import {
  createParticipantMessage,
  getParticipantMessages,
  getParticipantEvidenceStatus,
  getCurrentSession,
  getParticipantActivityDetail,
  requestParticipantDeletion,
  requestParticipantWithdrawal,
  saveParticipantActivityDraft,
  submitParticipantActivityResponse,
  uploadParticipantActivityEvidence,
  type CreateMessageResponse,
  type ActivityDetailResponse,
  type EvidenceMetadata,
  type DraftResponseRequest,
  type MessageListResponse,
} from "../api/participantApi";
import { CitizenCentricLogo } from "../components/CitizenCentricLogo";
import { env } from "../config/env";
import {
  disablePushNotificationsLocally,
  loadNotificationPreferences,
  registerForPushNotifications,
} from "../services/pushNotifications";
import { loadSessionMaterial } from "../services/sessionStore";
import { ParticipantHomeController } from "../studies/participantHomeController";
import type { ActivitySummary, ParticipantHomeState } from "../studies/types";

type HomeScreenProps = {
  participantDisplayName?: string;
  onSignOut: () => void;
  onSessionExpired: () => void;
};

type EditableResponseDraft = {
  answer: string;
  choices: string[];
  evidenceId: number | null;
};

type EditorMessage = {
  tone: "success" | "error";
  text: string;
};

type EvidenceAsset = {
  localUri: string;
  filename: string;
  contentType: string;
  size: number | null;
};

type EvidencePreview = {
  kind: "image" | "video" | "audio" | "document";
  uri: string;
  label: string;
};

type EvidenceWorkflowState = {
  status: "idle" | "uploading" | "polling" | "clean" | "rejected" | "failed";
  progressRatio: number;
  evidenceId: number | null;
  scanStatus: "pending" | "clean" | "infected" | "scan_failed" | null;
  scanDetail: string | null;
  selectedAsset: EvidenceAsset | null;
  preview: EvidencePreview | null;
  uploadSignature: string | null;
};

type ActivityEditorState = {
  draft: EditableResponseDraft;
  persisted: EditableResponseDraft;
  actionStatus: "idle" | "saving" | "submitting";
  confirmingSubmit: boolean;
  message: EditorMessage | null;
  evidence: EvidenceWorkflowState;
};

type ActivityDetailViewState =
  | { status: "idle" }
  | { status: "loading"; activityId: number }
  | { status: "ready"; activityId: number; detail: ActivityDetailResponse; editor: ActivityEditorState }
  | { status: "error"; activityId: number; message: string };

type HomePanel = "home" | "account" | "messages";

type MessagesPanelState = {
  status: "idle" | "loading" | "ready" | "error";
  items: MessageListResponse["data"];
  selectedThreadId: string | null;
  composeBody: string;
  sending: boolean;
  message: EditorMessage | null;
};

type AccountPanelState = {
  withdrawing: boolean;
  deleting: boolean;
  confirmWithdraw: boolean;
  confirmDelete: boolean;
  notificationsBusy: boolean;
  notificationsEnabled: boolean;
  notificationsUpdatedAt: string | null;
  message: EditorMessage | null;
};

const dateLabel = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function HomeScreen({ participantDisplayName, onSignOut, onSessionExpired }: HomeScreenProps) {
  const controller = useMemo(() => new ParticipantHomeController(), []);
  const [homeState, setHomeState] = useState<ParticipantHomeState>({ status: "initialising" });
  const accessTokenRef = useRef<string | null>(null);
  const [sessionEnding, setSessionEnding] = useState(false);
  const [detailState, setDetailState] = useState<ActivityDetailViewState>({ status: "idle" });
  const [homePanel, setHomePanel] = useState<HomePanel>("home");
  const [consentStatus, setConsentStatus] = useState<string>("granted");
  const [messagesState, setMessagesState] = useState<MessagesPanelState>({
    status: "idle",
    items: [],
    selectedThreadId: null,
    composeBody: "",
    sending: false,
    message: null,
  });
  const [accountState, setAccountState] = useState<AccountPanelState>({
    withdrawing: false,
    deleting: false,
    confirmWithdraw: false,
    confirmDelete: false,
    notificationsBusy: false,
    notificationsEnabled: false,
    notificationsUpdatedAt: null,
    message: null,
  });
  const detailRequestVersion = useRef(0);
  const detailAbortController = useRef<AbortController | null>(null);
  const writeRequestVersion = useRef(0);
  const writeAbortController = useRef<AbortController | null>(null);
  const evidenceRequestVersion = useRef(0);
  const evidenceAbortController = useRef<AbortController | null>(null);
  const evidencePollTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesRequestVersion = useRef(0);
  const messagesAbortController = useRef<AbortController | null>(null);

  useEffect(() => {
    const unsubscribe = controller.subscribe((state) => {
      setHomeState(state);
    });

    return () => {
      unsubscribe();
    };
  }, [controller]);

  useEffect(() => {
    let active = true;

    const initialise = async () => {
      const sessionMaterial = await loadSessionMaterial();
      if (!active) {
        return;
      }

      if (!sessionMaterial || Date.parse(sessionMaterial.expiresAt) <= Date.now()) {
        onSessionExpired();
        return;
      }

      const token = sessionMaterial.accessToken;
      accessTokenRef.current = token;

      try {
        const session = await getCurrentSession(token);
        if (!active) {
          return;
        }

        setConsentStatus(session.participant.consent_status);

        await controller.load({
          accessToken: token,
          session,
          preferredStudyId: sessionMaterial.studyScope?.[0],
        });
      } catch (error) {
        if (!active) {
          return;
        }

        if (error instanceof ApiRequestError && (error.status === 401 || error.status === 403)) {
          onSessionExpired();
          return;
        }

        await controller.load({
          accessToken: token,
          session: {
            session: {
              expires_at: sessionMaterial.expiresAt,
              revocable: true,
            },
            participant: {
              display_name: sessionMaterial.participantDisplayName || participantDisplayName || "Participant",
              consent_status: sessionMaterial.consentStatus || "granted",
            },
            invitation: {
              study_id: sessionMaterial.studyScope?.[0] ?? 0,
              invitation_status: "accepted",
              expires_at: sessionMaterial.expiresAt,
              accepted_at: sessionMaterial.expiresAt,
              requires_study_documents: false,
            },
            next_action: "portal",
            study_scope: sessionMaterial.studyScope || [],
          },
          preferredStudyId: sessionMaterial.studyScope?.[0],
        });
        setConsentStatus(sessionMaterial.consentStatus || "granted");
      }
    };

    void initialise();

    return () => {
      active = false;
      controller.destroy();
      detailAbortController.current?.abort();
      detailAbortController.current = null;
      writeAbortController.current?.abort();
      writeAbortController.current = null;
      evidenceAbortController.current?.abort();
      evidenceAbortController.current = null;
      if (evidencePollTimeout.current) {
        clearTimeout(evidencePollTimeout.current);
        evidencePollTimeout.current = null;
      }
      messagesAbortController.current?.abort();
      messagesAbortController.current = null;
    };
  }, [controller, onSessionExpired, participantDisplayName]);

  useEffect(() => {
    if (homeState.status === "session_expired") {
      onSessionExpired();
    }
  }, [homeState, onSessionExpired]);

  useEffect(() => {
    let active = true;
    const loadPreferences = async () => {
      const preferences = await loadNotificationPreferences();
      if (!active || !preferences) {
        return;
      }
      setAccountState((current) => ({
        ...current,
        notificationsEnabled: preferences.enabled,
        notificationsUpdatedAt: preferences.updatedAt,
      }));
    };
    void loadPreferences();

    return () => {
      active = false;
    };
  }, []);

  const participantName = resolveParticipantName(homeState, participantDisplayName);
  const activeStudyTitle = hasJourneyData(homeState)
    ? homeState.studies.find((study) => study.study_id === homeState.activeStudyId)?.title || "No study selected"
    : "No study selected";
  const consentLabel = readableConsentStatus(consentStatus);

  const updateReadyDetail = (
    updater: (state: Extract<ActivityDetailViewState, { status: "ready" }>) => Extract<ActivityDetailViewState, { status: "ready" }>,
  ) => {
    setDetailState((current) => (current.status === "ready" ? updater(current) : current));
  };

  const clearEvidencePollTimer = () => {
    if (evidencePollTimeout.current) {
      clearTimeout(evidencePollTimeout.current);
      evidencePollTimeout.current = null;
    }
  };

  const beginEvidenceRequest = () => {
    evidenceRequestVersion.current += 1;
    const requestVersion = evidenceRequestVersion.current;
    clearEvidencePollTimer();
    evidenceAbortController.current?.abort();
    const requestController = new AbortController();
    evidenceAbortController.current = requestController;
    return { requestVersion, signal: requestController.signal };
  };

  const cancelEvidenceOperations = (message?: EditorMessage) => {
    evidenceRequestVersion.current += 1;
    clearEvidencePollTimer();
    evidenceAbortController.current?.abort();
    evidenceAbortController.current = null;

    if (!message) {
      return;
    }

    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        message,
      },
    }));
  };

  const applyEvidenceStatus = (
    activityId: number,
    metadata: EvidenceMetadata,
    requestVersion: number,
  ) => {
    if (requestVersion !== evidenceRequestVersion.current) {
      return;
    }

    const normalized = normalizeEvidenceScanStatus(metadata.scan_status);
    updateReadyDetail((current) => {
      if (current.activityId !== activityId) {
        return current;
      }

      const currentEvidenceId = current.editor.draft.evidenceId;
      const nextEvidenceId = normalized === "clean"
        ? metadata.evidence_id
        : (currentEvidenceId === metadata.evidence_id ? null : currentEvidenceId);

      const nextStatus = normalized === "clean"
        ? "clean"
        : normalized === "infected"
          ? "rejected"
          : normalized === "scan_failed"
            ? "failed"
            : "polling";

      return {
        ...current,
        editor: {
          ...current.editor,
          draft: {
            ...current.editor.draft,
            evidenceId: nextEvidenceId,
          },
          evidence: {
            ...current.editor.evidence,
            status: nextStatus,
            progressRatio: nextStatus === "clean" ? 1 : current.editor.evidence.progressRatio,
            evidenceId: metadata.evidence_id,
            scanStatus: normalized,
            scanDetail: null,
          },
          message: normalized === "clean"
            ? { tone: "success", text: "Evidence scan is clean and ready to attach." }
            : normalized === "infected"
              ? { tone: "error", text: "Evidence was rejected by malware screening." }
              : normalized === "scan_failed"
                ? { tone: "error", text: "Evidence scan failed. Please retry the upload." }
                : current.editor.message,
        },
      };
    });
  };

  const pollEvidenceStatus = async (
    activityId: number,
    evidenceId: number,
    requestVersion: number,
    attempt: number,
  ) => {
    if (requestVersion !== evidenceRequestVersion.current) {
      return;
    }

    if (attempt > 24) {
      updateReadyDetail((current) => {
        if (current.activityId !== activityId) {
          return current;
        }

        return {
          ...current,
          editor: {
            ...current.editor,
            evidence: {
              ...current.editor.evidence,
              status: "failed",
            },
            message: {
              tone: "error",
              text: "Evidence scan is taking longer than expected. You can retry status check.",
            },
          },
        };
      });
      return;
    }

    const accessToken = accessTokenRef.current;
    if (!accessToken) {
      return;
    }

    try {
      const status = await getParticipantEvidenceStatus(accessToken, evidenceId, {
        signal: evidenceAbortController.current?.signal,
      });

      if (requestVersion !== evidenceRequestVersion.current) {
        return;
      }

      applyEvidenceStatus(activityId, status.evidence, requestVersion);
      if (status.evidence.scan_status === "pending") {
        clearEvidencePollTimer();
        evidencePollTimeout.current = setTimeout(() => {
          void pollEvidenceStatus(activityId, evidenceId, requestVersion, attempt + 1);
        }, 2500);
      }
    } catch (error) {
      if (requestVersion !== evidenceRequestVersion.current) {
        return;
      }

      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }

      updateReadyDetail((current) => {
        if (current.activityId !== activityId) {
          return current;
        }

        return {
          ...current,
          editor: {
            ...current.editor,
            evidence: {
              ...current.editor.evidence,
              status: "failed",
            },
            message: {
              tone: "error",
              text: mapEvidenceActionError(error),
            },
          },
        };
      });
    }
  };

  const refreshEvidenceStatus = async (activityId: number, evidenceId: number) => {
    const { requestVersion } = beginEvidenceRequest();

    updateReadyDetail((current) => {
      if (current.activityId !== activityId) {
        return current;
      }

      return {
        ...current,
        editor: {
          ...current.editor,
          evidence: {
            ...current.editor.evidence,
            status: "polling",
            evidenceId,
            scanStatus: "pending",
          },
        },
      };
    });

    await pollEvidenceStatus(activityId, evidenceId, requestVersion, 0);
  };

  const openActivityDetail = async (activityId: number) => {
    const accessToken = accessTokenRef.current;
    if (!accessToken) {
      return;
    }

    detailRequestVersion.current += 1;
    const requestVersion = detailRequestVersion.current;

    detailAbortController.current?.abort();
    const controllerForDetail = new AbortController();
    detailAbortController.current = controllerForDetail;

    setDetailState({ status: "loading", activityId });

    try {
      const detail = await getParticipantActivityDetail(accessToken, activityId, {
        signal: controllerForDetail.signal,
      });

      if (requestVersion !== detailRequestVersion.current) {
        return;
      }

      setDetailState({ status: "ready", activityId, detail, editor: createActivityEditorState(detail) });
      const existingEvidenceId = detail.response?.value?.evidence_id;
      if (typeof existingEvidenceId === "number") {
        void refreshEvidenceStatus(activityId, existingEvidenceId);
      } else {
        cancelEvidenceOperations();
      }
    } catch (error) {
      if (requestVersion !== detailRequestVersion.current) {
        return;
      }

      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }

      if (error instanceof ApiRequestError && (error.kind === "network" || error.kind === "timeout")) {
        setDetailState({
          status: "error",
          activityId,
          message: "You appear to be offline. Check your connection and try again.",
        });
        return;
      }

      setDetailState({
        status: "error",
        activityId,
        message: "We could not load this activity right now. Please try again.",
      });
    }
  };

  const updateDraft = (updater: (draft: EditableResponseDraft, detail: ActivityDetailResponse) => EditableResponseDraft) => {
    updateReadyDetail((current) => {
      if (isSubmittedResponse(current.detail.response?.status)) {
        return current;
      }

      const nextDraft = normalizeEditableResponseDraft(updater(current.editor.draft, current.detail), current.detail.activity);
      return {
        ...current,
        editor: {
          ...current.editor,
          draft: nextDraft,
          confirmingSubmit: false,
          message: current.editor.message?.tone === "error" ? current.editor.message : null,
        },
      };
    });
  };

  const beginWriteRequest = () => {
    writeRequestVersion.current += 1;
    const requestVersion = writeRequestVersion.current;
    writeAbortController.current?.abort();
    const requestController = new AbortController();
    writeAbortController.current = requestController;

    return { requestVersion, signal: requestController.signal };
  };

  const handleDetailActionError = async (error: unknown, activityId: number, action: "save" | "submit") => {
    if (error instanceof ApiRequestError && error.status === 401) {
      onSessionExpired();
      return;
    }

    if (error instanceof ApiRequestError && error.status === 409) {
      await openActivityDetail(activityId);
      return;
    }

    const message = mapDetailActionError(error, action);
    setDetailState((current) => {
      if (current.status !== "ready" || current.activityId !== activityId) {
        return current;
      }

      return {
        ...current,
        editor: {
          ...current.editor,
          actionStatus: "idle",
          message: { tone: "error", text: message },
        },
      };
    });
  };

  const persistDraft = async () => {
    const accessToken = accessTokenRef.current;
    if (!accessToken || detailState.status !== "ready" || isSubmittedResponse(detailState.detail.response?.status)) {
      return;
    }

    const payload = buildDraftRequest(detailState.detail, detailState.editor.draft);
    const { requestVersion, signal } = beginWriteRequest();

    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        actionStatus: "saving",
        confirmingSubmit: false,
        message: null,
      },
    }));

    try {
      const result = await saveParticipantActivityDraft(accessToken, detailState.activityId, payload, {
        signal,
        idempotencyKey: createIdempotencyKey("draft", detailState.activityId),
      });

      if (requestVersion !== writeRequestVersion.current) {
        return;
      }

      updateReadyDetail((current) => {
        const persisted = normalizeEditableResponseDraft(current.editor.draft, current.detail.activity);

        return {
          ...current,
          detail: {
            ...current.detail,
            response: {
              response_id: result.response_id,
              status: "draft",
              updated_at: result.updated_at,
              value: toResponseValue(persisted),
            },
          },
          editor: {
            ...current.editor,
            draft: persisted,
            persisted,
            actionStatus: "idle",
            message: { tone: "success", text: "Draft saved." },
          },
        };
      });
    } catch (error) {
      if (requestVersion !== writeRequestVersion.current) {
        return;
      }

      await handleDetailActionError(error, detailState.activityId, "save");
    }
  };

  const submitResponse = async () => {
    const accessToken = accessTokenRef.current;
    if (!accessToken || detailState.status !== "ready" || isSubmittedResponse(detailState.detail.response?.status)) {
      return;
    }

    const payload = buildDraftRequest(detailState.detail, detailState.editor.draft);
    const { requestVersion, signal } = beginWriteRequest();

    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        actionStatus: "submitting",
        confirmingSubmit: false,
        message: null,
      },
    }));

    try {
      const result = await submitParticipantActivityResponse(accessToken, detailState.activityId, payload, {
        signal,
        idempotencyKey: createIdempotencyKey("submit", detailState.activityId),
      });

      if (requestVersion !== writeRequestVersion.current) {
        return;
      }

      updateReadyDetail((current) => {
        const persisted = normalizeEditableResponseDraft(current.editor.draft, current.detail.activity);

        return {
          ...current,
          detail: {
            ...current.detail,
            response: {
              response_id: result.response_id,
              status: "submitted",
              submitted_at: result.submitted_at,
              updated_at: result.updated_at,
              value: toResponseValue(persisted),
            },
          },
          editor: {
            ...current.editor,
            draft: persisted,
            persisted,
            actionStatus: "idle",
            message: { tone: "success", text: "Response submitted." },
          },
        };
      });
    } catch (error) {
      if (requestVersion !== writeRequestVersion.current) {
        return;
      }

      await handleDetailActionError(error, detailState.activityId, "submit");
    }
  };

  const uploadEvidenceAsset = async (asset: EvidenceAsset) => {
    const accessToken = accessTokenRef.current;
    if (!accessToken || detailState.status !== "ready" || isSubmittedResponse(detailState.detail.response?.status)) {
      return;
    }

    const signature = evidenceAssetSignature(asset);
    const currentEvidence = detailState.editor.evidence;
    if (currentEvidence.uploadSignature === signature && ["uploading", "polling", "clean"].includes(currentEvidence.status)) {
      updateReadyDetail((current) => ({
        ...current,
        editor: {
          ...current.editor,
          message: { tone: "error", text: "This evidence is already attached or uploading." },
        },
      }));
      return;
    }

    const { requestVersion, signal } = beginEvidenceRequest();
    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        evidence: {
          ...current.editor.evidence,
          status: "uploading",
          progressRatio: 0,
          evidenceId: null,
          scanStatus: null,
          scanDetail: null,
          selectedAsset: asset,
          preview: evidencePreviewFromAsset(asset),
          uploadSignature: signature,
        },
        draft: {
          ...current.editor.draft,
          evidenceId: null,
        },
        message: null,
      },
    }));

    try {
      const upload = await uploadParticipantActivityEvidence(accessToken, detailState.activityId, {
        localUri: asset.localUri,
        filename: asset.filename,
        contentType: asset.contentType,
        onProgress: (ratio) => {
          if (requestVersion !== evidenceRequestVersion.current) {
            return;
          }
          updateReadyDetail((current) => ({
            ...current,
            editor: {
              ...current.editor,
              evidence: {
                ...current.editor.evidence,
                progressRatio: ratio,
              },
            },
          }));
        },
      }, {
        signal,
        idempotencyKey: createIdempotencyKey("evidence", detailState.activityId),
        timeoutMs: 45000,
      });

      if (requestVersion !== evidenceRequestVersion.current) {
        return;
      }

      applyEvidenceStatus(detailState.activityId, upload.evidence, requestVersion);
      if (upload.evidence.scan_status === "pending") {
        await pollEvidenceStatus(detailState.activityId, upload.evidence.evidence_id, requestVersion, 0);
      }
    } catch (error) {
      if (requestVersion !== evidenceRequestVersion.current) {
        return;
      }

      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }

      updateReadyDetail((current) => ({
        ...current,
        editor: {
          ...current.editor,
          evidence: {
            ...current.editor.evidence,
            status: "failed",
          },
          message: { tone: "error", text: mapEvidenceActionError(error) },
        },
      }));
    }
  };

  const pickDocumentOrAudioEvidence = async () => {
    const picked = await DocumentPicker.getDocumentAsync({
      copyToCacheDirectory: true,
      multiple: false,
      type: ["audio/*", "application/pdf", "text/plain", "text/csv", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    });
    if (picked.canceled || picked.assets.length === 0) {
      return;
    }

    const firstAsset = picked.assets[0];
    await uploadEvidenceAsset({
      localUri: firstAsset.uri,
      filename: firstAsset.name,
      contentType: firstAsset.mimeType || "application/octet-stream",
      size: firstAsset.size ?? null,
    });
  };

  const pickPhotoOrVideoFromLibrary = async () => {
    const permissions = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permissions.granted) {
      updateReadyDetail((current) => ({
        ...current,
        editor: {
          ...current.editor,
          message: { tone: "error", text: "Media library permission is required to select evidence." },
        },
      }));
      return;
    }

    const picked = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: false,
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      quality: 0.8,
    });
    if (picked.canceled || picked.assets.length === 0) {
      return;
    }

    const firstAsset = picked.assets[0];
    await uploadEvidenceAsset({
      localUri: firstAsset.uri,
      filename: firstAsset.fileName || `library-${Date.now()}`,
      contentType: firstAsset.mimeType || mediaTypeToMime(firstAsset.type),
      size: firstAsset.fileSize ?? null,
    });
  };

  const capturePhotoOrVideo = async (mode: "photo" | "video") => {
    const permissions = await ImagePicker.requestCameraPermissionsAsync();
    if (!permissions.granted) {
      updateReadyDetail((current) => ({
        ...current,
        editor: {
          ...current.editor,
          message: { tone: "error", text: "Camera permission is required to capture evidence." },
        },
      }));
      return;
    }

    const captured = await ImagePicker.launchCameraAsync({
      mediaTypes: mode === "photo" ? ImagePicker.MediaTypeOptions.Images : ImagePicker.MediaTypeOptions.Videos,
      quality: 0.8,
      videoQuality: ImagePicker.UIImagePickerControllerQualityType.Medium,
    });
    if (captured.canceled || captured.assets.length === 0) {
      return;
    }

    const firstAsset = captured.assets[0];
    await uploadEvidenceAsset({
      localUri: firstAsset.uri,
      filename: firstAsset.fileName || `${mode}-${Date.now()}`,
      contentType: firstAsset.mimeType || mediaTypeToMime(firstAsset.type),
      size: firstAsset.fileSize ?? null,
    });
  };

  const retryEvidenceUpload = async () => {
    if (detailState.status !== "ready") {
      return;
    }
    if (!detailState.editor.evidence.selectedAsset) {
      return;
    }
    await uploadEvidenceAsset(detailState.editor.evidence.selectedAsset);
  };

  const retryEvidenceStatusPolling = async () => {
    if (detailState.status !== "ready") {
      return;
    }
    if (!detailState.editor.evidence.evidenceId) {
      return;
    }
    await refreshEvidenceStatus(detailState.activityId, detailState.editor.evidence.evidenceId);
  };

  const removeAttachedEvidence = () => {
    updateDraft((draft) => ({
      ...draft,
      evidenceId: null,
    }));
    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        evidence: {
          ...current.editor.evidence,
          status: "idle",
          progressRatio: 0,
          evidenceId: null,
          scanStatus: null,
          scanDetail: null,
          selectedAsset: null,
          preview: null,
          uploadSignature: null,
        },
        message: { tone: "success", text: "Evidence attachment removed from this draft." },
      },
    }));
  };

  const cancelEvidenceUpload = () => {
    cancelEvidenceOperations({ tone: "error", text: "Evidence upload cancelled." });
    updateReadyDetail((current) => ({
      ...current,
      editor: {
        ...current.editor,
        evidence: {
          ...current.editor.evidence,
          status: "idle",
          progressRatio: 0,
          scanStatus: null,
          scanDetail: null,
          preview: null,
        },
      },
    }));
  };

  const openPolicyLink = async (url: string) => {
    try {
      await Linking.openURL(url);
    } catch {
      setAccountState((current) => ({
        ...current,
        message: { tone: "error", text: "We could not open this link right now." },
      }));
    }
  };

  const refreshMessages = async () => {
    const accessToken = accessTokenRef.current;
    if (!accessToken) {
      return;
    }

    messagesRequestVersion.current += 1;
    const requestVersion = messagesRequestVersion.current;
    messagesAbortController.current?.abort();
    const requestController = new AbortController();
    messagesAbortController.current = requestController;

    setMessagesState((current) => ({
      ...current,
      status: "loading",
      message: null,
    }));

    try {
      const result = await getParticipantMessages(accessToken, { signal: requestController.signal });
      if (requestVersion !== messagesRequestVersion.current) {
        return;
      }

      setMessagesState((current) => ({
        ...current,
        status: "ready",
        items: result.data,
        selectedThreadId: "study-thread",
      }));
    } catch (error) {
      if (requestVersion !== messagesRequestVersion.current) {
        return;
      }
      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }

      setMessagesState((current) => ({
        ...current,
        status: "error",
        message: {
          tone: "error",
          text: (error instanceof ApiRequestError && (error.kind === "network" || error.kind === "timeout"))
            ? "You appear to be offline. Check your connection and try again."
            : "We could not load messages right now.",
        },
      }));
    }
  };

  const sendMessage = async () => {
    const accessToken = accessTokenRef.current;
    const body = messagesState.composeBody.trim();
    if (!accessToken || !body) {
      return;
    }

    setMessagesState((current) => ({
      ...current,
      sending: true,
      message: null,
    }));

    try {
      const created: CreateMessageResponse = await createParticipantMessage(
        accessToken,
        { body },
        { idempotencyKey: createIdempotencyKey("message", 0) },
      );

      setMessagesState((current) => ({
        ...current,
        status: "ready",
        sending: false,
        composeBody: "",
        items: [...current.items, created.message],
        selectedThreadId: "study-thread",
        message: { tone: "success", text: "Message sent." },
      }));
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }

      setMessagesState((current) => ({
        ...current,
        sending: false,
        message: {
          tone: "error",
          text: (error instanceof ApiRequestError && (error.kind === "network" || error.kind === "timeout"))
            ? "You appear to be offline. Check your connection and try again."
            : "We could not send this message right now.",
        },
      }));
    }
  };

  const submitWithdrawalRequest = async () => {
    const accessToken = accessTokenRef.current;
    if (!accessToken || !hasJourneyData(homeState) || homeState.activeStudyId === null) {
      return;
    }

    setAccountState((current) => ({
      ...current,
      withdrawing: true,
      message: null,
      confirmWithdraw: false,
    }));

    try {
      await requestParticipantWithdrawal(
        accessToken,
        {
          scope: "study",
          study_id: homeState.activeStudyId,
          confirmed: true,
        },
        { idempotencyKey: createIdempotencyKey("withdrawal", homeState.activeStudyId) },
      );

      setAccountState((current) => ({
        ...current,
        withdrawing: false,
        message: { tone: "success", text: "Withdrawal request received. Your account session will now sign out." },
      }));
      onSessionExpired();
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }
      setAccountState((current) => ({
        ...current,
        withdrawing: false,
        message: {
          tone: "error",
          text: (error instanceof ApiRequestError && (error.kind === "network" || error.kind === "timeout"))
            ? "You appear to be offline. Check your connection and try again."
            : "We could not submit your withdrawal request right now.",
        },
      }));
    }
  };

  const submitDeletionRequest = async () => {
    const accessToken = accessTokenRef.current;
    if (!accessToken || !hasJourneyData(homeState) || homeState.activeStudyId === null) {
      return;
    }

    setAccountState((current) => ({
      ...current,
      deleting: true,
      message: null,
      confirmDelete: false,
    }));

    try {
      await requestParticipantDeletion(
        accessToken,
        {
          mode_preference: "delete",
          study_id: homeState.activeStudyId,
          scope: "account",
          confirmed: true,
        },
        { idempotencyKey: createIdempotencyKey("deletion", homeState.activeStudyId) },
      );

      accessTokenRef.current = null;
      controller.clear();
      detailRequestVersion.current += 1;
      detailAbortController.current?.abort();
      detailAbortController.current = null;
      writeRequestVersion.current += 1;
      writeAbortController.current?.abort();
      writeAbortController.current = null;
      evidenceRequestVersion.current += 1;
      evidenceAbortController.current?.abort();
      evidenceAbortController.current = null;
      if (evidencePollTimeout.current) {
        clearTimeout(evidencePollTimeout.current);
        evidencePollTimeout.current = null;
      }
      messagesRequestVersion.current += 1;
      messagesAbortController.current?.abort();
      messagesAbortController.current = null;
      setDetailState({ status: "idle" });
      setHomePanel("home");
      setMessagesState({
        status: "idle",
        items: [],
        selectedThreadId: null,
        composeBody: "",
        sending: false,
        message: null,
      });
      setAccountState((current) => ({
        ...current,
        deleting: false,
        confirmDelete: false,
        message: null,
      }));
      setSessionEnding(true);
      onSessionExpired();
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        onSessionExpired();
        return;
      }
      setAccountState((current) => ({
        ...current,
        deleting: false,
        message: {
          tone: "error",
          text: (error instanceof ApiRequestError && (error.kind === "network" || error.kind === "timeout"))
            ? "You appear to be offline. Check your connection and try again."
            : "We could not submit your deletion request right now.",
        },
      }));
    }
  };

  const openMessagesPanel = () => {
    setHomePanel("messages");
    void refreshMessages();
  };

  const enableNotifications = async () => {
    setAccountState((current) => ({
      ...current,
      notificationsBusy: true,
      message: null,
    }));

    const result = await registerForPushNotifications();
    if (result.status === "enabled") {
      setAccountState((current) => ({
        ...current,
        notificationsBusy: false,
        notificationsEnabled: true,
        notificationsUpdatedAt: new Date().toISOString(),
        message: { tone: "success", text: "Notifications enabled for this device." },
      }));
      return;
    }

    const tone = result.status === "error" ? "error" : "success";
    setAccountState((current) => ({
      ...current,
      notificationsBusy: false,
      notificationsEnabled: false,
      notificationsUpdatedAt: new Date().toISOString(),
      message: { tone, text: result.message },
    }));
  };

  const disableNotifications = async () => {
    setAccountState((current) => ({
      ...current,
      notificationsBusy: true,
      message: null,
    }));

    await disablePushNotificationsLocally();
    setAccountState((current) => ({
      ...current,
      notificationsBusy: false,
      notificationsEnabled: false,
      notificationsUpdatedAt: new Date().toISOString(),
      message: { tone: "success", text: "Notifications disabled on this device." },
    }));
  };

  const showDetail = detailState.status !== "idle";

  if (sessionEnding) {
    return (
      <View accessibilityLabel="Ending secure session" style={styles.stateBlock}>
        <ActivityIndicator size="small" color="#00573d" />
        <Text style={styles.body}>Ending your session securely.</Text>
      </View>
    );
  }

  if (showDetail) {
    return (
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}>
          <CitizenCentricLogo variant="compact" />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back to studies"
            style={styles.tertiaryButton}
            onPress={() => {
              cancelEvidenceOperations();
              setDetailState({ status: "idle" });
            }}
          >
            <Text style={styles.tertiaryButtonText}>Back</Text>
          </Pressable>
        </View>
        <Text accessibilityRole="header" style={styles.title}>
          Activity details
        </Text>

        {detailState.status === "loading" && (
          <View style={styles.stateBlock}>
            <ActivityIndicator size="small" color="#00573d" />
            <Text style={styles.body}>Loading activity details.</Text>
          </View>
        )}

        {detailState.status === "error" && (
          <View style={styles.stateBlock}>
            <Text style={styles.body}>{detailState.message}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retry activity details"
              style={styles.button}
              onPress={() => void openActivityDetail(detailState.activityId)}
            >
              <Text style={styles.buttonText}>Try again</Text>
            </Pressable>
          </View>
        )}

        {detailState.status === "ready" && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{detailState.detail.activity.title}</Text>
            {detailState.detail.activity.prompt ? (
              <Text style={styles.body}>{detailState.detail.activity.prompt}</Text>
            ) : (
              <Text style={styles.body}>No additional instructions are provided for this activity.</Text>
            )}
            <Text style={styles.metaLine}>Type: {readableActivityType(detailState.detail.activity.activity_type)}</Text>
            <Text style={styles.metaLine}>Status: {readableAvailability(detailState.detail.activity.availability.status)}</Text>
            <Text style={styles.metaLine}>{requiredLabel(detailState.detail.activity.required)}</Text>
            {detailState.detail.activity.availability.release_at ? (
              <Text style={styles.metaLine}>Opens: {formatDateTime(detailState.detail.activity.availability.release_at)}</Text>
            ) : null}
            {detailState.detail.activity.availability.due_at ? (
              <Text style={styles.metaLine}>Due: {formatDateTime(detailState.detail.activity.availability.due_at)}</Text>
            ) : null}
            <Text style={styles.metaLine}>Response: {readableResponseStatus(detailState.detail.response?.status)}</Text>
            {detailState.detail.response?.updated_at ? (
              <Text style={styles.metaLine}>Last updated: {formatDateTime(detailState.detail.response.updated_at)}</Text>
            ) : null}
            {detailState.detail.response?.submitted_at ? (
              <Text style={styles.metaLine}>Submitted: {formatDateTime(detailState.detail.response.submitted_at)}</Text>
            ) : null}
            {typeof detailState.detail.response?.value?.evidence_id === "number" ? (
              <Text style={styles.metaLine}>Evidence reference: #{detailState.detail.response.value.evidence_id}</Text>
            ) : null}

            <ActivityResponseEditor
              detail={detailState.detail}
              editor={detailState.editor}
              onChangeAnswer={(answer) => updateDraft((draft) => ({ ...draft, answer }))}
              onSelectSingleChoice={(choice) =>
                updateDraft((draft) => ({
                  ...draft,
                  choices: draft.choices[0] === choice ? [] : [choice],
                }))
              }
              onToggleMultipleChoice={(choice) =>
                updateDraft((draft, detail) => ({
                  ...draft,
                  choices: draft.choices.includes(choice)
                    ? draft.choices.filter((item) => item !== choice)
                    : orderedChoices([...draft.choices, choice], detail.activity.options || []),
                }))
              }
              onSaveDraft={() => void persistDraft()}
              onReviewSubmit={() =>
                updateReadyDetail((current) => ({
                  ...current,
                  editor: {
                    ...current.editor,
                    confirmingSubmit: true,
                  },
                }))
              }
              onCancelSubmit={() =>
                updateReadyDetail((current) => ({
                  ...current,
                  editor: {
                    ...current.editor,
                    confirmingSubmit: false,
                  },
                }))
              }
              onConfirmSubmit={() => void submitResponse()}
              onPickDocumentOrAudio={() => void pickDocumentOrAudioEvidence()}
              onPickPhotoOrVideoFromLibrary={() => void pickPhotoOrVideoFromLibrary()}
              onCapturePhoto={() => void capturePhotoOrVideo("photo")}
              onCaptureVideo={() => void capturePhotoOrVideo("video")}
              onRetryEvidenceUpload={() => void retryEvidenceUpload()}
              onRetryEvidenceStatus={() => void retryEvidenceStatusPolling()}
              onCancelEvidenceUpload={() => void cancelEvidenceUpload()}
              onRemoveAttachedEvidence={removeAttachedEvidence}
              onReplaceEvidence={() => void pickDocumentOrAudioEvidence()}
            />
          </View>
        )}
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.topBar}>
        <CitizenCentricLogo variant="compact" />
        <Pressable accessibilityRole="button" accessibilityLabel="Sign out" style={styles.button} onPress={onSignOut}>
          <Text style={styles.buttonText}>Sign out</Text>
        </Pressable>
      </View>

      <Text accessibilityRole="header" style={styles.title}>
        Citizen Centric
      </Text>
      <Text style={styles.body}>{participantName ? `Welcome ${participantName}.` : "Welcome."}</Text>

      {(homeState.status === "initialising" || (homeState.status === "loading" && homeState.studies.length === 0)) && (
        <View style={styles.stateBlock}>
          <ActivityIndicator accessibilityLabel="Loading your studies" size="small" color="#00573d" />
          <Text style={styles.body}>Loading your studies</Text>
        </View>
      )}

      {homeState.status === "empty" && (
        <View style={styles.stateBlock}>
          <Text style={styles.body}>No studies are available yet.</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Retry" style={styles.button} onPress={() => void controller.refresh()}>
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
        </View>
      )}

      {homeState.status === "offline" && (
        <View style={styles.alertCard}>
          <Text style={styles.alertTitle}>You appear to be offline.</Text>
          <Text style={styles.body}>Check your connection and try again.</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Retry" style={styles.button} onPress={() => void controller.refresh()}>
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
        </View>
      )}

      {homeState.status === "recoverable_error" && (
        <View style={styles.alertCard}>
          <Text style={styles.alertTitle}>Temporary service issue</Text>
          <Text style={styles.body}>{homeState.message}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Retry" style={styles.button} onPress={() => void controller.refresh()}>
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
        </View>
      )}

      {hasJourneyData(homeState) && (
        <View style={styles.contentBlock}>
          <View style={styles.panelTabs}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open activities panel"
              onPress={() => setHomePanel("home")}
              style={[styles.panelTab, homePanel === "home" ? styles.panelTabActive : null]}
            >
              <Text style={[styles.panelTabText, homePanel === "home" ? styles.panelTabTextActive : null]}>Activities</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open messages panel"
              onPress={openMessagesPanel}
              style={[styles.panelTab, homePanel === "messages" ? styles.panelTabActive : null]}
            >
              <Text style={[styles.panelTabText, homePanel === "messages" ? styles.panelTabTextActive : null]}>Messages</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Open account and privacy panel"
              onPress={() => setHomePanel("account")}
              style={[styles.panelTab, homePanel === "account" ? styles.panelTabActive : null]}
            >
              <Text style={[styles.panelTabText, homePanel === "account" ? styles.panelTabTextActive : null]}>Account</Text>
            </Pressable>
          </View>

          {homePanel === "home" && (
            <>
              {homeState.studies.length > 1 && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Choose a study</Text>
                  <View style={styles.studyList}>
                    {homeState.studies.map((study) => {
                      const selected = homeState.activeStudyId === study.study_id;

                      return (
                        <Pressable
                          key={study.study_id}
                          accessibilityRole="button"
                          accessibilityLabel={`Select study ${study.title}`}
                          onPress={() => {
                            cancelEvidenceOperations();
                            setDetailState({ status: "idle" });
                            void controller.selectStudy(study.study_id);
                          }}
                          style={[styles.studyChip, selected ? styles.studyChipSelected : null]}
                        >
                          <Text style={[styles.studyChipText, selected ? styles.studyChipTextSelected : null]}>{study.title}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  {homeState.requiresStudySelection ? <Text style={styles.body}>Choose a study to view its activities.</Text> : null}
                </View>
              )}

              {homeState.activeStudyId !== null && (
                <>
                  {homeState.isRefreshing && (
                    <View style={styles.refreshRow}>
                      <ActivityIndicator size="small" color="#00573d" />
                      <Text style={styles.metaLine}>Refreshing</Text>
                    </View>
                  )}
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Refresh activities"
                    onPress={() => void controller.refresh()}
                    style={styles.secondaryButton}
                  >
                    <Text style={styles.secondaryButtonText}>Refresh</Text>
                  </Pressable>
                  <ActivitySections activities={homeState.activities} onSelect={openActivityDetail} />
                </>
              )}
            </>
          )}

          {homePanel === "messages" && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Inbox</Text>
              <Text style={styles.metaLine}>Study: {activeStudyTitle}</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Refresh messages"
                onPress={() => void refreshMessages()}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>Refresh messages</Text>
              </Pressable>
              {messagesState.status === "loading" && (
                <View style={styles.refreshRow}>
                  <ActivityIndicator size="small" color="#00573d" />
                  <Text style={styles.metaLine}>Loading messages</Text>
                </View>
              )}
              {messagesState.items.length === 0 && messagesState.status === "ready" ? (
                <Text style={styles.body}>No messages yet. Send a message to your study team.</Text>
              ) : null}
              {messagesState.items.map((item) => (
                <View key={item.message_id} style={styles.messageRow}>
                  <Text style={styles.cardTitle}>{item.sender_type === "researcher" ? "Research Team" : "You"}</Text>
                  <Text style={styles.body}>{item.body}</Text>
                  <Text style={styles.metaLine}>{formatDateTime(item.created_at)}</Text>
                </View>
              ))}
              {messagesState.message ? <InlineMessage message={messagesState.message} /> : null}
              <TextInput
                accessibilityLabel="Compose message"
                multiline
                numberOfLines={4}
                onChangeText={(text) => setMessagesState((current) => ({ ...current, composeBody: text }))}
                placeholder="Write a secure message to your study team"
                style={[styles.input, styles.multilineInput]}
                textAlignVertical="top"
                value={messagesState.composeBody}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Send message"
                accessibilityState={{ disabled: messagesState.sending || !messagesState.composeBody.trim() }}
                disabled={messagesState.sending || !messagesState.composeBody.trim()}
                onPress={() => void sendMessage()}
                style={[styles.button, (messagesState.sending || !messagesState.composeBody.trim()) ? styles.disabledPrimaryButton : null]}
              >
                <Text style={styles.buttonText}>{messagesState.sending ? "Sending" : "Send message"}</Text>
              </Pressable>
            </View>
          )}

          {homePanel === "account" && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Account and privacy</Text>
              <Text style={styles.metaLine}>Participant: {participantName || "Participant"}</Text>
              <Text style={styles.metaLine}>Current study: {activeStudyTitle}</Text>
              <Text style={styles.metaLine}>Consent status: {consentLabel}</Text>
              {accountState.message ? <InlineMessage message={accountState.message} /> : null}

              <View style={styles.actionRow}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open privacy policy"
                  onPress={() => void openPolicyLink(env.privacyUrl)}
                  style={styles.secondaryButton}
                >
                  <Text style={styles.secondaryButtonText}>Privacy policy</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open terms"
                  onPress={() => void openPolicyLink(env.termsUrl)}
                  style={styles.secondaryButton}
                >
                  <Text style={styles.secondaryButtonText}>Terms</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open support"
                  onPress={() => void openPolicyLink(env.supportUrl)}
                  style={styles.secondaryButton}
                >
                  <Text style={styles.secondaryButtonText}>Support</Text>
                </Pressable>
              </View>

              <View style={styles.confirmPanel}>
                <Text style={styles.body}>Notifications</Text>
                <Text style={styles.metaLine}>
                  {accountState.notificationsEnabled
                    ? "Push notifications are enabled for this device."
                    : "Push notifications are currently disabled."}
                </Text>
                {accountState.notificationsUpdatedAt ? (
                  <Text style={styles.metaLine}>Last updated: {formatDateTime(accountState.notificationsUpdatedAt)}</Text>
                ) : null}
                <View style={styles.actionRow}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Enable notifications"
                    accessibilityState={{ disabled: accountState.notificationsBusy }}
                    disabled={accountState.notificationsBusy}
                    onPress={() => void enableNotifications()}
                    style={[styles.secondaryButton, accountState.notificationsBusy ? styles.disabledButton : null]}
                  >
                    <Text style={styles.secondaryButtonText}>Enable notifications</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Disable notifications"
                    accessibilityState={{ disabled: accountState.notificationsBusy }}
                    disabled={accountState.notificationsBusy}
                    onPress={() => void disableNotifications()}
                    style={[styles.secondaryButton, accountState.notificationsBusy ? styles.disabledButton : null]}
                  >
                    <Text style={styles.secondaryButtonText}>Disable notifications</Text>
                  </Pressable>
                </View>
              </View>

              <View style={styles.confirmPanel}>
                <Text style={styles.body}>Withdraw from this study</Text>
                <Text style={styles.metaLine}>This removes your active participation and signs you out.</Text>
                {!accountState.confirmWithdraw ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Start withdrawal request"
                    onPress={() => setAccountState((current) => ({ ...current, confirmWithdraw: true, confirmDelete: false }))}
                    style={styles.secondaryButton}
                  >
                    <Text style={styles.secondaryButtonText}>Request withdrawal</Text>
                  </Pressable>
                ) : (
                  <View style={styles.actionRow}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Cancel withdrawal request"
                      onPress={() => setAccountState((current) => ({ ...current, confirmWithdraw: false }))}
                      style={styles.secondaryButton}
                    >
                      <Text style={styles.secondaryButtonText}>Cancel</Text>
                    </Pressable>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Confirm withdrawal request"
                      accessibilityState={{ disabled: accountState.withdrawing }}
                      disabled={accountState.withdrawing}
                      onPress={() => void submitWithdrawalRequest()}
                      style={[styles.button, accountState.withdrawing ? styles.disabledPrimaryButton : null]}
                    >
                      <Text style={styles.buttonText}>{accountState.withdrawing ? "Submitting" : "Confirm withdrawal"}</Text>
                    </Pressable>
                  </View>
                )}
              </View>

              <View style={styles.confirmPanel}>
                <Text style={styles.body}>Request account deletion</Text>
                <Text style={styles.metaLine}>The research team will process deletion or anonymisation safely.</Text>
                {!accountState.confirmDelete ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Start deletion request"
                    onPress={() => setAccountState((current) => ({ ...current, confirmDelete: true, confirmWithdraw: false }))}
                    style={styles.secondaryButton}
                  >
                    <Text style={styles.secondaryButtonText}>Request deletion</Text>
                  </Pressable>
                ) : (
                  <View style={styles.actionRow}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Cancel deletion request"
                      onPress={() => setAccountState((current) => ({ ...current, confirmDelete: false }))}
                      style={styles.secondaryButton}
                    >
                      <Text style={styles.secondaryButtonText}>Cancel</Text>
                    </Pressable>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Confirm deletion request"
                      accessibilityState={{ disabled: accountState.deleting }}
                      disabled={accountState.deleting}
                      onPress={() => void submitDeletionRequest()}
                      style={[styles.button, accountState.deleting ? styles.disabledPrimaryButton : null]}
                    >
                      <Text style={styles.buttonText}>{accountState.deleting ? "Submitting" : "Confirm deletion"}</Text>
                    </Pressable>
                  </View>
                )}
              </View>
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}

function ActivityResponseEditor({
  detail,
  editor,
  onChangeAnswer,
  onSelectSingleChoice,
  onToggleMultipleChoice,
  onSaveDraft,
  onReviewSubmit,
  onCancelSubmit,
  onConfirmSubmit,
  onPickDocumentOrAudio,
  onPickPhotoOrVideoFromLibrary,
  onCapturePhoto,
  onCaptureVideo,
  onRetryEvidenceUpload,
  onRetryEvidenceStatus,
  onCancelEvidenceUpload,
  onRemoveAttachedEvidence,
  onReplaceEvidence,
}: {
  detail: ActivityDetailResponse;
  editor: ActivityEditorState;
  onChangeAnswer: (answer: string) => void;
  onSelectSingleChoice: (choice: string) => void;
  onToggleMultipleChoice: (choice: string) => void;
  onSaveDraft: () => void;
  onReviewSubmit: () => void;
  onCancelSubmit: () => void;
  onConfirmSubmit: () => void;
  onPickDocumentOrAudio: () => void;
  onPickPhotoOrVideoFromLibrary: () => void;
  onCapturePhoto: () => void;
  onCaptureVideo: () => void;
  onRetryEvidenceUpload: () => void;
  onRetryEvidenceStatus: () => void;
  onCancelEvidenceUpload: () => void;
  onRemoveAttachedEvidence: () => void;
  onReplaceEvidence: () => void;
}) {
  const isSubmitted = isSubmittedResponse(detail.response?.status);
  const supported = isSupportedResponseEntryType(detail.activity.activity_type);
  const dirty = isEditorDirty(editor);
  const choices = detail.activity.options || [];
  const actionBusy = editor.actionStatus !== "idle";
  const evidenceBusy = editor.evidence.status === "uploading" || editor.evidence.status === "polling";
  const missingChoiceOptions = isChoiceActivity(detail.activity.activity_type) && choices.length === 0;

  if (isSubmitted) {
    return (
      <View style={styles.editorBlock}>
        <Text style={styles.sectionTitle}>Submitted response</Text>
        <ReadOnlyResponseValue draft={editor.persisted} />
        {editor.message ? <InlineMessage message={editor.message} /> : null}
      </View>
    );
  }

  if (!supported) {
    return (
      <View style={styles.editorBlock}>
        <Text style={styles.body}>Response entry for this activity type is not available in the app yet.</Text>
      </View>
    );
  }

  return (
    <View style={styles.editorBlock}>
      <Text style={styles.sectionTitle}>Your response</Text>
      {dirty ? <Text style={styles.unsavedText}>Unsaved changes</Text> : <Text style={styles.metaLine}>No unsaved changes</Text>}

      {(detail.activity.activity_type === "short_text" || detail.activity.activity_type === "long_text") && (
        <TextInput
          accessibilityLabel={`Response for ${detail.activity.title}`}
          multiline
          numberOfLines={detail.activity.activity_type === "long_text" ? 6 : 3}
          onChangeText={onChangeAnswer}
          placeholder="Write your response"
          style={[styles.input, detail.activity.activity_type === "long_text" ? styles.multilineInput : null]}
          textAlignVertical="top"
          value={editor.draft.answer}
        />
      )}

      {detail.activity.activity_type === "single_choice" && (
        <ChoiceOptions
          options={choices}
          selectedChoices={editor.draft.choices}
          accessibilityPrefix="Select option"
          role="radio"
          onToggle={onSelectSingleChoice}
        />
      )}

      {detail.activity.activity_type === "multiple_choice" && (
        <ChoiceOptions
          options={choices}
          selectedChoices={editor.draft.choices}
          accessibilityPrefix="Toggle option"
          role="checkbox"
          onToggle={onToggleMultipleChoice}
        />
      )}

      {missingChoiceOptions ? <InlineMessage message={{ tone: "error", text: "Response options are unavailable right now." }} /> : null}

      <View style={styles.evidencePanel}>
        <Text style={styles.sectionTitle}>Evidence attachment</Text>
        <Text style={styles.metaLine}>{readableEvidenceStatus(editor.evidence)}</Text>
        {editor.evidence.selectedAsset ? <Text style={styles.metaLine}>Selected file: {editor.evidence.selectedAsset.filename}</Text> : null}
        {editor.evidence.evidenceId ? <Text style={styles.metaLine}>Evidence reference: #{editor.evidence.evidenceId}</Text> : null}
        {editor.evidence.preview ? <EvidencePreviewCard preview={editor.evidence.preview} /> : null}
        {editor.evidence.status === "uploading" ? (
          <Text style={styles.metaLine}>Upload progress: {Math.round(editor.evidence.progressRatio * 100)}%</Text>
        ) : null}

        <View style={styles.actionRow}>
          <Pressable accessibilityRole="button" accessibilityLabel="Capture photo evidence" onPress={onCapturePhoto} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Capture photo</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Capture video evidence" onPress={onCaptureVideo} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Capture video</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Select photo or video evidence"
            onPress={onPickPhotoOrVideoFromLibrary}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>Choose media</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Select document or audio evidence"
            onPress={onPickDocumentOrAudio}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>Choose document or audio</Text>
          </Pressable>
        </View>

        <View style={styles.actionRow}>
          {(editor.evidence.status === "uploading" || editor.evidence.status === "polling") ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Cancel evidence upload"
              onPress={onCancelEvidenceUpload}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Cancel evidence upload</Text>
            </Pressable>
          ) : null}

          {editor.evidence.status === "failed" ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retry evidence upload"
              onPress={onRetryEvidenceUpload}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Retry upload</Text>
            </Pressable>
          ) : null}

          {(editor.evidence.status === "polling" || editor.evidence.status === "failed") && editor.evidence.evidenceId ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retry evidence scan status"
              onPress={onRetryEvidenceStatus}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Retry status check</Text>
            </Pressable>
          ) : null}

          {editor.draft.evidenceId ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Replace attached evidence"
              onPress={onReplaceEvidence}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Replace evidence</Text>
            </Pressable>
          ) : null}

          {editor.draft.evidenceId ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Remove attached evidence"
              onPress={onRemoveAttachedEvidence}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Remove evidence</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      {editor.message ? <InlineMessage message={editor.message} /> : null}

      <View style={styles.actionRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save draft response"
          accessibilityState={{ disabled: !dirty || actionBusy || evidenceBusy || missingChoiceOptions }}
          disabled={!dirty || actionBusy || evidenceBusy || missingChoiceOptions}
          onPress={onSaveDraft}
          style={[styles.secondaryButton, (!dirty || actionBusy || evidenceBusy || missingChoiceOptions) ? styles.disabledButton : null]}
        >
          <Text style={styles.secondaryButtonText}>{editor.actionStatus === "saving" ? "Saving draft" : "Save draft"}</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Review response before submitting"
          accessibilityState={{ disabled: actionBusy || evidenceBusy || missingChoiceOptions }}
          disabled={actionBusy || evidenceBusy || missingChoiceOptions}
          onPress={onReviewSubmit}
          style={[styles.button, (actionBusy || evidenceBusy || missingChoiceOptions) ? styles.disabledPrimaryButton : null]}
        >
          <Text style={styles.buttonText}>{editor.actionStatus === "submitting" ? "Submitting" : "Submit response"}</Text>
        </Pressable>
      </View>

      {editor.confirmingSubmit ? (
        <View style={styles.confirmPanel}>
          <Text style={styles.body}>You will not be able to edit this response after submission.</Text>
          <View style={styles.actionRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Cancel submit response"
              onPress={onCancelSubmit}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>Cancel</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Confirm submit response"
              onPress={onConfirmSubmit}
              style={styles.button}
            >
              <Text style={styles.buttonText}>Confirm submit</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

function ChoiceOptions({
  options,
  selectedChoices,
  accessibilityPrefix,
  role,
  onToggle,
}: {
  options: string[];
  selectedChoices: string[];
  accessibilityPrefix: string;
  role: "radio" | "checkbox";
  onToggle: (choice: string) => void;
}) {
  return (
    <View style={styles.choiceList}>
      {options.map((choice) => {
        const selected = selectedChoices.includes(choice);

        return (
          <Pressable
            key={choice}
            accessibilityRole={role}
            accessibilityLabel={`${accessibilityPrefix} ${choice}`}
            accessibilityState={{ checked: selected }}
            onPress={() => onToggle(choice)}
            style={[styles.choiceOption, selected ? styles.choiceOptionSelected : null]}
          >
            <Text style={[styles.choiceOptionText, selected ? styles.choiceOptionTextSelected : null]}>{choice}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function ReadOnlyResponseValue({ draft }: { draft: EditableResponseDraft }) {
  return (
    <View style={styles.readOnlyBlock}>
      {draft.answer ? <Text style={styles.body}>{draft.answer}</Text> : null}
      {draft.choices.length > 0 ? <Text style={styles.body}>Selected: {draft.choices.join(", ")}</Text> : null}
      {!draft.answer && draft.choices.length === 0 ? <Text style={styles.body}>No response content available.</Text> : null}
    </View>
  );
}

function EvidencePreviewCard({ preview }: { preview: EvidencePreview }) {
  if (preview.kind === "image") {
    return (
      <View style={styles.previewCard}>
        <Text style={styles.metaLine}>Evidence preview: {preview.label}</Text>
        <Image accessibilityLabel="Selected image evidence preview" source={{ uri: preview.uri }} style={styles.previewImage} />
      </View>
    );
  }

  return (
    <View style={styles.previewCard}>
      <Text style={styles.metaLine}>Evidence preview: {preview.label}</Text>
      <Text style={styles.metaLine}>Preview not available for this file type on this screen.</Text>
    </View>
  );
}

function InlineMessage({ message }: { message: EditorMessage }) {
  return <Text style={message.tone === "error" ? styles.errorText : styles.successText}>{message.text}</Text>;
}

function hasJourneyData(
  state: ParticipantHomeState,
): state is Extract<ParticipantHomeState, { studies: unknown; activities: unknown; activeStudyId: unknown }> {
  return "studies" in state && "activities" in state && "activeStudyId" in state;
}

function resolveParticipantName(state: ParticipantHomeState, fallback?: string): string | undefined {
  if ("participantDisplayName" in state && state.participantDisplayName) {
    return state.participantDisplayName;
  }
  return fallback;
}

function ActivitySections({
  activities,
  onSelect,
}: {
  activities: ActivitySummary[];
  onSelect: (activityId: number) => void;
}) {
  if (activities.length === 0) {
    return <Text style={styles.body}>There are no activities in this study yet.</Text>;
  }

  const available = activities.filter((activity) => activity.availability.status === "open");
  const upcoming = activities.filter((activity) => activity.availability.status === "upcoming");
  const completed = activities.filter((activity) => activity.availability.status === "closed");

  return (
    <View style={styles.sectionGroup}>
      <ActivitySection title="Available" activities={available} onSelect={onSelect} />
      <ActivitySection title="Upcoming" activities={upcoming} onSelect={onSelect} />
      <ActivitySection title="Completed" activities={completed} onSelect={onSelect} />
    </View>
  );
}

function ActivitySection({
  title,
  activities,
  onSelect,
}: {
  title: "Available" | "Upcoming" | "Completed";
  activities: ActivitySummary[];
  onSelect: (activityId: number) => void;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {activities.length === 0 ? (
        <Text style={styles.metaLine}>None</Text>
      ) : (
        activities.map((activity) => {
          const availabilityLabel = readableAvailability(activity.availability.status);
          const responseLabel = readableResponseStatus(activity.response?.status);
          const scheduleLabel = readableSchedule(activity);
          const accessibilityLabel = `${activity.title}. ${availabilityLabel}. ${responseLabel}. ${scheduleLabel}`;

          return (
            <Pressable
              key={activity.activity_id}
              accessibilityRole="button"
              accessibilityLabel={accessibilityLabel}
              onPress={() => void onSelect(activity.activity_id)}
              style={styles.activityCard}
            >
              <Text style={styles.cardTitle}>{activity.title}</Text>
              <Text style={styles.metaLine}>Status: {availabilityLabel}</Text>
              <Text style={styles.metaLine}>{requiredLabel(activity.required)}</Text>
              <Text style={styles.metaLine}>Response: {responseLabel}</Text>
              <Text style={styles.metaLine}>{scheduleLabel}</Text>
            </Pressable>
          );
        })
      )}
    </View>
  );
}

function readableAvailability(status: ActivitySummary["availability"]["status"]): string {
  switch (status) {
    case "open":
      return "Available";
    case "upcoming":
      return "Upcoming";
    case "closed":
      return "Completed";
    default:
      return "Available";
  }
}

function readableResponseStatus(status?: "draft" | "submitted"): string {
  if (status === "draft") {
    return "Draft saved";
  }
  if (status === "submitted") {
    return "Submitted";
  }
  return "Not started";
}

function readableConsentStatus(status: string): string {
  if (status === "granted") {
    return "Granted";
  }
  if (status === "withdrawn") {
    return "Withdrawn";
  }
  return "Pending";
}

function isSubmittedResponse(status?: "draft" | "submitted"): boolean {
  return status === "submitted";
}

function isSupportedResponseEntryType(activityType: ActivitySummary["activity_type"]): boolean {
  return ["short_text", "long_text", "single_choice", "multiple_choice"].includes(activityType);
}

function isChoiceActivity(activityType: ActivitySummary["activity_type"]): boolean {
  return activityType === "single_choice" || activityType === "multiple_choice";
}

function requiredLabel(required: boolean): string {
  return required ? "Required" : "Optional";
}

function readableSchedule(activity: ActivitySummary): string {
  if (activity.availability.status === "open" && activity.availability.due_at) {
    return `Due ${formatDateTime(activity.availability.due_at)}`;
  }
  if (activity.availability.status === "upcoming" && activity.availability.release_at) {
    return `Opens ${formatDateTime(activity.availability.release_at)}`;
  }
  if (activity.availability.status === "closed" && activity.availability.due_at) {
    return `Closed after ${formatDateTime(activity.availability.due_at)}`;
  }
  return "No date available";
}

function createActivityEditorState(detail: ActivityDetailResponse): ActivityEditorState {
  const persisted = normalizeEditableResponseDraft(buildEditableResponseDraft(detail), detail.activity);

  return {
    draft: persisted,
    persisted,
    actionStatus: "idle",
    confirmingSubmit: false,
    message: null,
    evidence: {
      status: persisted.evidenceId ? "polling" : "idle",
      progressRatio: 0,
      evidenceId: persisted.evidenceId,
      scanStatus: persisted.evidenceId ? "pending" : null,
      scanDetail: null,
      selectedAsset: null,
      preview: null,
      uploadSignature: null,
    },
  };
}

function buildEditableResponseDraft(detail: ActivityDetailResponse): EditableResponseDraft {
  return {
    answer: detail.response?.value?.answer || "",
    choices: detail.response?.value?.choices || [],
    evidenceId: detail.response?.value?.evidence_id ?? null,
  };
}

function normalizeEditableResponseDraft(draft: EditableResponseDraft, activity: ActivityDetailResponse["activity"]): EditableResponseDraft {
  const filteredChoices = Array.isArray(draft.choices)
    ? draft.choices.filter((choice) => typeof choice === "string" && choice.trim())
    : [];

  if (activity.activity_type === "single_choice") {
    return {
      answer: draft.answer,
      choices: filteredChoices.slice(0, 1),
      evidenceId: draft.evidenceId,
    };
  }

  if (activity.activity_type === "multiple_choice") {
    return {
      answer: draft.answer,
      choices: orderedChoices(filteredChoices, activity.options || []),
      evidenceId: draft.evidenceId,
    };
  }

  return {
    answer: draft.answer,
    choices: [],
    evidenceId: draft.evidenceId,
  };
}

function orderedChoices(choices: string[], options: string[]): string[] {
  if (options.length === 0) {
    return [...new Set(choices)];
  }

  return options.filter((option) => choices.includes(option));
}

function buildDraftRequest(detail: ActivityDetailResponse, draft: EditableResponseDraft): DraftResponseRequest {
  const normalized = normalizeEditableResponseDraft(draft, detail.activity);

  return {
    answer: normalized.answer,
    choices: normalized.choices,
    evidence_id: normalized.evidenceId || undefined,
  };
}

function toResponseValue(draft: EditableResponseDraft): NonNullable<NonNullable<ActivityDetailResponse["response"]>["value"]> {
  return {
    answer: draft.answer,
    choices: draft.choices,
    evidence_id: draft.evidenceId || undefined,
  };
}

function isEditorDirty(editor: ActivityEditorState): boolean {
  return (
    editor.draft.answer !== editor.persisted.answer ||
    editor.draft.evidenceId !== editor.persisted.evidenceId ||
    editor.draft.choices.length !== editor.persisted.choices.length ||
    editor.draft.choices.some((choice, index) => choice !== editor.persisted.choices[index])
  );
}

function mapDetailActionError(error: unknown, action: "save" | "submit"): string {
  if (error instanceof ApiRequestError) {
    if (error.kind === "network" || error.kind === "timeout") {
      return "You appear to be offline. Check your connection and try again.";
    }

    if (error.status === 403 || error.status === 404) {
      return "This activity is no longer available for editing.";
    }

    if (error.status === 429) {
      return "Please wait a moment and try again.";
    }

    if (error.status === 400 || error.status === 422) {
      return action === "submit"
        ? "Your response is incomplete. Review it and try again."
        : "We could not save this draft. Review your response and try again.";
    }
  }

  return action === "submit"
    ? "We could not submit your response right now. Please try again."
    : "We could not save your draft right now. Please try again.";
}

function mapEvidenceActionError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return "Your session expired while uploading evidence.";
    }
    if (error.kind === "network" || error.kind === "timeout") {
      return "Evidence upload failed because your connection dropped. Your response draft is still saved locally.";
    }
    if (error.status === 409) {
      return "This activity was already submitted, so evidence can no longer be attached.";
    }
    if (error.status === 413) {
      return "This file is too large to upload.";
    }
    if (error.status === 415 || error.status === 422) {
      return "This file type is not supported for evidence upload.";
    }
    if (error.status === 429) {
      return "Please wait briefly before uploading another evidence file.";
    }
  }
  return "We could not upload or verify this evidence right now. Please try again.";
}

function createIdempotencyKey(
  action: "draft" | "submit" | "evidence" | "message" | "withdrawal" | "deletion",
  activityId: number,
): string {
  return `mob-${action}-${activityId}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeEvidenceScanStatus(status: string | undefined): "pending" | "clean" | "infected" | "scan_failed" {
  if (status === "clean" || status === "infected" || status === "scan_failed") {
    return status;
  }
  return "pending";
}

function readableEvidenceStatus(state: EvidenceWorkflowState): string {
  switch (state.status) {
    case "uploading":
      return "Uploading evidence file.";
    case "polling":
      return "Evidence uploaded. Security scan in progress.";
    case "clean":
      return "Evidence scan passed. Ready for draft save and submission.";
    case "rejected":
      return "Evidence was blocked by security screening. Please choose another file.";
    case "failed":
      return "Evidence screening could not be confirmed. Retry upload or status check.";
    default:
      return "No evidence attached.";
  }
}

function evidenceAssetSignature(asset: EvidenceAsset): string {
  return `${asset.localUri}|${asset.filename}|${asset.contentType}|${asset.size || 0}`;
}

function mediaTypeToMime(type: string | null | undefined): string {
  if (type === "video") {
    return "video/mp4";
  }
  return "image/jpeg";
}

function evidencePreviewFromAsset(asset: EvidenceAsset): EvidencePreview {
  const mediaType = asset.contentType.toLowerCase();
  if (mediaType.startsWith("image/")) {
    return {
      kind: "image",
      uri: asset.localUri,
      label: asset.filename,
    };
  }
  if (mediaType.startsWith("video/")) {
    return {
      kind: "video",
      uri: asset.localUri,
      label: asset.filename,
    };
  }
  if (mediaType.startsWith("audio/")) {
    return {
      kind: "audio",
      uri: asset.localUri,
      label: asset.filename,
    };
  }
  return {
    kind: "document",
    uri: asset.localUri,
    label: asset.filename,
  };
}

function readableActivityType(activityType: ActivitySummary["activity_type"]): string {
  return activityType
    .split("_")
    .map((part: string) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDateTime(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    return value;
  }
  return dateLabel.format(new Date(timestamp));
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: "#f7faf8",
    paddingHorizontal: 24,
    paddingVertical: 28,
    gap: 14,
  },
  topBar: {
    width: "100%",
    alignItems: "center",
    justifyContent: "space-between",
    flexDirection: "row",
  },
  title: {
    color: "#0c2f24",
    fontSize: 26,
    fontWeight: "700",
  },
  body: {
    color: "#25433a",
    fontSize: 16,
    lineHeight: 22,
  },
  button: {
    borderRadius: 12,
    backgroundColor: "#00573d",
    paddingHorizontal: 14,
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: "center",
  },
  buttonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "600",
  },
  secondaryButton: {
    borderRadius: 12,
    backgroundColor: "#dfeee8",
    paddingHorizontal: 14,
    paddingVertical: 10,
    minHeight: 44,
    alignSelf: "flex-start",
    justifyContent: "center",
  },
  secondaryButtonText: {
    color: "#0d3a2d",
    fontSize: 15,
    fontWeight: "600",
  },
  tertiaryButton: {
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: "center",
  },
  tertiaryButtonText: {
    color: "#0d3a2d",
    fontSize: 15,
    fontWeight: "600",
  },
  stateBlock: {
    gap: 10,
    alignItems: "flex-start",
  },
  alertCard: {
    borderRadius: 12,
    backgroundColor: "#eef5f1",
    borderWidth: 1,
    borderColor: "#c2d8ce",
    padding: 14,
    gap: 10,
  },
  alertTitle: {
    color: "#0d3a2d",
    fontSize: 17,
    fontWeight: "700",
  },
  editorBlock: {
    gap: 12,
    marginTop: 8,
  },
  evidencePanel: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#f7fbf9",
    padding: 12,
    gap: 10,
  },
  previewCard: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#ffffff",
    padding: 10,
    gap: 8,
  },
  previewImage: {
    width: "100%",
    height: 180,
    borderRadius: 8,
    backgroundColor: "#f1f7f4",
  },
  input: {
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#b8cfc4",
    backgroundColor: "#ffffff",
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: "#0d3a2d",
    fontSize: 16,
  },
  multilineInput: {
    minHeight: 132,
  },
  choiceList: {
    gap: 8,
  },
  choiceOption: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#b8cfc4",
    backgroundColor: "#ffffff",
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  choiceOptionSelected: {
    borderColor: "#00573d",
    backgroundColor: "#d8eee4",
  },
  choiceOptionText: {
    color: "#1e4438",
    fontSize: 15,
  },
  choiceOptionTextSelected: {
    color: "#0d3a2d",
    fontWeight: "700",
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  confirmPanel: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#f1f7f4",
    padding: 12,
    gap: 10,
  },
  readOnlyBlock: {
    gap: 8,
  },
  unsavedText: {
    color: "#8c5300",
    fontSize: 14,
    fontWeight: "600",
  },
  errorText: {
    color: "#8a1f17",
    fontSize: 14,
    lineHeight: 20,
  },
  successText: {
    color: "#16653a",
    fontSize: 14,
    lineHeight: 20,
  },
  contentBlock: {
    gap: 16,
  },
  panelTabs: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
  },
  panelTab: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#9fbfb2",
    backgroundColor: "#ffffff",
    paddingHorizontal: 14,
    paddingVertical: 8,
    minHeight: 40,
    justifyContent: "center",
  },
  panelTabActive: {
    borderColor: "#00573d",
    backgroundColor: "#d8eee4",
  },
  panelTabText: {
    color: "#1e4438",
    fontSize: 14,
    fontWeight: "600",
  },
  panelTabTextActive: {
    color: "#0d3a2d",
  },
  sectionGroup: {
    gap: 16,
  },
  section: {
    gap: 10,
  },
  sectionTitle: {
    color: "#0c2f24",
    fontSize: 19,
    fontWeight: "700",
  },
  refreshRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  studyList: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  studyChip: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#93b8aa",
    backgroundColor: "#ffffff",
    paddingHorizontal: 12,
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: "center",
  },
  studyChipSelected: {
    borderColor: "#00573d",
    backgroundColor: "#d8eee4",
  },
  studyChipText: {
    color: "#1e4438",
    fontSize: 15,
  },
  studyChipTextSelected: {
    color: "#0d3a2d",
    fontWeight: "700",
  },
  activityCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#ffffff",
    padding: 14,
    gap: 6,
    minHeight: 72,
  },
  card: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#ffffff",
    padding: 14,
    gap: 8,
  },
  messageRow: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#d1e2db",
    backgroundColor: "#f9fcfa",
    padding: 10,
    gap: 6,
  },
  cardTitle: {
    color: "#0d3a2d",
    fontSize: 17,
    fontWeight: "700",
  },
  metaLine: {
    color: "#35574c",
    fontSize: 14,
    lineHeight: 20,
  },
  disabledButton: {
    opacity: 0.55,
  },
  disabledPrimaryButton: {
    opacity: 0.55,
  },
});
