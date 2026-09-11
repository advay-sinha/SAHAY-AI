import { useRouter } from "expo-router";
import { ChatScreen } from "../src/screens/ChatScreen";

async function unavailableSend(_text: string): Promise<void> {
  throw new Error();
}

export default function ChatRoute() {
  const router = useRouter();

  return (
    <ChatScreen
      aiPermitted={false}
      consent="pending"
      onRequestHuman={() => router.push("/handoff")}
      onSend={unavailableSend}
    />
  );
}
