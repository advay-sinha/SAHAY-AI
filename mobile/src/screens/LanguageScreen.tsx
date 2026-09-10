import { Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";

/** LanguageScreen. P0 scaffold. Wired in P1 per mobile/CLAUDE.md. */
export function LanguageScreen() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <AiDisclosure />
      <Text>LanguageScreen</Text>
    </View>
  );
}
