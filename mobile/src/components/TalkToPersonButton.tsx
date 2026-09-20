import { Pressable, Text, View } from "react-native";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";
import { DecorativeMark } from "./Presentation";

interface Props {
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  label?: string;
}

export function TalkToPersonButton({ onPress, disabled = false, busy = false, label = t("human.button") }: Props) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ busy, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        {
          alignItems: "center",
          backgroundColor: disabled ? theme.colors.disabled : theme.colors.navySecondary,
          borderColor: disabled ? theme.colors.outline : theme.colors.navySecondary,
          borderRadius: theme.radius.large,
          borderWidth: 1,
          flexDirection: "row",
          gap: theme.space.md,
          minHeight: 56,
          paddingHorizontal: theme.space.lg,
          paddingVertical: theme.space.md,
        },
        pressed && !disabled ? pressFeedbackStyle : null,
      ]}
    >
      <DecorativeMark pattern="pair" size={36} tone="teal" />
      <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.card, flex: 1 }]}>{label}</Text>
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={{ width: 20, height: 20, borderColor: theme.colors.tealSoft, borderRadius: 10, borderWidth: 2 }}
      />
    </Pressable>
  );
}
