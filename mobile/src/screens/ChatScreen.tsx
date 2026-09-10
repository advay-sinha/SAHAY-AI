import { Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";

/** ChatScreen. P0 scaffold. Wired in P1 per mobile/CLAUDE.md. */
export function ChatScreen() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <AiDisclosure />
      <Text>ChatScreen</Text>
    </View>
  );
}
