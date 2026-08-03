import "react-native-gesture-handler";

import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { AuthController } from "./src/auth/authController";
import type { AuthState } from "./src/auth/types";
import { linking } from "./src/navigation/deepLinks";
import { routeNameForAuthState } from "./src/navigation/appStateRouter";
import type { RootStackParamList } from "./src/navigation/types";
import { AuthErrorScreen } from "./src/screens/AuthErrorScreen";
import { ConsentRequiredScreen } from "./src/screens/ConsentRequiredScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { ProcessingInvitationScreen } from "./src/screens/ProcessingInvitationScreen";
import { SignedOutScreen } from "./src/screens/SignedOutScreen";

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  const authController = useMemo(() => new AuthController(), []);
  const [authState, setAuthState] = useState<AuthState>({ status: "initialising" });

  useEffect(() => {
    const unsubscribe = authController.subscribe((state) => {
      setAuthState(state);
    });

    void authController.initialise();

    return () => {
      unsubscribe();
      authController.destroy();
    };
  }, [authController]);

  if (authState.status === "initialising") {
    return (
      <View accessibilityLabel="Loading Citizen Centric" style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#00573d" />
      </View>
    );
  }

  const currentRoute = routeNameForAuthState(authState);

  return (
    <NavigationContainer linking={linking} fallback={<ActivityIndicator />}>
      <StatusBar style="dark" />
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {currentRoute === "SignedOut" && (
          <Stack.Screen name="SignedOut">
            {() => <SignedOutScreen onRetry={() => void authController.retry()} />}
          </Stack.Screen>
        )}

        {currentRoute === "ProcessingInvitation" && (
          <Stack.Screen name="ProcessingInvitation" component={ProcessingInvitationScreen} />
        )}

        {currentRoute === "ConsentRequired" && authState.status === "consent_required" && (
          <Stack.Screen name="ConsentRequired">
            {() => (
              <ConsentRequiredScreen
                participantDisplayName={authState.participantDisplayName}
                onSignOut={() => void authController.signOut()}
              />
            )}
          </Stack.Screen>
        )}

        {currentRoute === "AuthenticatedHome" && authState.status === "authenticated" && (
          <Stack.Screen name="AuthenticatedHome">
            {() => (
              <HomeScreen
                participantDisplayName={authState.participantDisplayName}
                onSignOut={() => void authController.signOut()}
              />
            )}
          </Stack.Screen>
        )}

        {(currentRoute === "RecoverableError" || currentRoute === "TerminalError") &&
          (authState.status === "recoverable_error" || authState.status === "terminal_error") && (
          <Stack.Screen name={currentRoute}>
            {() => (
              <AuthErrorScreen
                state={authState}
                onRetry={() => void authController.retry()}
                onSignOut={() => void authController.signOut()}
              />
            )}
          </Stack.Screen>
        )}
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
