import { Text, View } from "react-native";
import { t } from "../i18n";
import { theme, typeStyles } from "../theme";
import { DecorativeMark } from "./Presentation";

export function AiDisclosure() {
  const label = t("disclosure.persistent");
  return (
    <View
      accessible
      accessibilityLabel={label}
      accessibilityRole="text"
      style={{
        alignItems: "center",
        backgroundColor: theme.colors.surfaceLow,
        borderColor: theme.colors.border,
        borderRadius: theme.radius.large,
        borderWidth: 1,
        flexDirection: "row",
        gap: theme.space.md,
        minHeight: 64,
        paddingHorizontal: theme.space.md,
        paddingVertical: theme.space.sm,
      }}
    >
      <DecorativeMark pattern="shield" size={44} tone="teal" />
      <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ flex: 1, gap: theme.space.xs }}>
        <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: theme.colors.teal }} />
        <Text style={[typeStyles.detail, { color: theme.colors.navy, fontWeight: "600" }]}>{label}</Text>
      </View>
    </View>
  );
}
