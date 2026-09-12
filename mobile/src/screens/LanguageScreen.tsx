import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, SafeScreen } from "../components/Presentation";
import { t, type Lang } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";

interface LanguageScreenProps {
  onSelectLanguage: (lang: Lang) => void;
}

const buttonStyle = {
  alignItems: "center" as const,
  backgroundColor: theme.colors.card,
  borderColor: theme.colors.border,
  borderRadius: theme.radius.large,
  borderWidth: 1,
  flexDirection: "row" as const,
  gap: theme.space.md,
  minHeight: 88,
  paddingHorizontal: theme.space.lg,
  paddingVertical: theme.space.lg,
};

const pressedButtonStyle = {
  backgroundColor: theme.colors.navySurface,
  borderColor: theme.colors.teal,
  borderWidth: 2,
};

export function LanguageScreen({ onSelectLanguage }: LanguageScreenProps) {
  return (
    <SafeScreen>
    <ScrollView
      contentContainerStyle={{
        backgroundColor: theme.colors.canvas,
        flexGrow: 1,
        gap: theme.space.xl,
        padding: theme.space.lg,
        paddingTop: theme.space.xl,
      }}
      style={{ flex: 1 }}
    >
      <AiDisclosure />
      <Text accessibilityRole="header" allowFontScaling style={typeStyles.title}>
        {t("language.title")}
      </Text>
      <View style={{ gap: theme.space.md }}>
      <Pressable
        accessibilityLabel={t("language.hindi")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false, selected: false }}
        onPress={() => onSelectLanguage("hi")}
        style={({ pressed }) => [buttonStyle, pressed ? pressedButtonStyle : null, pressed ? pressFeedbackStyle : null]}
      >
        <DecorativeMark pattern="tiles" />
        <Text allowFontScaling style={[typeStyles.heading, { flex: 1 }]}>
          {t("language.hindi")}
        </Text>
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={{ borderColor: theme.colors.outline, borderRadius: 14, borderWidth: 2, height: 28, width: 28 }}
        />
      </Pressable>
      <Pressable
        accessibilityLabel={t("language.english")}
        accessibilityRole="button"
        accessibilityState={{ disabled: false, selected: false }}
        onPress={() => onSelectLanguage("en")}
        style={({ pressed }) => [buttonStyle, pressed ? pressedButtonStyle : null, pressed ? pressFeedbackStyle : null]}
      >
        <DecorativeMark pattern="tiles" tone="teal" />
        <Text allowFontScaling style={[typeStyles.heading, { flex: 1 }]}>
          {t("language.english")}
        </Text>
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={{ borderColor: theme.colors.outline, borderRadius: 14, borderWidth: 2, height: 28, width: 28 }}
        />
      </Pressable>
      </View>
    </ScrollView>
    </SafeScreen>
  );
}
