import { HandoffScreen } from "../src/screens/HandoffScreen";

async function unavailableHumanRequest(): Promise<void> {
  throw new Error();
}

export default function HandoffRoute() {
  return <HandoffScreen onRequestHuman={unavailableHumanRequest} />;
}
