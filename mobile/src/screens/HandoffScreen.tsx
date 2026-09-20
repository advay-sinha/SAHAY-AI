import { useEffect, useRef, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { DecorativeMark, PersistentFooter, SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { theme, typeStyles } from "../theme";
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
    controllerRef.current = createHandoffRequestController(() => requestCallbackRef.current(), setState);
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
    <SafeScreen>
      <View style={{ backgroundColor: theme.colors.canvas, flex: 1, gap: 16, padding: 16 }}>
        <AiDisclosure />
        <ScrollView
          contentContainerStyle={{ flexGrow: 1, gap: 16, justifyContent: "center" }}
          keyboardShouldPersistTaps="handled"
          style={{ flex: 1 }}
        >
          {state === "requested" ? (
            <SurfaceCard elevated tone="teal" style={{ alignItems: "center", gap: theme.space.lg, minHeight: 224, justifyContent: "center" }}>
              <DecorativeMark pattern="shield" size={72} tone="teal" />
              <Text
                accessibilityLiveRegion="polite"
                accessibilityRole="text"
                allowFontScaling
                style={[typeStyles.heading, { textAlign: "center" }]}
              >
                {t("human.requested")}
              </Text>
            </SurfaceCard>
          ) : (
            <SurfaceCard
              elevated
              tone={state === "failed" ? "danger" : state === "requesting" ? "recessed" : "navy"}
              style={{ alignItems: "center", gap: theme.space.lg, justifyContent: "center", minHeight: 224 }}
            >
              <DecorativeMark
                pattern={state === "failed" ? "center" : state === "requesting" ? "bridge" : "pair"}
                size={72}
                tone={state === "failed" ? "danger" : "teal"}
              />
              <Text accessibilityRole="header" allowFontScaling style={[typeStyles.heading, { textAlign: "center" }] }>
                {t("human.button")}
              </Text>
              {state === "failed" ? (
                <Text accessibilityLiveRegion="polite" accessibilityRole="text" allowFontScaling style={[typeStyles.body, { color: theme.colors.danger, textAlign: "center" }]}>
                  {t("error.body")}
                </Text>
              ) : null}
            </SurfaceCard>
          )}
        </ScrollView>
        <PersistentFooter>
          {state !== "requested" ? (
            <TalkToPersonButton
              busy={isRequesting}
              disabled={isRequesting}
              label={state === "failed" ? t("error.retry") : t("human.button")}
              onPress={requestHuman}
            />
          ) : null}
        </PersistentFooter>
      </View>
    </SafeScreen>
  );
}
