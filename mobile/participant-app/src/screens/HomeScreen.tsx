import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiRequestError } from "../api/client";
import {
  getCurrentSession,
  getParticipantActivityDetail,
  saveParticipantActivityDraft,
  submitParticipantActivityResponse,
  type ActivityDetailResponse,
  type DraftResponseRequest,
} from "../api/participantApi";
import { CitizenCentricLogo } from "../components/CitizenCentricLogo";
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

type ActivityEditorState = {
  draft: EditableResponseDraft;
  persisted: EditableResponseDraft;
  actionStatus: "idle" | "saving" | "submitting";
  confirmingSubmit: boolean;
  message: EditorMessage | null;
};

type ActivityDetailViewState =
  | { status: "idle" }
  | { status: "loading"; activityId: number }
  | { status: "ready"; activityId: number; detail: ActivityDetailResponse; editor: ActivityEditorState }
  | { status: "error"; activityId: number; message: string };

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
  const [detailState, setDetailState] = useState<ActivityDetailViewState>({ status: "idle" });
  const detailRequestVersion = useRef(0);
  const detailAbortController = useRef<AbortController | null>(null);
  const writeRequestVersion = useRef(0);
  const writeAbortController = useRef<AbortController | null>(null);

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
              participant_id: sessionMaterial.participantId ?? -1,
              display_name: sessionMaterial.participantDisplayName || participantDisplayName || "Participant",
              consent_status: sessionMaterial.consentStatus || "granted",
            },
            study_scope: sessionMaterial.studyScope || [],
          },
          preferredStudyId: sessionMaterial.studyScope?.[0],
        });
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
    };
  }, [controller, onSessionExpired, participantDisplayName]);

  useEffect(() => {
    if (homeState.status === "session_expired") {
      onSessionExpired();
    }
  }, [homeState, onSessionExpired]);

  const participantName = resolveParticipantName(homeState, participantDisplayName);

  const updateReadyDetail = (
    updater: (state: Extract<ActivityDetailViewState, { status: "ready" }>) => Extract<ActivityDetailViewState, { status: "ready" }>,
  ) => {
    setDetailState((current) => (current.status === "ready" ? updater(current) : current));
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

  const showDetail = detailState.status !== "idle";

  if (showDetail) {
    return (
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}>
          <CitizenCentricLogo variant="compact" />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back to studies"
            style={styles.tertiaryButton}
            onPress={() => setDetailState({ status: "idle" })}
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
}) {
  const isSubmitted = isSubmittedResponse(detail.response?.status);
  const supported = isSupportedResponseEntryType(detail.activity.activity_type);
  const dirty = isEditorDirty(editor);
  const choices = detail.activity.options || [];
  const actionBusy = editor.actionStatus !== "idle";
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
      {editor.message ? <InlineMessage message={editor.message} /> : null}

      <View style={styles.actionRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save draft response"
          accessibilityState={{ disabled: !dirty || actionBusy || missingChoiceOptions }}
          disabled={!dirty || actionBusy || missingChoiceOptions}
          onPress={onSaveDraft}
          style={[styles.secondaryButton, (!dirty || actionBusy || missingChoiceOptions) ? styles.disabledButton : null]}
        >
          <Text style={styles.secondaryButtonText}>{editor.actionStatus === "saving" ? "Saving draft" : "Save draft"}</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Review response before submitting"
          accessibilityState={{ disabled: actionBusy || missingChoiceOptions }}
          disabled={actionBusy || missingChoiceOptions}
          onPress={onReviewSubmit}
          style={[styles.button, (actionBusy || missingChoiceOptions) ? styles.disabledPrimaryButton : null]}
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

function createIdempotencyKey(action: "draft" | "submit", activityId: number): string {
  return `mob-${action}-${activityId}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
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
