import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";

interface ConsentScreenProps {
  onAccept: () => void;
  onDecline: () => void;
}

const buttonStyle = {
  alignItems: "center" as const,
  backgroundColor: "#173f5f",
  justifyContent: "center" as const,
  minHeight: 48,
  paddingHorizontal: 20,
};

export function ConsentScreen({ onAccept, onDecline }: ConsentScreenProps) {
  const [declined, setDeclined] = useState(false);

  function declineConsent(): void {
    setDeclined(true);
  }

  return (
    <ScrollView contentContainerStyle={{ flexGrow: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />
      <Text accessibilityRole="header" style={{ fontSize: 24, fontWeight: "700" }}>
        {t("consent.title")}
      </Text>
      <Text>{t("consent.ai_disclosure")}</Text>
      <Text>{t("consent.human_review")}</Text>
      <Text>{t("consent.right_to_human")}</Text>
      <Text>{t("consent.what_we_record")}</Text>
      <Pressable
        accessibilityLabel={t("consent.accept")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false, selected: false }}
        onPress={onAccept}
        style={buttonStyle}
      >
        <Text style={{ color: "#ffffff", fontSize: 18 }}>{t("consent.accept")}</Text>
      </Pressable>
      <Pressable
        accessibilityLabel={t("consent.decline")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false, selected: declined }}
        onPress={declineConsent}
        style={[buttonStyle, { backgroundColor: "#ffffff", borderColor: "#173f5f", borderWidth: 2 }]}
      >
        <Text style={{ color: "#173f5f", fontSize: 18 }}>{t("consent.decline")}</Text>
      </Pressable>
      {declined ? (
        <View style={{ gap: 16 }}>
          <Text accessibilityRole="text">{t("consent.declined_note")}</Text>
          <TalkToPersonButton onPress={onDecline} />
        </View>
      ) : null}
    </ScrollView>
  );
}
