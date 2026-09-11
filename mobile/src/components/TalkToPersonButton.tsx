import { Pressable, Text } from "react-native";
import { t } from "../i18n";

interface TalkToPersonButtonProps {
  busy?: boolean;
  disabled?: boolean;
  label?: string;
  onPress: () => void;
}

/**
 * Persistent on every conversational screen. One tap, immediate, never in a
 * menu, never buried or delayed. Available regardless of consent state.
 */
export function TalkToPersonButton({
  busy = false,
  disabled = false,
  label = t("human.button"),
  onPress,
}: TalkToPersonButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ busy, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={{
        justifyContent: "center",
        minHeight: 56,
        opacity: disabled ? 0.65 : 1,
        paddingHorizontal: 16,
      }}
    >
      <Text allowFontScaling style={{ fontSize: 18 }}>
        {label}
      </Text>
    </Pressable>
  );
}
