import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createApiClient, type ApiClient } from "../api/client";
import { requestLogin, type LoginErrorKind } from "./login";
import {
  browserStore,
  clearSession,
  readSession,
  writeSession,
  type KeyValueStore,
  type Session,
} from "./session";

/**
 * Session state for the console.
 *
 * The only way a token enters the session is `login(username, password)`.
 * Nothing here reads the page URL.
 */

interface AuthValue {
  session: Session | null;
  api: ApiClient;
  login: (username: string, password: string) => Promise<LoginErrorKind | null>;
  logout: () => void;
  /** Re-read storage (dropping anything expired or invalid). No state change. */
  current: () => Session | null;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({
  children,
  store: injected,
}: {
  children: ReactNode;
  store?: KeyValueStore;
}) {
  const storeRef = useRef<KeyValueStore>(injected ?? browserStore());
  const store = storeRef.current;
  const [session, setSession] = useState<Session | null>(() => readSession(store));

  const logout = useCallback(() => {
    clearSession(store);
    setSession(null);
  }, [store]);

  const current = useCallback(() => readSession(store), [store]);

  const api = useMemo(
    () =>
      createApiClient({
        fetchFn: (...args) => fetch(...args),
        getToken: () => readSession(store)?.token ?? null,
        // A 401 anywhere: the token is no longer accepted. Drop it; the route
        // guard then sends the user to /login.
        onUnauthorized: logout,
      }),
    [store, logout],
  );

  const login = useCallback(
    async (username: string, password: string) => {
      const outcome = await requestLogin((...args) => fetch(...args), username, password);
      if (!outcome.ok) return outcome.error;
      const stored = writeSession(store, outcome.token, outcome.role, outcome.displayName);
      if (!stored) return "unavailable" as const; // token failed validation; store nothing
      setSession(stored);
      return null;
    },
    [store],
  );

  const value = useMemo(
    () => ({ session, api, login, logout, current }),
    [session, api, login, logout, current],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
