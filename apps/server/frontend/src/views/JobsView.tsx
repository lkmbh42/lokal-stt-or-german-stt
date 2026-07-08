import { useCallback, useEffect, useRef, useState } from "react";

import { useAnnouncer } from "../announcer";
import { apiFetch, apiJson, AuthExpiredError, downloadExport } from "../api";
import { describeMicError, startRecorder, type Recorder } from "../audio/recorder";
import { pcmChunksToWav } from "../audio/wav";
import { EXPORT_FORMATS, type Job, type Quota } from "../types";

const STATUS_LABELS: Record<Job["status"], string> = {
  queued: "In Warteschlange",
  processing: "Wird transkribiert",
  done: "Fertig",
  error: "Fehler",
  canceled: "Abgebrochen",
};

export function formatEta(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return "voraussichtlich unter einer Minute";
  const minutes = Math.round(seconds / 60);
  return minutes === 1
    ? "voraussichtlich 1 Minute"
    : `voraussichtlich ${minutes} Minuten`;
}

export function statusText(job: Job): string {
  if (job.status === "queued" && job.queue_position !== null) {
    const eta = formatEta(job.eta_seconds);
    return `Position ${job.queue_position} in der Warteschlange${eta ? `, ${eta}` : ""}`;
  }
  if (job.status === "processing" && job.progress > 0) {
    return `${STATUS_LABELS.processing} – ${Math.round(job.progress * 100)} %`;
  }
  if (job.status === "error" && job.error) {
    return `${STATUS_LABELS.error}: ${job.error}`;
  }
  return STATUS_LABELS[job.status];
}

function formatQuota(quota: Quota): string {
  const parts: string[] = [];
  if (quota.daily_limit_minutes !== null) {
    parts.push(
      `heute ${quota.used_today_minutes.toFixed(1)} von ` +
        `${quota.daily_limit_minutes} Minuten verwendet`,
    );
  }
  if (quota.monthly_limit_minutes !== null) {
    parts.push(
      `diesen Monat ${quota.used_month_minutes.toFixed(1)} von ` +
        `${quota.monthly_limit_minutes} Minuten`,
    );
  }
  return parts.length ? `Kontingent: ${parts.join("; ")}.` : "";
}

export function JobsView({ onAuthExpired }: { onAuthExpired: () => void }) {
  const { announce } = useAnnouncer();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [audioProcessing, setAudioProcessing] = useState(false);
  // persisted so it doesn't silently reset on reload (a reset here is easy to
  // miss and makes a recording come out with literal command words)
  const [dictationMode, setDictationModeState] = useState(() => {
    try {
      return localStorage.getItem("stt.dictation") === "true";
    } catch {
      return false;
    }
  });
  function setDictationMode(value: boolean) {
    setDictationModeState(value);
    try {
      localStorage.setItem("stt.dictation", String(value));
    } catch {
      /* private mode: setting simply doesn't persist */
    }
  }
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const pcmRef = useRef<Int16Array[]>([]);
  const previousStatuses = useRef<Map<string, Job["status"]>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const [jobList, quotaStatus] = await Promise.all([
        apiJson<Job[]>("/api/jobs"),
        apiJson<Quota>("/api/jobs/quota"),
      ]);
      setJobs(jobList);
      setQuota(quotaStatus);
      for (const job of jobList) {
        const before = previousStatuses.current.get(job.id);
        if (before && before !== job.status) {
          if (job.status === "done") {
            announce(`Transkription abgeschlossen: ${job.filename}`, "assertive");
          } else if (job.status === "error") {
            announce(`Transkription fehlgeschlagen: ${job.filename}`, "assertive");
          } else if (job.status === "processing") {
            announce(`Transkription gestartet: ${job.filename}`);
          }
        }
        previousStatuses.current.set(job.id, job.status);
      }
    } catch (refreshError) {
      if (refreshError instanceof AuthExpiredError) onAuthExpired();
    }
  }, [announce, onAuthExpired]);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  async function submitFiles(toSubmit: File[]) {
    setBusy(true);
    setError(null);
    try {
      for (const file of toSubmit) {
        const body = new FormData();
        body.append("file", file);
        if (initialPrompt.trim()) body.append("initial_prompt", initialPrompt.trim());
        if (dictationMode) body.append("dictation", "true");
        const response = await apiFetch("/api/jobs", { method: "POST", body });
        if (!response.ok) {
          const detail = await response
            .json()
            .then((data) => data.detail)
            .catch(() => null);
          throw new Error(
            typeof detail === "string" ? detail : `Upload fehlgeschlagen (${response.status})`,
          );
        }
        const job = (await response.json()) as Job;
        announce(
          `${file.name} eingereicht. ${statusText(job)}.`,
          "assertive",
        );
      }
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refresh();
    } catch (submitError) {
      if (submitError instanceof AuthExpiredError) {
        onAuthExpired();
        return;
      }
      const message =
        submitError instanceof Error ? submitError.message : "Unbekannter Fehler";
      setError(message);
      announce(`Fehler: ${message}`, "assertive");
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (files.length === 0) {
      setError("Bitte wählen Sie mindestens eine Audiodatei aus.");
      announce("Fehler: keine Datei ausgewählt", "assertive");
      return;
    }
    await submitFiles(files);
  }

  async function toggleRecording() {
    if (!recording) {
      setRecordError(null);
      try {
        pcmRef.current = [];
        recorderRef.current = await startRecorder(
          (chunk) => {
            pcmRef.current.push(new Int16Array(chunk));
          },
          { audioProcessing },
        );
        setRecording(true);
        announce(
          dictationMode
            ? "Aufnahme im Diktatmodus gestartet. Satzzeichen bitte mitsprechen."
            : "Aufnahme gestartet",
          "assertive",
        );
      } catch (micError) {
        // visible AND announced — a silent failure looks like a dead button
        const message = describeMicError(micError);
        setRecordError(message);
        announce(`Fehler: ${message}`, "assertive");
      }
      return;
    }
    await recorderRef.current?.stop().catch(() => undefined);
    recorderRef.current = null;
    setRecording(false);
    const blob = pcmChunksToWav(pcmRef.current);
    pcmRef.current = [];
    if (blob.size <= 44) {
      announce("Aufnahme war leer.", "assertive");
      return;
    }
    const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
    announce("Aufnahme beendet, wird hochgeladen …", "assertive");
    await submitFiles([new File([blob], `aufnahme-${stamp}.wav`, { type: "audio/wav" })]);
  }

  async function deleteJob(job: Job) {
    const verb =
      job.status === "queued" || job.status === "processing" ? "abgebrochen" : "gelöscht";
    try {
      const response = await apiFetch(`/api/jobs/${job.id}`, { method: "DELETE" });
      if (response.ok) {
        announce(`Auftrag ${job.filename} ${verb}.`);
        await refresh();
      }
    } catch (deleteError) {
      if (deleteError instanceof AuthExpiredError) onAuthExpired();
    }
  }

  async function exportJob(job: Job, format: string) {
    const stem = job.filename.replace(/\.[^.]+$/, "") || "transkript";
    const name = format === "all" ? `${stem}.zip` : `${stem}.${format}`;
    try {
      await downloadExport(job.id, format, name);
      announce(`Download gestartet: ${name}`);
    } catch {
      announce("Fehler: Export fehlgeschlagen", "assertive");
    }
  }

  return (
    <div>
      {quota && formatQuota(quota) && <p>{formatQuota(quota)}</p>}

      <h3>Neue Transkription</h3>
      <form className="stack" onSubmit={handleUploadSubmit} noValidate>
        <div>
          <label htmlFor="audio-file">
            Audiodateien <span className="hint">(mp3, wav, m4a, mp4, flac)</span>
          </label>
          <input
            id="audio-file"
            ref={fileInputRef}
            type="file"
            multiple
            accept=".mp3,.wav,.m4a,.mp4,.flac,audio/*"
            aria-describedby={error ? "submit-error" : undefined}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </div>
        <div>
          <label htmlFor="initial-prompt">
            Fachvokabular / Kontext <span className="hint">(optional)</span>
          </label>
          <input
            id="initial-prompt"
            type="text"
            value={initialPrompt}
            onChange={(event) => setInitialPrompt(event.target.value)}
          />
        </div>
        {error && (
          <p id="submit-error" className="job-status" data-status="error">
            {error}
          </p>
        )}
        <button type="submit" className="action" disabled={busy}>
          {busy ? "Wird hochgeladen …" : "Transkription starten"}
        </button>
      </form>

      <h3>Oder direkt aufnehmen</h3>
      <p className="hint">
        Die Aufnahme wird nach dem Stoppen als Auftrag hochgeladen und in voller
        Qualität transkribiert.
      </p>
      <div>
        <label>
          <input
            type="checkbox"
            checked={dictationMode}
            disabled={recording}
            onChange={(event) => setDictationMode(event.target.checked)}
          />{" "}
          <strong>Diktatmodus</strong> — gesprochene Satzzeichen umsetzen{" "}
          <span className="hint">(gilt auch für Datei-Upload)</span>
        </label>
        {dictationMode && (
          <p className="hint">
            Sprechen Sie die Satzzeichen mit: „Komma“ →&nbsp;, · „Punkt“ →&nbsp;. ·
            „Fragezeichen“ →&nbsp;? · „Ausrufezeichen“ →&nbsp;! · „Doppelpunkt“ →&nbsp;: ·
            „Semikolon“ →&nbsp;; · „Klammer auf/zu“ →&nbsp;( ) ·
            „Anführungszeichen auf/zu“ →&nbsp;„ “ · „Gedankenstrich“ →&nbsp;– ·
            „neue Zeile“.
          </p>
        )}
      </div>
      <label>
        <input
          type="checkbox"
          checked={audioProcessing}
          disabled={recording}
          onChange={(event) => setAudioProcessing(event.target.checked)}
        />{" "}
        Browser-Audioverarbeitung (Rauschunterdrückung, Verstärkung){" "}
        <span className="hint">
          — normalerweise aus für beste Erkennung; nur bei lauter Umgebung einschalten
        </span>
      </label>
      <button
        type="button"
        className={recording ? "action danger" : "action secondary"}
        aria-describedby={recordError ? "record-error" : undefined}
        onClick={() => void toggleRecording()}
      >
        {recording ? "Aufnahme stoppen und hochladen" : "Aufnahme starten"}
      </button>
      {recording && (
        <p>
          Aufnahme läuft — sprechen Sie jetzt.
          {dictationMode && (
            <>
              {" "}
              <strong>Diktatmodus aktiv:</strong> Satzzeichen mitsprechen
              (z.&nbsp;B. „Komma“, „Punkt“, „Klammer auf“).
            </>
          )}
        </p>
      )}
      {recordError && (
        <p id="record-error" className="job-status" data-status="error">
          {recordError}
        </p>
      )}

      <h3>Verlauf</h3>
      {jobs.length === 0 && <p>Noch keine Transkriptionen vorhanden.</p>}
      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id} aria-labelledby={`job-${job.id}-name`}>
            <div className="job-head">
              <span id={`job-${job.id}-name`}>
                <strong>{job.filename}</strong>
              </span>
              <span className="job-status" data-status={job.status}>
                {statusText(job)}
              </span>
              {job.duration != null && (
                <span className="hint">{Math.round(job.duration)} Sekunden Audio</span>
              )}
            </div>
            {job.status === "done" && (
              <div className="exports" role="group" aria-label={`Export für ${job.filename}`}>
                {EXPORT_FORMATS.map((format) => (
                  <button
                    key={format.id}
                    type="button"
                    className="action secondary"
                    onClick={() => void exportJob(job, format.id)}
                  >
                    {format.label}
                    <span className="visually-hidden"> – {job.filename}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="exports">
              <button type="button" className="action danger" onClick={() => void deleteJob(job)}>
                {job.status === "queued" || job.status === "processing"
                  ? "Abbrechen"
                  : "Löschen"}
                <span className="visually-hidden">: {job.filename}</span>
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
