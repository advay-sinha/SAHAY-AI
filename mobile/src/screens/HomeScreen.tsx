import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, PersistentFooter, SafeScreen } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";

const controlStyle = {
  alignItems: "center" as const,
  backgroundColor: theme.colors.card,
  borderColor: theme.colors.border,
  borderRadius: theme.radius.large,
  borderWidth: 1,
  flexDirection: "row" as const,
  gap: theme.space.md,
  minHeight: 84,
  padding: theme.space.lg,
};

interface HomeScreenProps {
  onOpenChat: () => void;
  onOpenRequests: () => void;
  onOpenTalk: () => void;
  onRequestHuman: () => void;
}

export function HomeScreen({
  onOpenChat,
  onOpenRequests,
  onOpenTalk,
  onRequestHuman,
}: HomeScreenProps) {
  const chatLabel = t("home.chat");
  const requestsLabel = t("home.my_requests");
  const talkLabel = t("home.talk");

  return (
    <SafeScreen>
      <View style={{ backgroundColor: theme.colors.canvas, flex: 1, gap: theme.space.md, padding: theme.space.lg }}>
        <AiDisclosure />
        <ScrollView
          contentContainerStyle={{ flexGrow: 1, gap: theme.space.md, paddingBottom: theme.space.sm }}
          style={{ flex: 1 }}
        >
          <Pressable
        accessibilityLabel={talkLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={onOpenTalk}
        style={({ pressed }) => [
          controlStyle,
          {
            alignItems: "stretch",
            backgroundColor: theme.colors.navySecondary,
            flexDirection: "column",
            minHeight: 168,
            padding: theme.space.xl,
          },
          pressed ? pressFeedbackStyle : null,
        ]}
      >
        <DecorativeMark pattern="wave" size={64} tone="teal" />
        <View style={{ alignSelf: "stretch", flex: 1, justifyContent: "flex-end" }}>
          <Text allowFontScaling style={[typeStyles.heading, { color: theme.colors.card, flexShrink: 1 }]}>
            {talkLabel}
          </Text>
        </View>
          </Pressable>
          <Pressable
        accessibilityLabel={chatLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={onOpenChat}
        style={({ pressed }) => [controlStyle, pressed ? pressFeedbackStyle : null]}
      >
        <DecorativeMark pattern="center" />
        <Text allowFontScaling style={[typeStyles.heading, { flex: 1, flexShrink: 1 }]}>
          {chatLabel}
        </Text>
          </Pressable>
          <Pressable
        accessibilityLabel={requestsLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={onOpenRequests}
        style={({ pressed }) => [controlStyle, pressed ? pressFeedbackStyle : null]}
      >
        <DecorativeMark pattern="tiles" tone="teal" />
        <Text allowFontScaling style={[typeStyles.heading, { flex: 1, flexShrink: 1 }]}>
          {requestsLabel}
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
