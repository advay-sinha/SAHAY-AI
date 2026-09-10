import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConnectionCheck } from "../components/ConnectionCheck";

/**
 * Live queue. The first authenticated call the console makes: GET /queue with
 * `Authorization: Bearer`. Case persistence lands in P2, so the queue is empty
 * for now; the empty, loading and error states are the real ones.
 *
 * A 401 is handled by the API client (session cleared, back to /login); this
 * page only has to render the other outcomes.
 */
export function QueuePage() {
  const { api } = useAuth();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .queue()
      .then((cases) => {
        if (cancelled) return;
        setCount(cases.length);
        setState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled || (err instanceof ApiError && err.status === 401)) return;
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <h1 className="text-xl font-medium">Live queue</h1>

      <section aria-live="polite" data-testid="queue-state">
        {state === "loading" && <p>Loading the queue…</p>}
        {state === "error" && <p>The queue could not be loaded. Try again shortly.</p>}
        {state === "ready" && count === 0 && <p>No cases are waiting.</p>}
        {state === "ready" && count > 0 && <p>{count} case(s) waiting.</p>}
      </section>

      <ConnectionCheck />
    </main>
  );
}
