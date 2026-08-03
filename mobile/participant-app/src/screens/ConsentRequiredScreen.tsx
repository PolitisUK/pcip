import { Pressable, StyleSheet, Text, View } from "react-native";

type ConsentRequiredScreenProps = {
  participantDisplayName?: string;
  onSignOut: () => void;
};

export function ConsentRequiredScreen({ participantDisplayName, onSignOut }: ConsentRequiredScreenProps) {
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Citizen Centric consent needed
      </Text>
      <Text style={styles.body}>
        {participantDisplayName
          ? `Hello ${participantDisplayName}.`
          : "You are signed in."} We still need consent confirmation before entering your participant space.
      </Text>
      <Text style={styles.body}>Please complete consent with your research team using your invitation guidance.</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Sign out"
        onPress={onSignOut}
        style={styles.button}
      >
        <Text style={styles.buttonText}>Sign out</Text>
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
    fontSize: 24,
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
