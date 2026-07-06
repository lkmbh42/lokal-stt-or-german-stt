/**
 * Voice-command mode: reuses the live-transcription WebSocket + engine to
 * recognize a fixed German command grammar (see commands.ts) and drive the
 * UI. A genuine differentiator for blind users — navigation without
 * keyboard or sight.
 *
 * The mode auto-stops when an audio recording starts (RecordView dispatches
 * `stt:recording-started`): one microphone owner at a time.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useAnnouncer } from "../announcer";
import { startRecorder, type Recorder } from "../audio/recorder";
import type { LiveServerMessage } from "../types";
import { matchCommand, type VoiceAction } from "./commands";

export function VoiceControl({
  onAction,
}: {
  onAction: (action: Exclude<VoiceAction, "stop-voice-control">) => void;
}) {
  const { announce } = useAnnouncer();
  const [active, setActive] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  const stop = useCallback(
    async (announceStop: boolean) => {
      setActive(false);
      if (recorderRef.current) {
        await recorderRef.current.stop().catch(() => undefined);
        recorderRef.current = null;
      }
      if (socketRef.current && socketRef.current.readyState <= WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: "stop", save: false }));
        socketRef.current.close();
      }
      socketRef.current = null;
      if (announceStop) announce("Sprachsteuerung beendet.", "assertive");
    },
    [announce],
  );

  const handleUtterance = useCallback(
    (text: string) => {
      const action = matchCommand(text);
      if (action === null) return; // closed grammar: ignore free speech
      if (action === "stop-voice-control") {
        void stop(true);
        return;
      }
      announce(`Befehl erkannt: ${text.trim()}`, "assertive");
      onActionRef.current(action);
    },
    [announce, stop],
  );

  async function start() {
    try {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocol}://${window.location.host}/ws/live`);
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve();
        socket.onerror = () => reject(new Error("Verbindung fehlgeschlagen"));
      });
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as LiveServerMessage;
          if (message.type === "final") handleUtterance(message.segment.text);
          if (message.type === "error") void stop(false);
        } catch {
          /* ignore non-JSON frames */
        }
      };
      socket.send(JSON.stringify({ type: "start", options: {} }));
      recorderRef.current = await startRecorder((chunk) => {
        if (socket.readyState === WebSocket.OPEN) socket.send(chunk);
      });
      setActive(true);
      announce(
        "Sprachsteuerung aktiv. Sagen Sie zum Beispiel „Bereich Verlauf“ oder " +
          "„Sprachsteuerung beenden“. Alle Befehle stehen im Tastenkürzel-Dialog.",
        "assertive",
      );
    } catch {
      announce("Fehler: Sprachsteuerung konnte nicht gestartet werden.", "assertive");
      await stop(false);
    }
  }

  // recording owns the microphone: leave voice mode when a recording begins
  useEffect(() => {
    function onRecordingStarted() {
      if (socketRef.current) {
        void stop(false);
        announce("Sprachsteuerung pausiert: Aufnahme läuft.", "polite");
      }
    }
    window.addEventListener("stt:recording-started", onRecordingStarted);
    return () => window.removeEventListener("stt:recording-started", onRecordingStarted);
  }, [announce, stop]);

  useEffect(() => {
    return () => {
      void stop(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <button
      type="button"
      onClick={() => (active ? void stop(true) : void start())}
      aria-pressed={active}
    >
      {active ? "Sprachsteuerung beenden" : "Sprachsteuerung starten"}
    </button>
  );
}
