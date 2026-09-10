/**
 * Microphone capture: 16 kHz mono PCM16, 500 ms frames (CONTRACTS.md section 1).
 *
 * expo-audio provides the recording surface (EXT-001, installed 2026-09-10). Native audio
 * modules are a known time sink; mobile/CLAUDE.md flags this as the highest
 * uncertainty task in the project.
 */

export const SAMPLE_RATE = 16000;
export const CHANNELS = 1;
export const FRAME_MS = 500;

export interface CaptureHandle {
  stop: () => Promise<void>;
}

export interface CaptureOptions {
  onFrame: (pcm16: ArrayBuffer, seq: number, ms: number) => void;
  onError: (error: Error) => void;
}

/** Implemented in P1 against expo-audio. Never impose a time limit on a turn. */
export async function startCapture(_options: CaptureOptions): Promise<CaptureHandle> {
  throw new Error("capture lands in P1");
}
