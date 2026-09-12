import { Pressable, ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";

interface TalkScreenProps {
  onOpenChat: () => void;
  onRequestHuman: () => void;
}

/** Presentation-only entry point for choosing another available conversation path. */
export function TalkScreen({ onOpenChat, onRequestHuman }: TalkScreenProps) {
  const chatLabel = t("home.chat");

  return (
    <View style={{ flex: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 24 }}
        style={{ flex: 1 }}
      >
        <Text accessibilityRole="header" allowFontScaling style={{ fontSize: 28 }}>
          {t("home.talk")}
        </Text>
        <Pressable
          accessibilityLabel={chatLabel}
          accessibilityRole="button"
          accessibilityState={{ disabled: false }}
          onPress={onOpenChat}
          style={{
            alignItems: "center",
            backgroundColor: "#ffffff",
            justifyContent: "center",
            minHeight: 48,
            paddingHorizontal: 20,
          }}
        >
          <Text allowFontScaling style={{ color: "#25313a", fontSize: 18 }}>
            {chatLabel}
          </Text>
        </Pressable>
      </ScrollView>
      <TalkToPersonButton onPress={onRequestHuman} />
    </View>
  );
}
