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
  onRequestHuman: () => void;
}

export function HomeScreen({ onRequestHuman }: HomeScreenProps) {
  const disabledControls = ["home.chat", "home.my_requests"] as const;

  return (
    <View style={{ flex: 1, gap: 16, padding: 16 }}>
      <AiDisclosure />
      <TalkToPersonButton onPress={onRequestHuman} />
      {disabledControls.map((key) => {
        const label = t(key);

        return (
          <Pressable
            accessibilityLabel={label}
            accessibilityRole="button"
            accessibilityState={{ disabled: true }}
            disabled
            key={key}
            style={disabledControlStyle}
          >
            <Text style={{ color: "#25313a", fontSize: 18 }}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}
