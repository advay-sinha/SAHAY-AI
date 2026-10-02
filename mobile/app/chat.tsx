import { useRouter } from "expo-router";
import { useEffect } from "react";
import { ChatScreen } from "../src/screens/ChatScreen";
import { useSessionSnapshot, useSessionStore } from "../src/session/SessionProvider";

export default function ChatRoute() {
  const router = useRouter();
  const store = useSessionStore();
  const { session, conversation } = useSessionSnapshot();

  useEffect(() => {
    store.connectConversation();
  }, [store, session]);

  // AI turns are shown only for a granted session. A declined session still
  // writes to the human officer; the server runs no analysis on it.
  const consent = session?.consent ?? "pending";

  return (
    <ChatScreen
      aiPermitted={consent === "granted"}
      consent={consent}
      onRequestHuman={() => router.push("/handoff")}
      onSend={(text) => store.sendChat(text)}
      receivedMessages={conversation.events}
    />
  );
}
