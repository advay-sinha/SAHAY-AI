import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, PersistentFooter, SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";
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
    <SafeScreen>
    <View style={{ flex: 1, gap: 16, padding: 16, backgroundColor: theme.colors.canvas }}>
      <AiDisclosure />
      <Text accessibilityRole="header" allowFontScaling style={typeStyles.title}>
        {t("timeline.title")}
      </Text>

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 16 }}
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1 }}
      >
        <View style={{ flex: 1, gap: 16 }}>
          {presentation.kind === "loading" ? (
            <SurfaceCard tone="navy" style={{ alignItems: "center", gap: theme.space.md }}>
            <DecorativeMark pattern="bridge" tone="teal" />
            <Text
              accessibilityLabel={t("timeline.loading")}
              accessibilityLiveRegion="polite"
              accessibilityRole="text"
              allowFontScaling
              style={typeStyles.body}
            >
              {t("timeline.loading")}
            </Text>
            </SurfaceCard>
          ) : null}

          {presentation.kind === "empty" ? (
            <SurfaceCard style={{ alignItems: "center", gap: theme.space.md }}>
            <DecorativeMark pattern="center" />
            <Text
              accessibilityLabel={t("timeline.empty")}
              accessibilityRole="text"
              allowFontScaling
              style={typeStyles.body}
            >
              {t("timeline.empty")}
            </Text>
            </SurfaceCard>
          ) : null}

          {presentation.kind === "unavailable" ? (
            <SurfaceCard tone="recessed" style={{ alignItems: "center", gap: theme.space.md }}>
            <DecorativeMark pattern="shield" />
            <Text
              accessibilityLabel={t("error.title")}
              accessibilityRole="text"
              allowFontScaling
              style={typeStyles.body}
            >
              {t("error.title")}
            </Text>
            </SurfaceCard>
          ) : null}

          {presentation.kind === "failed" ? (
            <View style={{ gap: 12 }}>
              <SurfaceCard tone="danger" style={{ alignItems: "center", gap: theme.space.md }}>
              <DecorativeMark pattern="center" tone="danger" />
              <Text
                accessibilityLabel={t("error.body")}
                accessibilityLiveRegion="polite"
                accessibilityRole="text"
                allowFontScaling
                style={typeStyles.body}
              >
                {t("error.body")}
              </Text>
              </SurfaceCard>
              {onRetry ? (
                <Pressable
                  accessibilityLabel={t("error.retry")}
                  accessibilityRole="button"
                  accessibilityState={{ disabled: false }}
                  onPress={onRetry}
                  style={({ pressed }) => [{ alignItems: "center", backgroundColor: theme.colors.navySecondary, borderRadius: theme.radius.large, justifyContent: "center", minHeight: theme.size.button, paddingHorizontal: 16 }, pressed ? pressFeedbackStyle : null]}
                >
                  <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.card }]}>
                    {t("error.retry")}
                  </Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {presentation.kind === "timeline" ? (
            <View style={{ gap: 16 }}>
              <SurfaceCard
                accessible
                accessibilityLabel={`${t("timeline.reference")}: ${presentation.reference}`}
                accessibilityRole="text"
                elevated
                tone="navy"
                style={{ gap: theme.space.xs, padding: theme.space.xl }}
              >
                <Text allowFontScaling style={typeStyles.detail}>
                  {t("timeline.reference")}
                </Text>
                <Text allowFontScaling style={typeStyles.heading}>
                  {presentation.reference}
                </Text>
              </SurfaceCard>
              <SurfaceCard style={{ padding: theme.space.lg }}>
                {presentation.entries.map((entry, index) => (
                  <View
                    accessible
                    accessibilityLabel={entry.label}
                    accessibilityRole="text"
                    key={`${entry.stage}:${index}`}
                    style={{ flexDirection: "row", gap: theme.space.md, minHeight: 64 }}
                  >
                    <View
                      accessibilityElementsHidden
                      importantForAccessibility="no-hide-descendants"
                      style={{ alignItems: "center", width: 36 }}
                    >
                      <View style={{ alignItems: "center", backgroundColor: index === 0 ? theme.colors.teal : theme.colors.navySurface, borderColor: theme.colors.teal, borderRadius: 16, borderWidth: 2, height: 32, justifyContent: "center", width: 32 }}>
                        <View style={{ backgroundColor: theme.colors.navy, borderRadius: 4, height: 8, width: 8 }} />
                      </View>
                      {index < presentation.entries.length - 1 ? (
                        <View style={{ backgroundColor: theme.colors.border, flex: 1, width: 2 }} />
                      ) : null}
                    </View>
                    <View style={{ borderBottomColor: theme.colors.border, borderBottomWidth: index < presentation.entries.length - 1 ? 1 : 0, flex: 1, paddingBottom: theme.space.lg, paddingTop: theme.space.xs }}>
                      <Text allowFontScaling style={typeStyles.body}>{entry.label}</Text>
                    </View>
                  </View>
                ))}
              </SurfaceCard>
            </View>
          ) : null}
        </View>
      </ScrollView>

      <PersistentFooter>
        <TalkToPersonButton onPress={onRequestHuman} />
      </PersistentFooter>
    </View>
    </SafeScreen>
  );
}
