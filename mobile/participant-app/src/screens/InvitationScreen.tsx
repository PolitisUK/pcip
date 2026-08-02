import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

type InvitationScreenProps = {
  token: string;
};

function obfuscateToken(token: string): string {
  if (token.length <= 6) {
    return "***";
  }
  return `${token.slice(0, 3)}...${token.slice(-3)}`;
}

export function InvitationScreen({ token }: InvitationScreenProps) {
  const tokenPreview = useMemo(() => obfuscateToken(token), [token]);

  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Invitation Link Received
      </Text>
      <Text style={styles.body}>
        The invitation token has been parsed from the deep link and is ready for secure exchange with the participant session API.
      </Text>
      <Text accessibilityLabel="Invitation token preview" style={styles.tokenPreview}>
        Token preview: {tokenPreview}
      </Text>
      <Text style={styles.body}>
        This foundation intentionally does not persist invitation tokens and does not yet call the exchange endpoint.
      </Text>
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
  tokenPreview: {
    color: "#123f31",
    fontSize: 15,
    fontWeight: "600",
  },
});
