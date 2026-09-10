import { Text } from "react-native";
import { t } from "../i18n";

/** Visible throughout intake, not only on the consent screen. */
export function AiDisclosure() {
  return (
    <Text accessibilityRole="text" style={{ fontSize: 13 }}>
      {t("disclosure.persistent")}
    </Text>
  );
}
