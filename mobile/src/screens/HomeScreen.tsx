import { Pressable, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";

const disabledControlStyle = {
  alignItems: "center" as const,
  backgroundColor: "#d7dde2",
  justifyContent: "center" as const,
  minHeight: 48,
  opacity: 0.65,
  paddingHorizontal: 20,
};

interface HomeScreenProps {
  onOpenChat: () => void;
  onRequestHuman: () => void;
}

export function HomeScreen({ onOpenChat, onRequestHuman }: HomeScreenProps) {
  const chatLabel = t("home.chat");
  const requestsLabel = t("home.my_requests");

  return (
    <View style={{ flex: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />
      <TalkToPersonButton onPress={onRequestHuman} />
      <Pressable
        accessibilityLabel={chatLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: false }}
        onPress={onOpenChat}
        style={{ ...disabledControlStyle, backgroundColor: "#ffffff", opacity: 1 }}
      >
        <Text allowFontScaling style={{ color: "#25313a", fontSize: 18 }}>
          {chatLabel}
        </Text>
      </Pressable>
      <Pressable
        accessibilityLabel={requestsLabel}
        accessibilityRole="button"
        accessibilityState={{ disabled: true }}
        disabled
        style={disabledControlStyle}
      >
        <Text allowFontScaling style={{ color: "#25313a", fontSize: 18 }}>
          {requestsLabel}
        </Text>
      </Pressable>
    </View>
  );
}
