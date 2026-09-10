import { Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";

/** ConsentScreen. P0 scaffold. Wired in P1 per mobile/CLAUDE.md. */
export function ConsentScreen() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <AiDisclosure />
      <Text>ConsentScreen</Text>
    </View>
  );
}
