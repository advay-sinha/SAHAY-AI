/**
 * Barge-in: the user's speech stops playback immediately and becomes the next
 * turn. Verified by hand, with a real voice, not only in a simulator.
 */

import type { PlaybackQueue } from "./playback";

export function attachBargeIn(playback: PlaybackQueue, onUserSpeech: () => void) {
  return {
    handleLocalSpeechDetected() {
      if (playback.isPlaying()) playback.stop();
      onUserSpeech();
    },
  };
}
