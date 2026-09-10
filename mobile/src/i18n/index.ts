/**
 * Every user-visible string goes through here. No hardcoded English anywhere
 * in the app: a distressed user may not read English at all.
 */

import en from "./en.json";
import hi from "./hi.json";

export type Lang = "hi" | "en";

const BUNDLES: Record<Lang, Record<string, string>> = { hi, en };

let current: Lang = "hi";

export function setLanguage(lang: Lang): void {
  current = lang;
}

export function getLanguage(): Lang {
  return current;
}

export function t(key: string): string {
  // Falls back to the other language rather than showing a raw key to a user.
  return BUNDLES[current][key] ?? BUNDLES[current === "hi" ? "en" : "hi"][key] ?? key;
}

export function missingKeys(): string[] {
  const hiKeys = new Set(Object.keys(hi));
  const enKeys = new Set(Object.keys(en));
  const missing: string[] = [];
  for (const key of hiKeys) if (!enKeys.has(key)) missing.push(`en:${key}`);
  for (const key of enKeys) if (!hiKeys.has(key)) missing.push(`hi:${key}`);
  return missing;
}
