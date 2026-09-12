import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { SessionProvider } from "../src/session/SessionProvider";
import { theme } from "../src/theme";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar backgroundColor={theme.colors.canvas} style="dark" />
        <Stack screenOptions={{ contentStyle: { backgroundColor: theme.colors.canvas }, headerShown: false }} />
      </SessionProvider>
    </SafeAreaProvider>
  );
}
