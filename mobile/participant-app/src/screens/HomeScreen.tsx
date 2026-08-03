import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiRequestError } from "../api/client";
import {
  getCurrentSession,
  getParticipantActivityDetail,
  type ActivityDetailResponse,
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

type ActivityDetailViewState =
  | { status: "idle" }
  | { status: "loading"; activityId: number }
  | { status: "ready"; activityId: number; detail: ActivityDetailResponse }
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
    };
  }, [controller, onSessionExpired, participantDisplayName]);

  useEffect(() => {
    if (homeState.status === "session_expired") {
      onSessionExpired();
    }
  }, [homeState, onSessionExpired]);

  const participantName = resolveParticipantName(homeState, participantDisplayName);

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

      setDetailState({ status: "ready", activityId, detail });
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

  const showDetail = detailState.status !== "idle";

  if (showDetail) {
    return (
      <ScrollView contentContainerStyle={styles.container}>
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
            <Text style={styles.metaLine}>
              Response: {readableResponseStatus(detailState.detail.response.status || undefined)}
            </Text>
            {detailState.detail.response.updated_at ? (
              <Text style={styles.metaLine}>Last updated: {formatDateTime(detailState.detail.response.updated_at)}</Text>
            ) : null}
            {detailState.detail.response.submitted_at ? (
              <Text style={styles.metaLine}>Submitted: {formatDateTime(detailState.detail.response.submitted_at)}</Text>
            ) : null}
            {typeof detailState.detail.response.value?.evidence_id === "number" ? (
              <Text style={styles.metaLine}>Evidence reference: #{detailState.detail.response.value.evidence_id}</Text>
            ) : null}
          </View>
        )}
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
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
              {homeState.requiresStudySelection ? (
                <Text style={styles.body}>Choose a study to view its activities.</Text>
              ) : null}
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
});
