/**
 * Microphone capture: Web Audio → 16 kHz mono int16 PCM chunks.
 *
 * An AudioWorklet (inlined as a Blob module — no extra asset to serve)
 * downsamples from the hardware rate and posts ~250 ms chunks. The caller
 * ships each chunk over the live WebSocket.
 */

const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions.targetRate;
    this.chunkSize = options.processorOptions.chunkSize;
    this.ratio = sampleRate / this.targetRate;
    this.readPos = 0;
    this.input = [];
    this.output = new Int16Array(this.chunkSize);
    this.outPos = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) this.input.push(channel[i]);

    // linear-interpolation resample of everything currently buffered
    while (this.readPos + this.ratio < this.input.length) {
      const pos = this.readPos;
      const idx = Math.floor(pos);
      const frac = pos - idx;
      const sample = this.input[idx] * (1 - frac) + this.input[idx + 1] * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      this.output[this.outPos++] = Math.round(clamped * 32767);
      this.readPos += this.ratio;
      if (this.outPos === this.chunkSize) {
        this.port.postMessage(this.output.buffer.slice(0));
        this.outPos = 0;
      }
    }
    const consumed = Math.floor(this.readPos);
    this.input = this.input.slice(consumed);
    this.readPos -= consumed;
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

export interface Recorder {
  stop: () => Promise<void>;
}

/** Translate getUserMedia failures into actionable German messages —
 * "nothing happened" silent failures are not acceptable UX. */
export function describeMicError(error: unknown): string {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return (
      "Mikrofonzugriff ist hier nicht verfügbar — die Seite muss über HTTPS " +
      "oder localhost/127.0.0.1 geöffnet sein."
    );
  }
  const name = error instanceof DOMException ? error.name : "";
  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return (
        "Mikrofonzugriff wurde blockiert. Bitte über das Berechtigungs-/" +
        "Schloss-Symbol in der Adressleiste erlauben und unter Windows " +
        "Einstellungen → Datenschutz → Mikrofon prüfen."
      );
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "Kein Mikrofon gefunden. Bitte ein Mikrofon anschließen oder aktivieren.";
    case "NotReadableError":
    case "TrackStartError":
      return "Das Mikrofon wird gerade von einer anderen Anwendung verwendet.";
    case "AbortError":
      return (
        "Das Mikrofon konnte nicht gestartet werden. Bitte die Seite neu " +
        "laden (F5) und erneut versuchen — besonders nach geänderten " +
        "Website-Berechtigungen. Hilft das nicht: anderes Programm schließen, " +
        "das das Mikrofon belegt, oder unter Windows Einstellungen → " +
        "Datenschutz → Mikrofon den Zugriff für Desktop-Apps erlauben."
      );
    case "SecurityError":
      return "Der Browser verbietet Mikrofonzugriff in diesem Kontext (HTTPS erforderlich).";
    default:
      return `Mikrofonzugriff nicht möglich${name ? ` (${name})` : ""}.`;
  }
}

/** Browser DSP (noise suppression, auto-gain, echo cancellation) is tuned
 * for phone calls, not transcription — it can smear consonants (e.g. the
 * "s" in "Ausrufezeichen") and hurt STT accuracy. Off by default so the
 * model receives clean, unprocessed audio; the recorder passes this through
 * from a per-session setting. */
export interface RecorderOptions {
  audioProcessing?: boolean;
}

export async function startRecorder(
  onChunk: (chunk: ArrayBuffer) => void,
  options: RecorderOptions = {},
): Promise<Recorder> {
  const dsp = options.audioProcessing ?? false;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: dsp,
      noiseSuppression: dsp,
      autoGainControl: dsp,
    },
  });

  // From here on the mic is ACQUIRED: any setup failure must release it,
  // otherwise the browser keeps "using the microphone" indefinitely and
  // blocks every other app until the tab is closed.
  let audioContext: AudioContext | null = null;
  try {
    audioContext = new AudioContext();
    const workletUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: "application/javascript" }),
    );
    try {
      await audioContext.audioWorklet.addModule(workletUrl);
    } finally {
      URL.revokeObjectURL(workletUrl);
    }

    const source = audioContext.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(audioContext, "pcm-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      processorOptions: { targetRate: 16000, chunkSize: 4096 },
    });
    node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => onChunk(event.data);
    source.connect(node);

    return {
      async stop() {
        node.port.onmessage = null;
        source.disconnect();
        node.disconnect();
        for (const track of stream.getTracks()) track.stop();
        await audioContext!.close();
      },
    };
  } catch (setupError) {
    for (const track of stream.getTracks()) track.stop();
    await audioContext?.close().catch(() => undefined);
    throw setupError;
  }
}
