export type ApiConfigResult =
  | { ok: true; baseUrl: string }
  | { ok: false; error: "missing" | "invalid" };

export function resolveApiBaseUrl(raw: unknown): ApiConfigResult;
export function configuredApiUrl(): string | undefined;
