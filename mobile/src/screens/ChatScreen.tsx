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
import { SafeScreen, SurfaceCard } from "../components/Presentation";
import { TalkToPersonButton } from "../components/TalkToPersonButton";
import { t } from "../i18n";
import { pressFeedbackStyle, theme, typeStyles } from "../theme";
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
  onSend: (text: string, localId: number) => Promise<void>;
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
      (text, localId) => sendCallbackRef.current(text, localId),
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
    <SafeScreen>
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, gap: 12, padding: 16, backgroundColor: theme.colors.canvas }}
    >
      <View style={{ gap: 12 }}>
        <AiDisclosure />
      </View>

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, gap: 12, justifyContent: "flex-end", paddingVertical: 8 }}
        keyboardDismissMode="none"
        keyboardShouldPersistTaps="handled"
        style={{ flex: 1 }}
      >
        {displayMessages.map((message) => (
          <View key={message.id} style={{ alignSelf: "flex-start", gap: theme.space.xs, maxWidth: "88%" }}>
            <Text accessibilityRole="header" allowFontScaling style={[typeStyles.caption, { color: theme.colors.navy }]}>
              {t(message.labelKey)}
            </Text>
            <SurfaceCard
              tone={message.labelKey === "chat.human_officer" ? "teal" : "navy"}
              style={{ borderTopLeftRadius: theme.radius.small, padding: theme.space.lg }}
            >
              <Text accessibilityRole="text" allowFontScaling style={typeStyles.body}>
                {message.text}
              </Text>
            </SurfaceCard>
          </View>
        ))}

        {state.messages.map((message) => (
          <View key={message.id} style={{ alignSelf: "flex-end", gap: theme.space.xs, maxWidth: "88%" }}>
            <Text accessibilityRole="text" allowFontScaling style={{ backgroundColor: theme.colors.navySecondary, borderRadius: theme.radius.large, borderTopRightRadius: theme.radius.small, color: theme.colors.card, fontSize: 17, lineHeight: 26, padding: theme.space.lg }}>
              {message.text}
            </Text>
            <Text
              accessibilityLiveRegion="polite"
              accessibilityRole="text"
              allowFontScaling
              style={{ color: message.status === "failed" ? theme.colors.danger : theme.colors.muted, fontSize: 15, lineHeight: 20, textAlign: "right" }}
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
                style={({ pressed }) => [{ alignItems: "center", alignSelf: "flex-end", backgroundColor: theme.colors.dangerSoft, borderRadius: theme.radius.medium, justifyContent: "center", minHeight: 48, paddingHorizontal: 16 }, pressed && !isPending ? pressFeedbackStyle : null]}
              >
                <Text allowFontScaling style={[typeStyles.label, { color: theme.colors.danger }]}>
                  {t("error.retry")}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ))}
      <View style={{ gap: theme.space.md, paddingTop: theme.space.md }}>
        <TalkToPersonButton onPress={onRequestHuman} />
        <SurfaceCard elevated style={{ gap: theme.space.sm, padding: theme.space.md }}>
        <View style={{ alignItems: "flex-end", flexDirection: "row", gap: theme.space.sm }}>
          <TextInput
          accessibilityHint={t("chat.placeholder")}
          accessibilityLabel={t("chat.placeholder")}
          accessibilityState={{ disabled: isPending }}
          allowFontScaling
          editable={!isPending}
          multiline
          onChangeText={(text) => controllerRef.current?.setDraft(text)}
          placeholder={t("chat.placeholder")}
          scrollEnabled
          style={{
            backgroundColor: theme.colors.card,
            borderColor: theme.colors.outline,
            borderRadius: theme.radius.medium,
            borderWidth: 1.5,
            color: theme.colors.ink,
            fontSize: 17,
            lineHeight: 24,
            maxHeight: 96,
            flex: 1,
            minHeight: theme.size.button,
            padding: theme.space.md,
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
          style={({ pressed }) => [{
            alignItems: "center",
            backgroundColor: canSend ? theme.colors.navySecondary : theme.colors.disabled,
            borderRadius: theme.radius.medium,
            justifyContent: "center",
            minHeight: theme.size.button,
            minWidth: 88,
            paddingHorizontal: 16,
            paddingVertical: 12,
          }, pressed && canSend ? pressFeedbackStyle : null]}
        >
          <Text allowFontScaling style={[typeStyles.label, { color: canSend ? theme.colors.card : theme.colors.muted }]}>
            {t("chat.send")}
          </Text>
          </Pressable>
        </View>
        </SurfaceCard>
      </View>
      </ScrollView>
    </KeyboardAvoidingView>
    </SafeScreen>
  );
}
