import { Pressable, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { t, type Lang } from "../i18n";

interface LanguageScreenProps {
  onSelectLanguage: (lang: Lang) => void;
}

const buttonStyle = {
  alignItems: "center" as const,
  backgroundColor: "#173f5f",
  justifyContent: "center" as const,
  minHeight: 48,
  paddingHorizontal: 20,
};

export function LanguageScreen({ onSelectLanguage }: LanguageScreenProps) {
  return (
    <View style={{ flex: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />
      <Text accessibilityRole="header" style={{ fontSize: 24, fontWeight: "700" }}>
        {t("language.title")}
      </Text>
      <Pressable
        accessibilityLabel={t("language.hindi")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={() => onSelectLanguage("hi")}
        style={buttonStyle}
      >
        <Text style={{ color: "#ffffff", fontSize: 18 }}>{t("language.hindi")}</Text>
      </Pressable>
      <Pressable
        accessibilityLabel={t("language.english")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={() => onSelectLanguage("en")}
        style={buttonStyle}
      >
        <Text style={{ color: "#ffffff", fontSize: 18 }}>{t("language.english")}</Text>
      </Pressable>
    </View>
  );
}
