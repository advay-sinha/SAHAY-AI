/**
 * Clearly fictional, in-memory fixtures for tests only. Nothing here is
 * imported by production code, and none of it is a real session or person.
 */

const TOKEN = "fixture-header.fixture-claims.fixture-signature-NEVER-LOG";
const BASE_URL = "http://backend.fixture.test:8000";

function sessionResponse(overrides = {}) {
  return {
    session_id: "fixture-session-0001",
    case_id: "fixture-case-0001",
    reference_no: "SAH-FIXTURE",
    session_token: TOKEN,
    ws_url: "/ws/session/fixture-session-0001",
    lang: "hi",
    consent: "granted",
    ai_disclosure: "Fixture disclosure text",
    human_request_available: true,
    ...overrides,
  };
}

function timelineResponse(entries = []) {
  return { reference: "SAH-FIXTURE", timeline: entries };
}

function jsonResponse(status, body) {
  return {
    status,
    async text() {
      return typeof body === "string" ? body : JSON.stringify(body);
    },
  };
}

/**
 * A recording fetch. Each call takes the next scripted reply: an object from
 * jsonResponse, an Error to throw, "hang" to never settle, or a function
 * returning a promise for fine-grained control.
 */
function scriptedFetch(replies) {
  const calls = [];
  const queue = [...replies];
  async function fetchImpl(url, init) {
    calls.push({ url, init });
    const reply = queue.shift();
    if (reply === undefined) throw new Error("unexpected request");
    if (reply === "hang") return new Promise(() => {});
    if (reply instanceof Error) throw reply;
    if (typeof reply === "function") return reply(url, init);
    return reply;
  }
  return { calls, fetchImpl };
}

/** Collects every console call so a test can assert the token never appears. */
function captureConsole() {
  const methods = ["log", "info", "warn", "error", "debug", "trace"];
  const original = {};
  const lines = [];
  for (const method of methods) {
    original[method] = console[method];
    console[method] = (...args) => {
      lines.push(args.map((arg) => {
        try {
          return typeof arg === "string" ? arg : JSON.stringify(arg);
        } catch {
          return String(arg);
        }
      }).join(" "));
    };
  }
  return {
    lines,
    restore() {
      for (const method of methods) console[method] = original[method];
    },
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

module.exports = {
  BASE_URL,
  TOKEN,
  captureConsole,
  deferred,
  jsonResponse,
  scriptedFetch,
  sessionResponse,
  timelineResponse,
};
