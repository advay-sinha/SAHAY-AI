import { getLanguage } from "../i18n";
import { validateVictimTimeline, type VictimTimeline } from "./victimPayload";
import {
  ApiError,
  createSession as postSession,
  getTimeline as fetchTimeline,
  validateApiBaseUrl,
  type ActiveSession,
  type Consent,
} from "./apiCore";

const API_BASE_URL = validateApiBaseUrl(process.env.EXPO_PUBLIC_API_URL, __DEV__);
const SOCKET_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

export { ApiError, type ActiveSession, type Consent };

export function createSession(consent: Consent): Promise<ActiveSession> {
  return postSession(API_BASE_URL, { channel: "mobile_chat", consent, lang: getLanguage() });
}

export function getActiveTimeline(session: ActiveSession): Promise<VictimTimeline> {
  return fetchTimeline(API_BASE_URL, session, validateVictimTimeline);
}

export function getSocketBaseUrl(): string {
  return SOCKET_BASE_URL;
}
