/**
 * The victim's live conversation socket: text turns up, victim-safe events down.
 *
 * Owned by the session store, which passes the token in and never exposes it.
 * The token reaches only the socket URL, in the transitional query form that
 * CONTRACTS.md section 1 (PC-05) permits for the text-first slice; it is never
 * stored in state, logged or returned.
 *
 * Every incoming frame goes through the allowlist validator in victimPayload;
 * anything else is dropped. The server already filters by role, so this is
 * defence in depth, not the primary control.
 *
 * A sent message counts as delivered when the server echoes it back as the
 * victim's transcript line. Without that echo it fails, and the screen offers
 * a retry. A dropped connection reconnects with backoff (a hosted backend may
 * be waking from sleep); a refused one (policy violation) does not.
 */

const { parseVictimEvent } = require("./victimPayload");

const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000];
const MAX_RECONNECTS = 30;
const ECHO_TIMEOUT_MS = 20000;
const CLOSE_POLICY_VIOLATION = 1008;
const OPEN = 1;

function socketBaseUrl(httpBaseUrl) {
  if (httpBaseUrl.startsWith("https://")) return `wss://${httpBaseUrl.slice("https://".length)}`;
  if (httpBaseUrl.startsWith("http://")) return `ws://${httpBaseUrl.slice("http://".length)}`;
  return null;
}

function createConversation({
  baseUrl,
  sessionId,
  token,
  lang,
  socketFactory,
  onChange,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const wsBase = socketBaseUrl(baseUrl);
  let socket = null;
  let stopped = false;
  let reconnects = 0;
  let reconnectTimer = null;
  let status = "idle";
  let events = [];
  let sessionStatus = null;
  let pendingEcho = null;

  function emit() {
    onChange(Object.freeze({ status, events, sessionStatus }));
  }

  function settleEcho(error) {
    if (pendingEcho === null) return;
    const { resolve, reject, timer } = pendingEcho;
    pendingEcho = null;
    clearTimer(timer);
    if (error) reject(error);
    else resolve();
  }

  function receive(raw) {
    const event = parseVictimEvent(raw);
    if (event === null) return;
    if (event.type === "session.status") {
      sessionStatus = Object.freeze({ ...event });
    } else {
      events = Object.freeze([...events, Object.freeze({ ...event })]);
      if (event.type === "transcript.line" && event.speaker === "victim") settleEcho(null);
    }
    emit();
  }

  function scheduleReconnect() {
    if (stopped || reconnects >= MAX_RECONNECTS) {
      status = "closed";
      emit();
      return;
    }
    const delay = RECONNECT_DELAYS_MS[Math.min(reconnects, RECONNECT_DELAYS_MS.length - 1)];
    reconnects += 1;
    status = "reconnecting";
    emit();
    reconnectTimer = setTimer(() => {
      reconnectTimer = null;
      open();
    }, delay);
  }

  function open() {
    if (stopped) return;
    if (wsBase === null) {
      status = "closed";
      emit();
      return;
    }
    status = reconnects === 0 ? "connecting" : "reconnecting";
    emit();

    let current;
    try {
      current = socketFactory(
        `${wsBase}/ws/session/${encodeURIComponent(sessionId)}?token=${encodeURIComponent(token)}`,
      );
    } catch {
      scheduleReconnect();
      return;
    }
    socket = current;

    current.onopen = () => {
      if (socket !== current || stopped) return;
      reconnects = 0;
      status = "open";
      emit();
    };
    current.onmessage = (message) => {
      if (socket !== current || stopped) return;
      if (typeof message.data === "string") receive(message.data);
    };
    current.onerror = () => {};
    current.onclose = (event) => {
      if (socket !== current) return;
      socket = null;
      settleEcho(new Error("closed"));
      if (stopped) return;
      if (event && event.code === CLOSE_POLICY_VIOLATION) {
        status = "closed";
        emit();
        return;
      }
      scheduleReconnect();
    };
  }

  function sendFrame(frame) {
    if (stopped || socket === null || socket.readyState !== OPEN) return false;
    try {
      socket.send(JSON.stringify(frame));
      return true;
    } catch {
      return false;
    }
  }

  return {
    connect() {
      if (stopped || status !== "idle") return;
      open();
    },

    /** Resolves when the server echoes the turn; rejects if it cannot be sent or is not echoed. */
    sendChat(text) {
      if (pendingEcho !== null) return Promise.reject(new Error("busy"));
      return new Promise((resolve, reject) => {
        if (!sendFrame({ type: "chat.message", text, lang })) {
          reject(new Error("offline"));
          return;
        }
        const timer = setTimer(() => settleEcho(new Error("timeout")), ECHO_TIMEOUT_MS);
        pendingEcho = { resolve, reject, timer };
      });
    },

    requestHuman() {
      return sendFrame({ type: "request_human" })
        ? Promise.resolve()
        : Promise.reject(new Error("offline"));
    },

    close() {
      stopped = true;
      if (reconnectTimer !== null) clearTimer(reconnectTimer);
      reconnectTimer = null;
      settleEcho(new Error("closed"));
      const current = socket;
      socket = null;
      if (current !== null) {
        try {
          current.close();
        } catch {
          // Already closed.
        }
      }
      status = "closed";
    },
  };
}

module.exports = { createConversation, socketBaseUrl };
