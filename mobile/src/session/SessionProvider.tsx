import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, createSession as createRemoteSession, getActiveTimeline, getSocketBaseUrl, type ActiveSession, type Consent } from "../net/api";
import { SessionSocket } from "../net/socket";
import type { VictimTimeline } from "../net/victimPayload";
import type { ChatAck, HumanRequestAck, SocketControlFrame, VictimEvent } from "../types/events";

interface SessionContextValue {
  session: ActiveSession | null;
  events: readonly VictimEvent[];
  createSession: (consent: Consent) => Promise<ActiveSession>;
  clearSession: () => void;
  loadTimeline: () => Promise<VictimTimeline | null>;
  sendChat: (text: string, localId: number) => Promise<void>;
  requestHuman: () => Promise<void>;
}
interface Pending { resolve: () => void; reject: () => void; }

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<ActiveSession | null>(null);
  const [events, setEvents] = useState<readonly VictimEvent[]>([]);
  const sessionRef = useRef<ActiveSession | null>(null);
  const generation = useRef(0);
  const createPending = useRef<Promise<ActiveSession> | null>(null);
  const socketRef = useRef<SessionSocket | null>(null);
  const readyRef = useRef<Promise<void> | null>(null);
  const readyResolve = useRef<(() => void) | null>(null);
  const readyReject = useRef<(() => void) | null>(null);
  const chatSequence = useRef(0);
  const humanSequence = useRef(0);
  const chatIds = useRef(new Map<number, string>());
  const humanId = useRef<string | null>(null);
  const pendingChats = useRef(new Map<string, Pending>());
  const pendingHumans = useRef(new Map<string, Pending>());

  const rejectPending = useCallback(() => {
    for (const item of pendingChats.current.values()) item.reject();
    for (const item of pendingHumans.current.values()) item.reject();
    pendingChats.current.clear();
    pendingHumans.current.clear();
    readyReject.current?.();
    readyResolve.current = null;
    readyReject.current = null;
    readyRef.current = null;
  }, []);

  const clearSession = useCallback(() => {
    generation.current += 1;
    socketRef.current?.close();
    socketRef.current = null;
    rejectPending();
    sessionRef.current = null;
    chatIds.current.clear();
    humanId.current = null;
    chatSequence.current = 0;
    humanSequence.current = 0;
    setEvents([]);
    setSession(null);
  }, [rejectPending]);

  const createSession = useCallback((consent: Consent): Promise<ActiveSession> => {
    if (createPending.current !== null) return createPending.current;
    const startedAt = generation.current;
    const request = createRemoteSession(consent).then((created) => {
      if (generation.current !== startedAt) throw new ApiError("unavailable");
      generation.current += 1;
      sessionRef.current = created;
      setEvents([]);
      setSession(created);
      return created;
    }).finally(() => { createPending.current = null; });
    createPending.current = request;
    return request;
  }, []);

  const loadTimeline = useCallback(async (): Promise<VictimTimeline | null> => {
    const active = sessionRef.current;
    const startedAt = generation.current;
    if (active === null) throw new ApiError("authentication");
    try {
      const timeline = await getActiveTimeline(active);
      if (sessionRef.current !== active || generation.current !== startedAt) return null;
      return timeline;
    } catch (error) {
      if (error instanceof ApiError && error.kind === "authentication"
          && sessionRef.current === active && generation.current === startedAt) clearSession();
      throw error;
    }
  }, [clearSession]);

  const handleControl = useCallback((frame: SocketControlFrame) => {
    if (frame.type === "auth.ok") {
      readyResolve.current?.();
      readyResolve.current = null;
      readyReject.current = null;
      return;
    }
    if (frame.type === "chat.ack") {
      const pending = pendingChats.current.get(frame.client_message_id);
      if (!pending) return;
      pendingChats.current.delete(frame.client_message_id);
      frame.status === "accepted" || frame.status === "duplicate" ? pending.resolve() : pending.reject();
      return;
    }
    const pending = pendingHumans.current.get(frame.request_id);
    if (!pending) return;
    pendingHumans.current.delete(frame.request_id);
    frame.status === "accepted" || frame.status === "duplicate" ? pending.resolve() : pending.reject();
  }, []);

  const ensureSocket = useCallback((active: ActiveSession): Promise<void> => {
    if (socketRef.current !== null && readyRef.current !== null) return readyRef.current;
    const startedAt = generation.current;
    readyRef.current = new Promise<void>((resolve, reject) => {
      readyResolve.current = resolve;
      readyReject.current = reject;
    });
    const socket = new SessionSocket({
      baseUrl: getSocketBaseUrl(), path: active.ws_url, sessionId: active.session_id,
      token: active.session_token,
      onControl: handleControl,
      onEvent: (event) => {
        if (sessionRef.current !== active || generation.current !== startedAt) return;
        setEvents((current) => {
          const turnId = "turn_id" in event ? event.turn_id : null;
          if (turnId && current.some((item) => item.type === event.type && "turn_id" in item && item.turn_id === turnId)) return current;
          return [...current, event];
        });
      },
      onStateChange: (state, code) => {
        if (state !== "closed" || sessionRef.current !== active || generation.current !== startedAt) return;
        socketRef.current = null;
        rejectPending();
        if (code === 4401 || code === 4403) clearSession();
      },
    });
    socketRef.current = socket;
    socket.connect();
    return readyRef.current;
  }, [clearSession, handleControl, rejectPending]);

  const sendChat = useCallback(async (text: string, localId: number): Promise<void> => {
    const active = sessionRef.current;
    if (active === null) throw new ApiError("authentication");
    await ensureSocket(active);
    if (sessionRef.current !== active) throw new ApiError("authentication");
    let id = chatIds.current.get(localId);
    if (!id) {
      chatSequence.current += 1;
      id = `m:${chatSequence.current}`;
      chatIds.current.set(localId, id);
    }
    const acknowledgement = new Promise<void>((resolve, reject) => pendingChats.current.set(id!, { resolve, reject }));
    if (!socketRef.current?.sendText(id, text, active.lang)) {
      pendingChats.current.delete(id);
      throw new ApiError("unavailable");
    }
    return acknowledgement;
  }, [ensureSocket]);

  const requestHuman = useCallback(async (): Promise<void> => {
    const active = sessionRef.current;
    if (active === null) throw new ApiError("authentication");
    await ensureSocket(active);
    if (humanId.current === null) {
      humanSequence.current += 1;
      humanId.current = `h:${humanSequence.current}`;
    }
    const id = humanId.current;
    const acknowledgement = new Promise<void>((resolve, reject) => pendingHumans.current.set(id, { resolve, reject }));
    if (!socketRef.current?.requestHuman(id)) {
      pendingHumans.current.delete(id);
      throw new ApiError("unavailable");
    }
    return acknowledgement;
  }, [ensureSocket]);

  const value = useMemo(() => ({ session, events, createSession, clearSession, loadTimeline, sendChat, requestHuman }),
    [session, events, createSession, clearSession, loadTimeline, sendChat, requestHuman]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("SessionProvider is required");
  return value;
}
