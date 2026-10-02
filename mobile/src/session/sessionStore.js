/**
 * The one runtime victim session, in memory only.
 *
 * The token lives in this closure and nowhere else. It is not part of the
 * snapshot the screens read, so no component, prop, log or error can carry
 * it. Nothing is persisted: when the process ends the session is gone.
 *
 * Timeline requests use only the case_id from the validated session. Each
 * request is tagged; a response that arrives after the session changed, or
 * after a newer request started, is dropped.
 */

const { resolveApiBaseUrl } = require("../net/apiConfig");
const { createConversation } = require("../net/conversation");
const { createSession, fetchTimeline } = require("../net/restClient");

const IDLE_TIMELINE = Object.freeze({ status: "idle", payload: null });
const IDLE_CONVERSATION = Object.freeze({ status: "idle", events: Object.freeze([]), sessionStatus: null });
const OPEN_WAIT_MS = 30000;

function publicSession(session) {
  return Object.freeze({
    session_id: session.session_id,
    case_id: session.case_id,
    reference_no: session.reference_no,
    ws_url: session.ws_url,
    lang: session.lang,
    consent: session.consent,
  });
}

function createSessionStore({ apiUrl, fetchImpl, timeoutMs, socketFactory = null }) {
  const config = resolveApiBaseUrl(apiUrl);
  const listeners = new Set();

  let credential = null;
  let caseAccessRevoked = false;
  let epoch = 0;
  let creationTicket = 0;
  let timelineTicket = 0;
  let timelineAbort = null;
  let conversation = null;
  let snapshot = Object.freeze({
    configured: config.ok,
    session: null,
    creation: Object.freeze({ status: "idle", consent: null, lang: null, attempt: 0 }),
    timeline: IDLE_TIMELINE,
    conversation: IDLE_CONVERSATION,
  });

  function update(patch) {
    snapshot = Object.freeze({ ...snapshot, ...patch });
    for (const listener of [...listeners]) {
      try {
        listener();
      } catch {
        // A failing subscriber must not leave the session half-updated or
        // turn a background request into an unhandled rejection.
      }
    }
  }

  function setTimeline(status, payload = null) {
    update({ timeline: Object.freeze({ status, payload }) });
  }

  function abortTimeline() {
    timelineTicket += 1;
    if (timelineAbort !== null) {
      timelineAbort.abort();
      timelineAbort = null;
    }
  }

  function closeConversation() {
    if (conversation !== null) conversation.close();
    conversation = null;
  }

  /** Opens the one socket for the current session. Idempotent. */
  function ensureConversation() {
    const session = snapshot.session;
    if (conversation !== null || session === null || credential === null) return conversation;
    if (!config.ok || socketFactory === null) return null;
    const sessionEpoch = epoch;
    conversation = createConversation({
      baseUrl: config.baseUrl,
      sessionId: session.session_id,
      token: credential,
      lang: session.lang,
      socketFactory,
      onChange: (state) => {
        if (sessionEpoch === epoch) update({ conversation: state });
      },
    });
    conversation.connect();
    return conversation;
  }

  /** Resolves true once the socket is open, false if it closes or the wait runs out. */
  function whenOpen() {
    return new Promise((resolve) => {
      if (snapshot.conversation.status === "open") {
        resolve(true);
        return;
      }
      let unsubscribe = () => {};
      const timer = setTimeout(() => {
        unsubscribe();
        resolve(false);
      }, OPEN_WAIT_MS);
      const listener = () => {
        const { status } = snapshot.conversation;
        if (status !== "open" && status !== "closed") return;
        clearTimeout(timer);
        unsubscribe();
        resolve(status === "open");
      };
      listeners.add(listener);
      unsubscribe = () => listeners.delete(listener);
    });
  }

  function dropSession(timelineStatus) {
    closeConversation();
    abortTimeline();
    epoch += 1;
    creationTicket += 1;
    credential = null;
    caseAccessRevoked = false;
    update({
      session: null,
      creation: Object.freeze({ status: "idle", consent: null, lang: null, attempt: 0 }),
      timeline: Object.freeze({ status: timelineStatus, payload: null }),
      conversation: IDLE_CONVERSATION,
    });
  }

  async function attemptCreation(consent, lang, attempt) {
    const ticket = ++creationTicket;
    update({ creation: Object.freeze({ status: "creating", consent, lang, attempt }) });

    const result = config.ok
      ? await createSession({ fetchImpl, baseUrl: config.baseUrl, consent, lang, timeoutMs })
        .catch(() => ({ ok: false, reason: "network" }))
      : { ok: false, reason: "config" };

    if (ticket !== creationTicket) return { ok: false, reason: "stale" };

    if (!result.ok) {
      update({ creation: Object.freeze({ status: "failed", consent, lang, attempt }) });
      return { ok: false, reason: result.reason };
    }

    epoch += 1;
    credential = result.session.session_token;
    caseAccessRevoked = false;
    const session = publicSession(result.session);
    update({
      session,
      creation: Object.freeze({ status: "succeeded", consent, lang, attempt }),
      timeline: IDLE_TIMELINE,
    });
    return { ok: true, session };
  }

  const api = {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    getSnapshot() {
      return snapshot;
    },

    /** The single consent decision. Never retried automatically. */
    startSession(consent, lang) {
      if (consent !== "granted" && consent !== "declined") {
        return Promise.resolve({ ok: false, reason: "invalid" });
      }
      if (lang !== "hi" && lang !== "en") return Promise.resolve({ ok: false, reason: "invalid" });
      if (snapshot.session !== null) return Promise.resolve({ ok: false, reason: "active" });
      if (snapshot.creation.status === "creating") {
        return Promise.resolve({ ok: false, reason: "in_flight" });
      }
      if (snapshot.creation.status !== "idle") {
        return Promise.resolve({ ok: false, reason: "decided" });
      }
      return attemptCreation(consent, lang, 1);
    },

    /** Explicit, user-triggered retry of the same decision after a failure. */
    retrySessionCreation() {
      const { status, consent, lang, attempt } = snapshot.creation;
      if (status === "creating") return Promise.resolve({ ok: false, reason: "in_flight" });
      if (status !== "failed" || consent === null || lang === null) {
        return Promise.resolve({ ok: false, reason: "not_failed" });
      }
      return attemptCreation(consent, lang, attempt + 1);
    },

    clearSession() {
      dropSession("idle");
    },

    /** Opens the conversation socket for the current session. */
    connectConversation() {
      ensureConversation();
    },

    /**
     * One text turn. Rejects with no session or no connection. A declined
     * session may still write: the server keeps the words for a person and
     * runs no AI analysis on them.
     */
    async sendChat(text) {
      if (snapshot.session === null) throw new Error("unavailable");
      const live = ensureConversation();
      if (live === null || !(await whenOpen())) throw new Error("offline");
      await live.sendChat(text);
    },

    /**
     * "Talk to a person", from any screen. With no session yet, asking for a
     * person is taken as declining the AI: a declined session is created, so
     * no AI analysis runs and the case routes straight to a human.
     */
    async requestHuman(lang) {
      if (snapshot.session === null) {
        const started = snapshot.creation.status === "idle"
          ? await api.startSession("declined", lang === "en" ? "en" : "hi")
          : snapshot.creation.status === "failed"
            ? await api.retrySessionCreation()
            : { ok: false };
        if (!started.ok) throw new Error("unavailable");
      }
      const live = ensureConversation();
      if (live === null || !(await whenOpen())) throw new Error("offline");
      await live.requestHuman();
    },

    /** Loads the current session's one case. Takes no case identifier. */
    async loadTimeline() {
      const session = snapshot.session;
      if (session === null || credential === null || caseAccessRevoked) {
        abortTimeline();
        setTimeline("unavailable");
        return;
      }
      if (!config.ok) {
        setTimeline("failed");
        return;
      }

      abortTimeline();
      const ticket = timelineTicket;
      const sessionEpoch = epoch;
      const controller = new AbortController();
      timelineAbort = controller;
      setTimeline("loading");

      const result = await fetchTimeline({
        fetchImpl,
        baseUrl: config.baseUrl,
        caseId: session.case_id,
        sessionToken: credential,
        signal: controller.signal,
        timeoutMs,
      }).catch(() => ({ kind: "failed", reason: "network" }));

      if (ticket !== timelineTicket || sessionEpoch !== epoch) return;
      timelineAbort = null;

      switch (result.kind) {
        case "ready":
          setTimeline("ready", result.timeline);
          return;
        case "unauthenticated":
          dropSession("unavailable");
          return;
        case "forbidden":
          caseAccessRevoked = true;
          setTimeline("unavailable");
          return;
        case "not_found":
          setTimeline("unavailable");
          return;
        case "aborted":
          setTimeline("idle");
          return;
        default:
          setTimeline("failed");
      }
    },

    cancelTimeline() {
      abortTimeline();
      if (snapshot.timeline.status === "loading") setTimeline("idle");
    },
  };
  return api;
}

/** Maps the stored timeline onto the existing MyRequests presentation states. */
function timelineLoadState(timeline) {
  switch (timeline.status) {
    case "ready":
      return "ready";
    case "failed":
      return "failed";
    case "unavailable":
      return "unavailable";
    default:
      return "loading";
  }
}

module.exports = { createSessionStore, timelineLoadState };
