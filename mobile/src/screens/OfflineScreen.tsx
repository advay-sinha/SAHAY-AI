import { Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";

/** OfflineScreen. P0 scaffold. Wired in P1 per mobile/CLAUDE.md. */
export function OfflineScreen() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <AiDisclosure />
      <Text>OfflineScreen</Text>
    </View>
  );
}
