import { Pressable, Text } from "react-native";
import { t } from "../i18n";

/**
 * Persistent on every conversational screen. One tap, immediate, never in a
 * menu, never buried or delayed. Available regardless of consent state.
 */
export function TalkToPersonButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("human.button")}
      onPress={onPress}
      style={{ minHeight: 56, justifyContent: "center", paddingHorizontal: 16 }}
    >
      <Text style={{ fontSize: 18 }}>{t("human.button")}</Text>
    </Pressable>
  );
}
