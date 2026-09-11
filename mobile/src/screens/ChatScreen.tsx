import { useEffect, useMemo, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { AiDisclosure } from "../components/AiDisclosure";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import {
  createChatSendController,
  selectDisplayMessages,
  type ChatSendController,
  type ChatState,
  type ConsentStatus,
} from "./chatState";

interface ChatScreenProps {
  aiPermitted: boolean;
  consent: ConsentStatus;
  onRequestHuman: () => void;
  onSend: (text: string) => Promise<void>;
  receivedMessages?: readonly unknown[];
}

const initialState: ChatState = { draft: "", messages: [] };

export function ChatScreen({
  aiPermitted,
  consent,
  onRequestHuman,
  onSend,
  receivedMessages = [],
}: ChatScreenProps) {
  const [state, setState] = useState<ChatState>(initialState);
  const sendCallbackRef = useRef(onSend);
  sendCallbackRef.current = onSend;

  const controllerRef = useRef<ChatSendController | null>(null);
  if (controllerRef.current === null) {
    controllerRef.current = createChatSendController(
      (text) => sendCallbackRef.current(text),
      setState,
    );
  }

  useEffect(() => {
    const controller = controllerRef.current;
    return () => controller?.dispose();
  }, []);

  const displayMessages = useMemo(
    () => selectDisplayMessages(receivedMessages, consent, aiPermitted),
    [aiPermitted, consent, receivedMessages],
  );
  const isPending = state.messages.some((message) => message.status === "pending");
  const canSend = state.draft.trim().length > 0 && !isPending;

  function send(): void {
    void controllerRef.current?.send();
  }

  function retry(id: number): void {
    void controllerRef.current?.retry(id);
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, gap: 12, padding: 16 }}
    >
      <View style={{ gap: 12 }}>
        <AiDisclosure />
      </View>

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 12, justifyContent: "flex-end" }}
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1 }}
      >
        {displayMessages.map((message) => (
          <View key={message.id} style={{ gap: 4, paddingVertical: 8 }}>
            <Text accessibilityRole="header" allowFontScaling style={{ fontSize: 16 }}>
              {t(message.labelKey)}
            </Text>
            <Text accessibilityRole="text" allowFontScaling style={{ fontSize: 18 }}>
              {message.text}
            </Text>
          </View>
        ))}

        {state.messages.map((message) => (
          <View key={message.id} style={{ gap: 4, paddingVertical: 8 }}>
            <Text accessibilityRole="text" allowFontScaling style={{ fontSize: 18 }}>
              {message.text}
            </Text>
            <Text
              accessibilityLiveRegion="polite"
              accessibilityRole="text"
              allowFontScaling
              style={{ fontSize: 16 }}
            >
              {message.status === "pending"
                ? t("chat.pending")
                : message.status === "sent"
                  ? t("chat.sent")
                  : t("error.body")}
            </Text>
            {message.status === "failed" ? (
              <Pressable
                accessibilityLabel={t("error.retry")}
                accessibilityRole="button"
                accessibilityState={{ disabled: isPending }}
                disabled={isPending}
                onPress={() => retry(message.id)}
                style={{ justifyContent: "center", minHeight: 48, paddingHorizontal: 16 }}
              >
                <Text allowFontScaling style={{ fontSize: 18 }}>
                  {t("error.retry")}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ))}
      </ScrollView>

      <View style={{ gap: 8 }}>
        <TextInput
          accessibilityHint={t("chat.placeholder")}
          accessibilityLabel={t("chat.placeholder")}
          accessibilityState={{ disabled: isPending }}
          allowFontScaling
          editable={!isPending}
          multiline
          onChangeText={(text) => controllerRef.current?.setDraft(text)}
          placeholder={t("chat.placeholder")}
          style={{
            borderColor: "#56636d",
            borderWidth: 1,
            fontSize: 18,
            maxHeight: 160,
            minHeight: 48,
            padding: 12,
            textAlignVertical: "top",
          }}
          value={state.draft}
        />
        <Pressable
          accessibilityLabel={t("chat.send")}
          accessibilityRole="button"
          accessibilityState={{ busy: isPending, disabled: !canSend }}
          disabled={!canSend}
          onPress={send}
          style={{
            alignItems: "center",
            justifyContent: "center",
            minHeight: 48,
            opacity: canSend ? 1 : 0.65,
            paddingHorizontal: 16,
          }}
        >
          <Text allowFontScaling style={{ fontSize: 18 }}>
            {t("chat.send")}
          </Text>
        </Pressable>
        <TalkToPersonButton onPress={onRequestHuman} />
      </View>
    </KeyboardAvoidingView>
  );
}
