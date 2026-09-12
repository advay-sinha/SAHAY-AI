import { useRef, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";

interface ConsentScreenProps {
  onAccept: () => void;
  onDecline: () => void;
}

const buttonStyle = {
  alignItems: "center" as const,
  backgroundColor: theme.colors.navySecondary,
  borderRadius: theme.radius.large,
  justifyContent: "center" as const,
  minHeight: theme.size.button,
  paddingHorizontal: 20,
  paddingVertical: 12,
};

export function ConsentScreen({ onAccept, onDecline }: ConsentScreenProps) {
  const [declined, setDeclined] = useState(false);
  const decisionStarted = useRef(false);

  function acceptConsent(): void {
    if (decisionStarted.current) return;
    decisionStarted.current = true;
    onAccept();
  }

  function declineConsent(): void {
    if (decisionStarted.current) return;
    decisionStarted.current = true;
    setDeclined(true);
    onDecline();
  }

  return (
    <SafeScreen>
    <ScrollView
      contentContainerStyle={{ flexGrow: 1, gap: 16, padding: 16, backgroundColor: theme.colors.canvas }}
      keyboardShouldPersistTaps="handled"
    >
      <AiDisclosure />
      <Text accessibilityRole="header" allowFontScaling style={typeStyles.title}>
        {t("consent.title")}
      </Text>
      <SurfaceCard elevated tone="navy" style={{ gap: theme.space.md, padding: theme.space.lg }}>
        {([
          ["consent.ai_disclosure", "wave", "teal"],
          ["consent.human_review", "shield", "navy"],
          ["consent.right_to_human", "pair", "teal"],
          ["consent.what_we_record", "tiles", "navy"],
        ] as const).map(([key, pattern, tone]) => (
          <SurfaceCard
            key={key}
            style={{ alignItems: "center", flexDirection: "row", gap: theme.space.md, padding: theme.space.md }}
          >
            <DecorativeMark pattern={pattern} size={36} tone={tone} />
            <Text allowFontScaling style={[typeStyles.bodyMedium, { flex: 1 }]}>{t(key)}</Text>
          </SurfaceCard>
        ))}
      </SurfaceCard>
      <Pressable
        accessibilityLabel={t("consent.accept")}
        accessibilityRole="button"
        accessibilityState={{ disabled: declined, selected: false }}
        disabled={declined}
        onPress={acceptConsent}
        style={({ pressed }) => [buttonStyle, pressed && !declined ? pressFeedbackStyle : null]}
      >
        <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.card, textAlign: "center" }]}>
          {t("consent.accept")}
        </Text>
      </Pressable>
      <Pressable
        accessibilityLabel={t("consent.decline")}
        accessibilityRole="button"
        accessibilityState={{ disabled: declined, selected: declined }}
        disabled={declined}
        onPress={declineConsent}
        style={({ pressed }) => [
          buttonStyle,
          { backgroundColor: theme.colors.card, borderColor: theme.colors.navy, borderWidth: 2 },
          pressed && !declined ? pressFeedbackStyle : null,
        ]}
      >
        <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.navy, textAlign: "center" }]}>
          {t("consent.decline")}
        </Text>
      </Pressable>
      {declined ? (
        <View style={{ gap: 16 }}>
          <SurfaceCard tone="teal">
            <Text accessibilityRole="text" allowFontScaling style={typeStyles.body}>
              {t("consent.declined_note")}
            </Text>
          </SurfaceCard>
          <TalkToPersonButton onPress={onDecline} />
        </View>
      ) : null}
    </ScrollView>
    </SafeScreen>
  );
}
