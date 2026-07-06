/**
 * Short audio cues ("earcons") for recording state — perceivable even when
 * the screen-reader user is focused elsewhere in the DOM. Explicitly allowed
 * by the brief; everything else must not auto-play audio.
 */

export type Earcon = "start" | "stop" | "complete" | "error";

let context: AudioContext | null = null;

function ctx(): AudioContext {
  if (!context) context = new AudioContext();
  return context;
}

function tone(frequency: number, startAt: number, duration: number): void {
  const audio = ctx();
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.type = "sine";
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, audio.currentTime + startAt);
  gain.gain.exponentialRampToValueAtTime(0.18, audio.currentTime + startAt + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + startAt + duration);
  oscillator.connect(gain).connect(audio.destination);
  oscillator.start(audio.currentTime + startAt);
  oscillator.stop(audio.currentTime + startAt + duration + 0.05);
}

const PATTERNS: Record<Earcon, Array<[number, number, number]>> = {
  start: [
    [523, 0, 0.12],
    [784, 0.13, 0.15],
  ],
  stop: [
    [784, 0, 0.12],
    [523, 0.13, 0.15],
  ],
  complete: [
    [660, 0, 0.1],
    [660, 0.12, 0.1],
    [880, 0.24, 0.2],
  ],
  error: [
    [220, 0, 0.25],
    [196, 0.27, 0.3],
  ],
};

export function playEarcon(name: Earcon, enabled: boolean): void {
  if (!enabled) return;
  try {
    for (const [frequency, at, duration] of PATTERNS[name]) {
      tone(frequency, at, duration);
    }
  } catch {
    // no audio output available — announcements still cover the state change
  }
}
