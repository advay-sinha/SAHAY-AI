/**
 * Root-level, memory-only holder for the one runtime victim session.
 *
 * The store is created once per app process and kept in React state. It is
 * never written to storage, a URL, or a log.
 */

import { createContext, useContext, useState, useSyncExternalStore, type ReactNode } from "react";
import { configuredApiUrl } from "../net/apiConfig";
import type { FetchLike } from "../net/restClient";
import { createSessionStore, type SessionSnapshot, type SessionStore } from "./sessionStore";

const SessionContext = createContext<SessionStore | null>(null);

const platformFetch: FetchLike = (url, init) => fetch(url, init);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() =>
    createSessionStore({ apiUrl: configuredApiUrl(), fetchImpl: platformFetch }),
  );

  return <SessionContext.Provider value={store}>{children}</SessionContext.Provider>;
}

export function useSessionStore(): SessionStore {
  const store = useContext(SessionContext);
  if (store === null) throw new Error("SessionProvider is missing");
  return store;
}

export function useSessionSnapshot(): SessionSnapshot {
  const store = useSessionStore();
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
