import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { CitizenCentricLogo } from "../components/CitizenCentricLogo";

export function ProcessingInvitationScreen() {
  return (
    <View style={styles.container}>
      <CitizenCentricLogo variant="full" />
      <ActivityIndicator accessibilityLabel="Joining your study" size="large" color="#00573d" />
      <Text accessibilityRole="header" style={styles.title}>
        Joining your study
      </Text>
      <Text style={styles.body}>We are checking your invitation securely.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f7faf8",
    paddingHorizontal: 24,
    gap: 14,
  },
  title: {
    color: "#0c2f24",
    fontSize: 24,
    fontWeight: "700",
    textAlign: "center",
  },
  body: {
    color: "#25433a",
    fontSize: 16,
    lineHeight: 22,
    textAlign: "center",
  },
});
