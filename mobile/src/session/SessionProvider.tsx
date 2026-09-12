/**
 * One process-lifetime, memory-only session authority for REST and live text.
 * Credentials cross only the private store-construction callback below; they
 * are never present in a public snapshot, screen prop, URL, storage, or log.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { ApiError } from '../net/apiCore';
import { configuredApiUrl, resolveApiBaseUrl } from '../net/apiConfig';
import type { FetchLike, ValidatedSession } from '../net/restClient';
import { SessionSocket } from '../net/socket';
import type { SocketControlFrame, VictimEvent } from '../types/events';
import {
  createSessionStore,
  type PublicSession,
  type SessionSnapshot,
  type SessionStore,
} from './sessionStore';

interface LiveSessionValue {
  session: PublicSession | null;
  events: readonly VictimEvent[];
  sendChat: (text: string, localId: number) => Promise<void>;
  requestHuman: () => Promise<void>;
}

interface SessionContextValue extends LiveSessionValue {
  store: SessionStore;
}

interface Pending {
  resolve: () => void;
  reject: (error?: unknown) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);
const platformFetch: FetchLike = (url, init) => fetch(url, init);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<readonly VictimEvent[]>([]);
  const liveSession = useRef<ValidatedSession | null>(null);
  const generation = useRef(0);
  const socketRef = useRef<SessionSocket | null>(null);
  const readyRef = useRef<Promise<void> | null>(null);
  const readyResolve = useRef<(() => void) | null>(null);
  const readyReject = useRef<((error?: unknown) => void) | null>(null);
  const chatSequence = useRef(0);
  const humanSequence = useRef(0);
  const chatIds = useRef(new Map<number, string>());
  const humanId = useRef<string | null>(null);
  const pendingChats = useRef(new Map<string, Pending>());
  const pendingHumans = useRef(new Map<string, Pending>());

  const rejectPending = useCallback(() => {
    const error = new ApiError('unavailable');
    for (const item of pendingChats.current.values()) item.reject(error);
    for (const item of pendingHumans.current.values()) item.reject(error);
    pendingChats.current.clear();
    pendingHumans.current.clear();
    readyReject.current?.(error);
    readyResolve.current = null;
    readyReject.current = null;
    readyRef.current = null;
  }, []);

  const invalidateLiveSession = useCallback((resetEvents: boolean) => {
    generation.current += 1;
    liveSession.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    rejectPending();
    chatIds.current.clear();
    humanId.current = null;
    chatSequence.current = 0;
    humanSequence.current = 0;
    if (resetEvents) setEvents([]);
  }, [rejectPending]);

  const [store] = useState(() => {
    const apiUrl = configuredApiUrl();
    return createSessionStore({
      apiUrl,
      fetchImpl: platformFetch,
      onCredentialChange: (session) => {
        invalidateLiveSession(true);
        if (session?.consent === 'granted') liveSession.current = session;
      },
    });
  });
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const socketConfig = useMemo(() => resolveApiBaseUrl(configuredApiUrl()), []);

  useEffect(() => () => invalidateLiveSession(false), [invalidateLiveSession]);

  const handleControl = useCallback((frame: SocketControlFrame) => {
    if (frame.type === 'auth.ok') {
      readyResolve.current?.();
      readyResolve.current = null;
      readyReject.current = null;
      return;
    }
    if (frame.type === 'chat.ack') {
      const pending = pendingChats.current.get(frame.client_message_id);
      if (!pending) return;
      pendingChats.current.delete(frame.client_message_id);
      if (frame.status === 'accepted' || frame.status === 'duplicate') pending.resolve();
      else pending.reject(new ApiError('unavailable'));
      return;
    }
    const pending = pendingHumans.current.get(frame.request_id);
    if (!pending) return;
    pendingHumans.current.delete(frame.request_id);
    if (frame.status === 'accepted' || frame.status === 'duplicate') pending.resolve();
    else pending.reject(new ApiError('unavailable'));
  }, []);

  const ensureSocket = useCallback((active: ValidatedSession): Promise<void> => {
    if (socketRef.current !== null && readyRef.current !== null) return readyRef.current;
    if (!socketConfig.ok || active.consent !== 'granted') {
      return Promise.reject(new ApiError('authentication'));
    }

    const startedAt = generation.current;
    readyRef.current = new Promise<void>((resolve, reject) => {
      readyResolve.current = resolve;
      readyReject.current = reject;
    });
    const current = () => liveSession.current === active && generation.current === startedAt;
    const socket = new SessionSocket({
      baseUrl: socketConfig.baseUrl.replace(/^http/, 'ws'),
      path: active.ws_url,
      sessionId: active.session_id,
      token: active.session_token,
      onControl: (frame) => {
        if (current()) handleControl(frame);
      },
      onEvent: (event) => {
        if (!current()) return;
        setEvents((existing) => {
          const turnId = 'turn_id' in event ? event.turn_id : null;
          if (turnId && existing.some((item) =>
            item.type === event.type && 'turn_id' in item && item.turn_id === turnId)) return existing;
          return [...existing, event];
        });
      },
      onStateChange: (state, code) => {
        if (state !== 'closed' || !current()) return;
        socketRef.current = null;
        rejectPending();
        if (code === 4401 || code === 4403) store.clearSession();
      },
    });
    socketRef.current = socket;
    socket.connect();
    return readyRef.current;
  }, [handleControl, rejectPending, socketConfig, store]);

  const sendChat = useCallback(async (text: string, localId: number): Promise<void> => {
    const active = liveSession.current;
    if (active === null) throw new ApiError('authentication');
    await ensureSocket(active);
    if (liveSession.current !== active) throw new ApiError('authentication');

    let id = chatIds.current.get(localId);
    if (!id) {
      chatSequence.current += 1;
      id = `m:${chatSequence.current}`;
      chatIds.current.set(localId, id);
    }
    if (pendingChats.current.has(id)) throw new ApiError('unavailable');
    const acknowledgement = new Promise<void>((resolve, reject) => {
      pendingChats.current.set(id!, { resolve, reject });
    });
    if (!socketRef.current?.sendText(id, text, active.lang)) {
      pendingChats.current.delete(id);
      throw new ApiError('unavailable');
    }
    return acknowledgement;
  }, [ensureSocket]);

  const requestHuman = useCallback(async (): Promise<void> => {
    const active = liveSession.current;
    if (active === null) throw new ApiError('authentication');
    await ensureSocket(active);
    if (liveSession.current !== active) throw new ApiError('authentication');

    if (humanId.current === null) {
      humanSequence.current += 1;
      humanId.current = `h:${humanSequence.current}`;
    }
    const id = humanId.current;
    if (pendingHumans.current.has(id)) throw new ApiError('unavailable');
    const acknowledgement = new Promise<void>((resolve, reject) => {
      pendingHumans.current.set(id, { resolve, reject });
    });
    if (!socketRef.current?.requestHuman(id)) {
      pendingHumans.current.delete(id);
      throw new ApiError('unavailable');
    }
    return acknowledgement;
  }, [ensureSocket]);

  const value = useMemo<SessionContextValue>(() => ({
    store,
    session: snapshot.session,
    events,
    sendChat,
    requestHuman,
  }), [events, requestHuman, sendChat, snapshot.session, store]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function useSessionContext(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('SessionProvider is missing');
  return value;
}

export function useSessionStore(): SessionStore {
  return useSessionContext().store;
}

export function useSessionSnapshot(): SessionSnapshot {
  const store = useSessionStore();
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}

export function useSession(): LiveSessionValue {
  const { session, events, sendChat, requestHuman } = useSessionContext();
  return { session, events, sendChat, requestHuman };
}
