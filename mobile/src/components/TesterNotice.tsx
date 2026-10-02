import { Text } from "react-native";
import { t } from "../i18n";
import { testerBuild } from "../net/features";
import { theme, typeStyles } from "../theme";

/** Hosted tester builds only (EXT-130): fictional stories, never a real event. */
export function TesterNotice() {
  if (!testerBuild()) return null;
  return (
    <Text
      accessibilityRole="text"
      allowFontScaling
      style={[typeStyles.detail, { color: theme.colors.navy, fontWeight: "700" }]}
    >
      {t("disclosure.tester")}
    </Text>
  );
}
