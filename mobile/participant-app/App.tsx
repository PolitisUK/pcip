import "react-native-gesture-handler";

import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { linking } from "./src/navigation/deepLinks";
import type { RootStackParamList } from "./src/navigation/types";
import { HomeScreen } from "./src/screens/HomeScreen";
import { InvitationScreen } from "./src/screens/InvitationScreen";
import { clearSessionMaterial, loadSessionMaterial } from "./src/services/sessionStore";

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  const [isLoading, setIsLoading] = useState(true);
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    let mounted = true;

    (async () => {
      const existingSession = await loadSessionMaterial();
      if (mounted) {
        setHasSession(Boolean(existingSession));
        setIsLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  if (isLoading) {
    return (
      <View accessibilityLabel="Loading mobile shell" style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#00573d" />
      </View>
    );
  }

  return (
    <NavigationContainer linking={linking} fallback={<ActivityIndicator />}>
      <StatusBar style="dark" />
      <Stack.Navigator>
        <Stack.Screen name="Home" options={{ title: "Participant" }}>
          {() => (
            <HomeScreen
              hasSession={hasSession}
              onResetSession={async () => {
                await clearSessionMaterial();
                setHasSession(false);
              }}
            />
          )}
        </Stack.Screen>
        <Stack.Screen name="Invitation" options={{ title: "Invitation" }}>
          {({ route }) => <InvitationScreen token={route.params.token} />}
        </Stack.Screen>
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f7faf8",
  },
});
