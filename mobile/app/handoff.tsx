import { HandoffScreen } from "../src/screens/HandoffScreen";
import { useSession } from "../src/session/SessionProvider";

export default function HandoffRoute() {
  const { requestHuman } = useSession();
  return <HandoffScreen onRequestHuman={requestHuman} />;
}
