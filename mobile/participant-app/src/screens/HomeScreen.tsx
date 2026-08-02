import { Pressable, StyleSheet, Text, View } from "react-native";

type HomeScreenProps = {
  hasSession: boolean;
  onResetSession: () => void;
};

export function HomeScreen({ hasSession, onResetSession }: HomeScreenProps) {
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Citizen Centric Participant
      </Text>
      <Text style={styles.body}>
        Mobile foundation shell is ready. Invitation deep-link routing and secure session storage are configured.
      </Text>
      <Text style={styles.body}>Session stored: {hasSession ? "yes" : "no"}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Clear secure session"
        style={styles.button}
        onPress={onResetSession}
      >
        <Text style={styles.buttonText}>Clear secure session</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f7faf8",
    paddingHorizontal: 24,
    paddingVertical: 28,
    gap: 14,
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
    alignSelf: "flex-start",
    marginTop: 12,
    borderRadius: 12,
    backgroundColor: "#00573d",
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  buttonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "600",
  },
});
