import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, PersistentFooter, SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";

interface TalkScreenProps {
  onOpenChat: () => void;
  onRequestHuman: () => void;
}

/** Presentation-only entry point for choosing another available conversation path. */
export function TalkScreen({ onOpenChat, onRequestHuman }: TalkScreenProps) {
  const chatLabel = t("home.chat");

  return (
    <SafeScreen>
    <View style={{ flex: 1, gap: 16, padding: 16, backgroundColor: theme.colors.canvas }}>
      <AiDisclosure />
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 24, paddingBottom: 8 }}
        style={{ flex: 1 }}
      >
        <Text accessibilityRole="header" allowFontScaling style={typeStyles.title}>
          {t("home.talk")}
        </Text>
        <SurfaceCard
          elevated
          tone="navy"
          style={{
            alignItems: "center",
            justifyContent: "center",
            minHeight: 264,
            overflow: "hidden",
          }}
        >
          <View
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            style={{
              alignItems: "center",
              backgroundColor: theme.colors.card,
              borderColor: theme.colors.tealSoft,
              borderRadius: 72,
              borderWidth: 12,
              height: 144,
              justifyContent: "center",
              width: 144,
            }}
          >
            <DecorativeMark pattern="wave" size={88} tone="teal" />
          </View>
        </SurfaceCard>
        <Pressable
          accessibilityLabel={chatLabel}
          accessibilityRole="button"
          accessibilityState={{ disabled: false }}
          onPress={onOpenChat}
          style={({ pressed }) => [{
            alignItems: "center",
            backgroundColor: theme.colors.card,
            borderColor: theme.colors.border,
            borderRadius: theme.radius.large,
            borderWidth: 1,
            justifyContent: "center",
            minHeight: 48,
            paddingHorizontal: 20,
            paddingVertical: 14,
          }, pressed ? pressFeedbackStyle : null]}
        >
          <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.navy }] }>
            {chatLabel}
          </Text>
        </Pressable>
      </ScrollView>
      <PersistentFooter>
        <TalkToPersonButton onPress={onRequestHuman} />
      </PersistentFooter>
    </View>
    </SafeScreen>
  );
}
