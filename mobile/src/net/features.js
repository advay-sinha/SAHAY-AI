/**
 * Build-time feature switches from EXPO_PUBLIC_* variables.
 *
 * EXPO_PUBLIC_VOICE=off hides every voice entry point. Hosted tester builds
 * (EXT-130) set it because the cloud backend runs ASR_PROVIDER=mock and would
 * otherwise answer real speech with canned transcripts. Voice stays on by
 * default so the laptop and APK demo builds are unchanged.
 */

function resolveVoiceEnabled(raw) {
  if (typeof raw !== "string") return true;
  return raw.trim().toLowerCase() !== "off";
}

function voiceEnabled() {
  // Direct member access so Expo inlines the public variable at build time.
  return resolveVoiceEnabled(process.env.EXPO_PUBLIC_VOICE);
}

/**
 * EXPO_PUBLIC_TESTER_BUILD=on shows a fictional-stories-only notice under the
 * AI disclosure on every screen (root CLAUDE.md invariant 8). Off by default.
 */
function resolveTesterBuild(raw) {
  return typeof raw === "string" && raw.trim().toLowerCase() === "on";
}

function testerBuild() {
  return resolveTesterBuild(process.env.EXPO_PUBLIC_TESTER_BUILD);
}

module.exports = { resolveTesterBuild, resolveVoiceEnabled, testerBuild, voiceEnabled };
