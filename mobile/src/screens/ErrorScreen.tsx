import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, PersistentFooter, SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";
import { createErrorActions } from "./errorActions";

interface ErrorScreenProps {
  onRequestHuman: () => void;
  onRetry: () => void;
}

export function ErrorScreen({ onRequestHuman, onRetry }: ErrorScreenProps) {
  const { requestHuman, retry } = createErrorActions({ onRequestHuman, onRetry });

  return (
    <SafeScreen>
    <View style={{ flex: 1, gap: 16, padding: 16, backgroundColor: theme.colors.canvas }}>
      <AiDisclosure />

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 16 }}
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1 }}
      >
        <SurfaceCard elevated tone="recessed" style={{ alignItems: "center", gap: theme.space.lg, justifyContent: "center", marginTop: theme.space.xl, minHeight: 280 }}>
          <DecorativeMark pattern="shield" size={72} tone="danger" />
          <Text accessibilityRole="header" allowFontScaling style={[typeStyles.title, { textAlign: "center" }]}>
            {t("error.title")}
          </Text>
          <Text accessibilityRole="text" allowFontScaling style={[typeStyles.body, { textAlign: "center" }]}>
            {t("error.body")}
          </Text>
        </SurfaceCard>
        <Pressable
          accessibilityLabel={t("error.retry")}
          accessibilityRole="button"
          accessibilityState={{ disabled: false }}
          onPress={retry}
          style={({ pressed }) => [{ alignItems: "center", backgroundColor: theme.colors.navySecondary, borderRadius: theme.radius.large, justifyContent: "center", minHeight: theme.size.button, paddingHorizontal: 16, paddingVertical: 12 }, pressed ? pressFeedbackStyle : null]}
        >
          <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.card }]}>
            {t("error.retry")}
          </Text>
        </Pressable>
      </ScrollView>

      <PersistentFooter>
        <TalkToPersonButton onPress={requestHuman} />
      </PersistentFooter>
    </View>
    </SafeScreen>
  );
}
