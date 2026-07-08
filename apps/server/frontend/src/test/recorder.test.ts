/**
 * The recorder must request the microphone with browser DSP (noise
 * suppression / auto-gain / echo cancellation) OFF by default — those
 * degrade STT accuracy — and only enable it when explicitly asked.
 */

import { startRecorder } from "../audio/recorder";

function stubGetUserMedia() {
  const calls: MediaTrackConstraints[] = [];
  Object.defineProperty(navigator, "mediaDevices", {
    value: {
      getUserMedia: (c: MediaStreamConstraints) => {
        calls.push(c.audio as MediaTrackConstraints);
        // fail right after acquisition so we don't need real Web Audio
        return Promise.reject(new DOMException("stop here", "NotReadableError"));
      },
    },
    configurable: true,
  });
  return calls;
}

describe("startRecorder audio constraints", () => {
  it("disables noise suppression / auto-gain / echo cancellation by default", async () => {
    const calls = stubGetUserMedia();
    await startRecorder(() => undefined).catch(() => undefined);
    expect(calls[0]).toMatchObject({
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    });
  });

  it("enables DSP only when audioProcessing is requested", async () => {
    const calls = stubGetUserMedia();
    await startRecorder(() => undefined, { audioProcessing: true }).catch(() => undefined);
    expect(calls[0]).toMatchObject({
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    });
  });
});
