import { Image, type ImageStyle, StyleSheet, View } from "react-native";

type CitizenCentricLogoProps = {
  variant: "full" | "compact";
  style?: ImageStyle;
};

const FULL_LOGO = require("../../assets/citizen-centric-logo.png");
const COMPACT_LOGO = require("../../assets/citizen-centric-logo-compact.png");

export function CitizenCentricLogo({ variant, style }: CitizenCentricLogoProps) {
  const isFull = variant === "full";

  return (
    <View style={isFull ? styles.fullWrap : styles.compactWrap}>
      <Image
        accessible
        accessibilityLabel="Citizen Centric by Politis"
        resizeMode="contain"
        testID={isFull ? "citizen-centric-logo-full" : "citizen-centric-logo-compact"}
        source={isFull ? FULL_LOGO : COMPACT_LOGO}
        style={[isFull ? styles.full : styles.compact, style]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fullWrap: {
    alignItems: "center",
    width: "100%",
  },
  compactWrap: {
    alignItems: "center",
    justifyContent: "center",
  },
  full: {
    width: "100%",
    maxWidth: 360,
    height: 120,
  },
  compact: {
    width: 48,
    height: 48,
  },
});