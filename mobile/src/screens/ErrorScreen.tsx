import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { createErrorActions } from "./errorActions";

interface ErrorScreenProps {
  onRequestHuman: () => void;
  onRetry: () => void;
}

export function ErrorScreen({ onRequestHuman, onRetry }: ErrorScreenProps) {
  const { requestHuman, retry } = createErrorActions({ onRequestHuman, onRetry });

  return (
    <View style={{ flex: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 16 }}
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1 }}
      >
        <Text accessibilityRole="header" allowFontScaling style={{ fontSize: 24 }}>
          {t("error.title")}
        </Text>
        <Text accessibilityRole="text" allowFontScaling style={{ fontSize: 18 }}>
          {t("error.body")}
        </Text>
        <Pressable
          accessibilityLabel={t("error.retry")}
          accessibilityRole="button"
          accessibilityState={{ disabled: false }}
          onPress={retry}
          style={{ justifyContent: "center", minHeight: 48, paddingHorizontal: 16 }}
        >
          <Text allowFontScaling style={{ fontSize: 18 }}>
            {t("error.retry")}
          </Text>
        </Pressable>
      </ScrollView>

      <TalkToPersonButton onPress={requestHuman} />
    </View>
  );
}
