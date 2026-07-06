import { useCallback, useEffect, useRef, useState } from "react";

import { TranscriptBatcher, useAnnouncer } from "../announcer";
import { playEarcon } from "../audio/earcons";
import { startRecorder, type Recorder } from "../audio/recorder";
import type { LiveServerMessage } from "../types";

type RecordingState = "idle" | "connecting" | "recording" | "stopping";

interface FinalSegment {
  id: number;
  text: string;
}

export function RecordView() {
  const { announce, liveTranscriptMuted, earconsEnabled } = useAnnouncer();
  const [state, setState] = useState<RecordingState>("idle");
  const [finals, setFinals] = useState<FinalSegment[]>([]);
  const [partial, setPartial] = useState("");
  const [saveRecording, setSaveRecording] = useState(true);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [statusLine, setStatusLine] = useState("Bereit für Aufnahme.");

  const socketRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const batcherRef = useRef<TranscriptBatcher | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const cleanup = useCallback(async () => {
    batcherRef.current?.dispose();
    batcherRef.current = null;
    if (recorderRef.current) {
      await recorderRef.current.stop().catch(() => undefined);
      recorderRef.current = null;
    }
    if (socketRef.current && socketRef.current.readyState <= WebSocket.OPEN) {
      socketRef.current.close();
    }
    socketRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      void cleanup();
    };
  }, [cleanup]);

  const handleServerMessage = useCallback(
    (message: LiveServerMessage) => {
      switch (message.type) {
        case "ready":
          break;
        case "partial":
          setPartial(message.text);
          break;
        case "final":
          setFinals((current) => [
            ...current,
            { id: message.segment.id, text: message.segment.text },
          ]);
          setPartial("");
          if (!liveTranscriptMuted) {
            batcherRef.current?.add(message.segment.text);
          }
          break;
        case "stopped":
          batcherRef.current?.flush();
          setState("idle");
          setStatusLine(
            message.job_id
              ? "Aufnahme beendet. Vollständige Transkription läuft – siehe Verlauf."
              : "Aufnahme beendet.",
          );
          announce(
            message.job_id
              ? "Aufnahme beendet. Vollständige Transkription läuft, Ergebnis im Verlauf."
              : "Aufnahme beendet.",
            "assertive",
          );
          playEarcon("complete", earconsEnabled);
          break;
        case "error":
          setStatusLine(`Fehler: ${message.message}`);
          announce(`Fehler: ${message.message}`, "assertive");
          playEarcon("error", earconsEnabled);
          break;
      }
    },
    [announce, earconsEnabled, liveTranscriptMuted],
  );

  async function startRecording() {
    setState("connecting");
    setFinals([]);
    setPartial("");
    setStatusLine("Verbindung wird aufgebaut …");
    batcherRef.current = new TranscriptBatcher((text) => announce(text, "polite"));
    try {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocol}://${window.location.host}/ws/live`);
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;

      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve();
        socket.onerror = () => reject(new Error("Verbindung zum Server fehlgeschlagen"));
      });

      socket.onmessage = (event) => {
        try {
          handleServerMessage(JSON.parse(event.data) as LiveServerMessage);
        } catch {
          /* non-JSON frame: ignore */
        }
      };
      socket.onclose = () => {
        if (stateRef.current === "recording") {
          setState("idle");
          setStatusLine("Verbindung unterbrochen.");
          announce("Fehler: Verbindung zum Server unterbrochen", "assertive");
          playEarcon("error", earconsEnabled);
          void cleanup();
        }
      };

      socket.send(
        JSON.stringify({
          type: "start",
          options: initialPrompt.trim() ? { initial_prompt: initialPrompt.trim() } : {},
        }),
      );

      recorderRef.current = await startRecorder((chunk) => {
        if (socket.readyState === WebSocket.OPEN) socket.send(chunk);
      });

      setState("recording");
      setStatusLine("Aufnahme läuft.");
      announce("Aufnahme gestartet", "assertive");
      playEarcon("start", earconsEnabled);
      // voice-control mode listens for this and releases the microphone
      window.dispatchEvent(new Event("stt:recording-started"));
    } catch (startError) {
      const message =
        startError instanceof Error
          ? startError.message
          : "Mikrofonzugriff nicht möglich";
      setState("idle");
      setStatusLine(`Fehler: ${message}`);
      announce(`Fehler: ${message}`, "assertive");
      playEarcon("error", earconsEnabled);
      await cleanup();
    }
  }

  async function stopRecording() {
    setState("stopping");
    setStatusLine("Aufnahme wird beendet …");
    announce("Aufnahme beendet", "assertive");
    playEarcon("stop", earconsEnabled);
    if (recorderRef.current) {
      await recorderRef.current.stop().catch(() => undefined);
      recorderRef.current = null;
    }
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "stop", save: saveRecording }));
    } else {
      setState("idle");
    }
  }

  // global shortcut: Ctrl+Alt+R toggles recording
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!event.ctrlKey || !event.altKey || event.shiftKey || event.metaKey) return;
      if (event.key.toLowerCase() !== "r") return;
      event.preventDefault();
      if (stateRef.current === "idle") void startRecording();
      else if (stateRef.current === "recording") void stopRecording();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveRecording, initialPrompt, liveTranscriptMuted, earconsEnabled]);

  const busy = state === "connecting" || state === "stopping";

  return (
    <div>
      {/* visible status text; screen-reader announcements go through the
          central assertive live region to avoid double-speaking */}
      <p id="record-status">{statusLine}</p>

      <div className="stack">
        <label>
          <input
            type="checkbox"
            checked={saveRecording}
            disabled={state !== "idle"}
            onChange={(event) => setSaveRecording(event.target.checked)}
          />{" "}
          Nach dem Stoppen in voller Qualität transkribieren und im Verlauf speichern
        </label>

        <div>
          <label htmlFor="record-prompt">
            Fachvokabular / Kontext <span className="hint">(optional)</span>
          </label>
          <input
            id="record-prompt"
            type="text"
            value={initialPrompt}
            disabled={state !== "idle"}
            onChange={(event) => setInitialPrompt(event.target.value)}
          />
        </div>

        {state !== "recording" ? (
          <button
            type="button"
            className="action"
            disabled={busy}
            onClick={() => void startRecording()}
          >
            Aufnahme starten
          </button>
        ) : (
          <button type="button" className="action danger" onClick={() => void stopRecording()}>
            Aufnahme stoppen
          </button>
        )}
      </div>

      <h3 id="live-transcript-heading">Live-Transkript</h3>
      <div
        className="transcript-area"
        aria-labelledby="live-transcript-heading"
        role="region"
      >
        {finals.length === 0 && !partial && <p className="hint">Noch kein Text erkannt.</p>}
        {finals.map((segment) => (
          <p key={segment.id}>{segment.text}</p>
        ))}
        {partial && (
          <p className="partial-text" aria-hidden="true">
            {partial}
          </p>
        )}
      </div>
      <p className="hint">
        Erkannte Sätze werden automatisch vorgelesen (gebündelt, nicht Wort für Wort). Diese
        Ansagen lassen sich unter „Einstellungen zur Vorlesefunktion“ stummschalten.
      </p>
    </div>
  );
}
