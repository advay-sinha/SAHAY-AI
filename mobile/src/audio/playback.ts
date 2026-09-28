/**
 * Assistant-turn audio (PC-12). Whole files are fetched by turn id with the session token in a
 * header; nothing streams on the socket. When the server has no approved audio (404) or playback
 * fails for any reason, nothing is shown to the person: the text is already on screen.
 */

import { createAudioPlayer, type AudioPlayer } from "expo-audio";
import type { TurnAudioSource } from "../net/restClient";

export interface PlaybackQueue {
  /** Plays one assistant turn, replacing whatever is playing. `null` does nothing. */
  play: (source: TurnAudioSource | null) => void;
  /** Stops immediately. Barge-in must feel instant. */
  stop: () => void;
  isPlaying: () => boolean;
}

export function createPlaybackQueue(): PlaybackQueue {
  let player: AudioPlayer | null = null;

  function stop(): void {
    const current = player;
    player = null;
    if (current === null) return;
    try {
      current.pause();
      current.remove();
    } catch {
      // Releasing a player that failed to load is harmless; the text is already shown.
    }
  }

  function play(source: TurnAudioSource | null): void {
    stop();
    if (source === null) return;
    try {
      const next = createAudioPlayer({ uri: source.uri, headers: source.headers });
      player = next;
      next.play();
    } catch {
      stop();
    }
  }

  function isPlaying(): boolean {
    try {
      return player?.playing === true;
    } catch {
      return false;
    }
  }

  return { play, stop, isPlaying };
}
