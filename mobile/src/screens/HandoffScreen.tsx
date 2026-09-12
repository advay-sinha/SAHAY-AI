import { useEffect, useRef, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import {
  createHandoffRequestController,
  type HandoffRequestController,
  type HandoffState,
} from "./handoffState";

interface HandoffScreenProps {
  onRequestHuman: () => Promise<void>;
}

export function HandoffScreen({ onRequestHuman }: HandoffScreenProps) {
  const [state, setState] = useState<HandoffState>("idle");
  const requestCallbackRef = useRef(onRequestHuman);
  requestCallbackRef.current = onRequestHuman;

  const controllerRef = useRef<HandoffRequestController | null>(null);
  if (controllerRef.current === null) {
    controllerRef.current = createHandoffRequestController(
      () => requestCallbackRef.current(),
      setState,
    );
  }

  useEffect(() => {
    const controller = controllerRef.current;
    return () => controller?.dispose();
  }, []);

  function requestHuman(): void {
    void controllerRef.current?.request();
  }

  const isRequesting = state === "requesting";

  return (
    <ScrollView
      contentContainerStyle={{ flexGrow: 1, gap: 16, padding: 16 }}
      keyboardShouldPersistTaps="handled"
    >
      <AiDisclosure />
      {state === "requested" ? (
        <Text accessibilityLiveRegion="polite" accessibilityRole="text" allowFontScaling>
          {t("human.requested")}
        </Text>
      ) : (
        <View style={{ gap: 16 }}>
          {state === "failed" ? (
            <Text accessibilityLiveRegion="polite" accessibilityRole="text" allowFontScaling>
              {t("error.body")}
            </Text>
          ) : null}
          <TalkToPersonButton
            busy={isRequesting}
            disabled={isRequesting}
            label={state === "failed" ? t("error.retry") : t("human.button")}
            onPress={requestHuman}
          />
        </View>
      )}
    </ScrollView>
  );
}
