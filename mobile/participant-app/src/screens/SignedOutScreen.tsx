import { Pressable, StyleSheet, Text, View } from "react-native";

type SignedOutScreenProps = {
  onRetry: () => void;
};

export function SignedOutScreen({ onRetry }: SignedOutScreenProps) {
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Citizen Centric
      </Text>
      <Text style={styles.body}>Open your study invitation link to sign in securely.</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Restore saved session"
        onPress={onRetry}
        style={styles.button}
      >
        <Text style={styles.buttonText}>Restore saved session</Text>
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
