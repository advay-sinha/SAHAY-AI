import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import {
  selectMyRequestsPresentation,
  type MyRequestsLoadState,
} from "./myRequestsState";

interface MyRequestsScreenProps {
  loadState: MyRequestsLoadState;
  onRequestHuman: () => void;
  onRetry?: () => void;
  payload?: unknown;
}

export function MyRequestsScreen({
  loadState,
  onRequestHuman,
  onRetry,
  payload,
}: MyRequestsScreenProps) {
  const presentation = selectMyRequestsPresentation(loadState, payload);

  return (
    <ScrollView
      contentContainerStyle={{ flexGrow: 1, gap: 16, padding: 16 }}
      keyboardShouldPersistTaps="handled"
    >
      <AiDisclosure />
      <Text accessibilityRole="header" allowFontScaling style={{ fontSize: 24 }}>
        {t("timeline.title")}
      </Text>

      <View style={{ flex: 1, gap: 16 }}>
        {presentation.kind === "loading" ? (
          <Text
            accessibilityLabel={t("timeline.loading")}
            accessibilityLiveRegion="polite"
            accessibilityRole="text"
            allowFontScaling
            style={{ fontSize: 18 }}
          >
            {t("timeline.loading")}
          </Text>
        ) : null}

        {presentation.kind === "empty" ? (
          <Text
            accessibilityLabel={t("timeline.empty")}
            accessibilityRole="text"
            allowFontScaling
            style={{ fontSize: 18 }}
          >
            {t("timeline.empty")}
          </Text>
        ) : null}

        {presentation.kind === "unavailable" ? (
          <Text
            accessibilityLabel={t("error.title")}
            accessibilityRole="text"
            allowFontScaling
            style={{ fontSize: 18 }}
          >
            {t("error.title")}
          </Text>
        ) : null}

        {presentation.kind === "failed" ? (
          <View style={{ gap: 12 }}>
            <Text
              accessibilityLabel={t("error.body")}
              accessibilityLiveRegion="polite"
              accessibilityRole="text"
              allowFontScaling
              style={{ fontSize: 18 }}
            >
              {t("error.body")}
            </Text>
            {onRetry ? (
              <Pressable
                accessibilityLabel={t("error.retry")}
                accessibilityRole="button"
                accessibilityState={{ disabled: false }}
                onPress={onRetry}
                style={{ justifyContent: "center", minHeight: 48, paddingHorizontal: 16 }}
              >
                <Text allowFontScaling style={{ fontSize: 18 }}>
                  {t("error.retry")}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {presentation.kind === "timeline" ? (
          <View style={{ gap: 16 }}>
            <View
              accessible
              accessibilityLabel={`${t("timeline.reference")}: ${presentation.reference}`}
              accessibilityRole="text"
              style={{ gap: 4 }}
            >
              <Text allowFontScaling style={{ fontSize: 16 }}>
                {t("timeline.reference")}
              </Text>
              <Text allowFontScaling style={{ fontSize: 20 }}>
                {presentation.reference}
              </Text>
            </View>
            {presentation.entries.map((entry, index) => (
              <View
                accessible
                accessibilityLabel={entry.label}
                accessibilityRole="text"
                key={`${entry.stage}:${index}`}
                style={{ paddingVertical: 8 }}
              >
                <Text allowFontScaling style={{ fontSize: 18 }}>
                  {entry.label}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
      </View>

      <TalkToPersonButton onPress={onRequestHuman} />
    </ScrollView>
  );
}
