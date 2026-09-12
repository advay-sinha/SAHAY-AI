import { describe, expect, it, vi } from "vitest";

import { probeBackendHealth } from "./BackendStatusBadge";

describe("backend status badge", () => {
  it("reports Operational only after a successful ok health response", async () => {
    const health = vi.fn(async () => ({ status: "ok" })) as never;
    await expect(probeBackendHealth(health)).resolves.toBe("operational");
  });

  it("never reports Operational when health is unreachable or non-ok", async () => {
    const unreachable = vi.fn(async () => {
      throw new TypeError("network unavailable");
    }) as never;
    const nonOk = vi.fn(async () => ({ status: "degraded" })) as never;

    await expect(probeBackendHealth(unreachable)).resolves.toBe("unreachable");
    await expect(probeBackendHealth(nonOk)).resolves.toBe("unreachable");
  });
});
