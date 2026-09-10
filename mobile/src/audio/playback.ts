/** TTS playback queue. Chunks arrive on the socket as binary frames. */

export interface PlaybackQueue {
  enqueue: (chunk: ArrayBuffer) => void;
  /** Stops immediately. Barge-in must feel instant. */
  stop: () => void;
  isPlaying: () => boolean;
}

export function createPlaybackQueue(): PlaybackQueue {
  throw new Error("playback lands in P1");
}
