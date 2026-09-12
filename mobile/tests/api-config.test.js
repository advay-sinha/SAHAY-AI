/** EXPO_PUBLIC_API_URL handling. Runs with Node and no installed dependency. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { configuredApiUrl, resolveApiBaseUrl } = require("../src/net/apiConfig");

const MOBILE = path.join(__dirname, "..");

function productionFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...productionFiles(full));
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) found.push(full);
  }
  return found;
}

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/.*$/gm, "$1 ");
}

test("a valid configured URL is accepted and normalized", () => {
  assert.deepEqual(resolveApiBaseUrl("http://192.168.1.20:8000"), {
    ok: true,
    baseUrl: "http://192.168.1.20:8000",
  });
  assert.deepEqual(resolveApiBaseUrl("  HTTPS://Api.Example.test/sahay/  "), {
    ok: true,
    baseUrl: "https://api.example.test/sahay",
  });
  assert.deepEqual(resolveApiBaseUrl("http://127.0.0.1:18000/"), {
    ok: true,
    baseUrl: "http://127.0.0.1:18000",
  });
  assert.deepEqual(resolveApiBaseUrl("http://[::1]:8000"), { ok: true, baseUrl: "http://[::1]:8000" });
});

test("missing configuration is refused without a fallback", () => {
  for (const value of [undefined, null, "", "   ", 8000, {}]) {
    assert.deepEqual(resolveApiBaseUrl(value), { ok: false, error: "missing" });
  }
});

test("malformed or unsupported URLs are refused", () => {
  for (const value of [
    "localhost:8000",
    "ftp://example.test",
    "ws://example.test",
    "http://",
    "http://user:pass@example.test",
    "http://example.test?token=abc",
    "http://example.test/#frag",
    "http://example.test:0",
    "http://example.test:65536",
    "http://exa mple.test",
    "http://example.test/a/../b",
    "http://example.test//double",
    "http://-bad.test",
    "http://example.test/%2e%2e",
    "javascript:alert(1)",
  ]) {
    assert.equal(resolveApiBaseUrl(value).ok, false, value);
  }
});

test("a refused value is never echoed back", () => {
  const secretish = "http://fixture-user:fixture-pass@example.test/?token=abc";
  const result = resolveApiBaseUrl(secretish);
  assert.equal(result.ok, false);
  assert.doesNotMatch(JSON.stringify(result), /fixture-pass|fixture-user|token|example/);
});

test("the configured URL is read only from EXPO_PUBLIC_API_URL", () => {
  const previous = process.env.EXPO_PUBLIC_API_URL;
  try {
    delete process.env.EXPO_PUBLIC_API_URL;
    assert.equal(configuredApiUrl(), undefined);
    process.env.EXPO_PUBLIC_API_URL = "http://10.0.0.5:8000";
    assert.equal(configuredApiUrl(), "http://10.0.0.5:8000");
  } finally {
    if (previous === undefined) delete process.env.EXPO_PUBLIC_API_URL;
    else process.env.EXPO_PUBLIC_API_URL = previous;
  }

  const source = fs.readFileSync(path.join(MOBILE, "src", "net", "apiConfig.js"), "utf8");
  assert.match(source, /process\.env\.EXPO_PUBLIC_API_URL/);
});

test("production source hard-codes no backend URL, host or forwarded port", () => {
  const offences = [];
  for (const root of ["app", "src"]) {
    for (const file of productionFiles(path.join(MOBILE, root))) {
      const code = stripComments(fs.readFileSync(file, "utf8"));
      for (const pattern of [
        /["'`]https?:\/\/[^"'`]+["'`]/,
        /localhost/i,
        /127\.0\.0\.1/,
        /10\.0\.2\.2/,
        /\b18000\b/,
        /\b8000\b/,
      ]) {
        if (pattern.test(code)) offences.push(`${path.relative(MOBILE, file)}: ${pattern}`);
      }
    }
  }
  assert.deepEqual(offences, []);
});

test("app.json declares no API URL and no extra network configuration", () => {
  const appJson = fs.readFileSync(path.join(MOBILE, "app.json"), "utf8");
  assert.doesNotMatch(appJson, /https?:\/\/|localhost|EXPO_PUBLIC_API_URL|apiUrl/i);
});
