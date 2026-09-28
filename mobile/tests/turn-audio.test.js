const test = require("node:test");
const assert = require("node:assert/strict");

const { buildTurnAudioSource } = require("../src/net/restClient");

const BASE = { baseUrl: "http://192.168.1.20:8000", sessionId: "s-1", turnId: "t-9", sessionToken: "tok.en-1" };

test("PC-12 source points at the turn audio route with the token in the header only", () => {
  const source = buildTurnAudioSource(BASE);
  assert.equal(source.uri, "http://192.168.1.20:8000/sessions/s-1/turns/t-9/audio");
  assert.deepEqual(source.headers, { Accept: "audio/wav", Authorization: "Bearer tok.en-1" });
  assert.ok(!source.uri.includes("tok.en-1"));
});

test("malformed input builds nothing", () => {
  for (const bad of [
    { ...BASE, turnId: "../cases" },
    { ...BASE, sessionId: "" },
    { ...BASE, sessionToken: "has space" },
    { ...BASE, baseUrl: "" },
    { ...BASE, turnId: undefined },
  ]) {
    assert.equal(buildTurnAudioSource(bad), null);
  }
});
