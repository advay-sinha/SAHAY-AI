import { Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";

/** TalkScreen. P0 scaffold. Wired in P1 per mobile/CLAUDE.md. */
export function TalkScreen() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <AiDisclosure />
      <Text>TalkScreen</Text>
    </View>
  );
}
