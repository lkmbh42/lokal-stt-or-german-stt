import React, { useRef, useState } from "react";

import { useAnnouncer } from "../announcer";

/**
 * Accessible upload: a real, labeled `<input type="file">` is the primary
 * mechanism. Drag-and-drop is a purely additive enhancement on top of it —
 * never required (brief: blind users cannot drag-and-drop reliably).
 */
export function UploadView({ onSubmitted }: { onSubmitted: () => void }) {
  const { announce } = useAnnouncer();
  const [files, setFiles] = useState<File[]>([]);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [hotwords, setHotwords] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    const incoming = Array.from(list);
    setFiles((current) => [...current, ...incoming]);
    setError(null);
    announce(
      incoming.length === 1
        ? `Datei ausgewählt: ${incoming[0].name}`
        : `${incoming.length} Dateien ausgewählt`,
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (files.length === 0) {
      setError("Bitte wählen Sie mindestens eine Audiodatei aus.");
      announce("Fehler: keine Datei ausgewählt", "assertive");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      for (const file of files) {
        const body = new FormData();
        body.append("file", file);
        if (initialPrompt.trim()) body.append("initial_prompt", initialPrompt.trim());
        if (hotwords.trim()) body.append("hotwords", hotwords.trim());
        const response = await fetch("/api/jobs", { method: "POST", body });
        if (!response.ok) {
          const detail = await response
            .json()
            .then((data) => data.detail)
            .catch(() => response.statusText);
          throw new Error(
            typeof detail === "string" ? detail : `Upload fehlgeschlagen (${response.status})`,
          );
        }
      }
      announce(
        files.length === 1
          ? "Datei hochgeladen, Transkription gestartet."
          : `${files.length} Dateien hochgeladen, Transkription gestartet.`,
        "assertive",
      );
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onSubmitted();
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Unbekannter Fehler beim Upload";
      setError(message);
      announce(`Fehler: ${message}`, "assertive");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit} noValidate>
      <div
        className={`dropzone${dragActive ? " active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <label htmlFor="audio-file">
          Audiodateien{" "}
          <span className="hint">(mp3, wav, m4a, mp4, flac – Ablegen per Maus optional)</span>
        </label>
        <input
          id="audio-file"
          ref={fileInputRef}
          type="file"
          multiple
          accept=".mp3,.wav,.m4a,.mp4,.flac,audio/*"
          aria-describedby={error ? "upload-error" : undefined}
          onChange={(event) => addFiles(event.target.files)}
        />
        {files.length > 0 && (
          <ul aria-label="Ausgewählte Dateien">
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`}>
                {file.name}{" "}
                <button
                  type="button"
                  className="action secondary"
                  onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                >
                  Entfernen<span className="visually-hidden">: {file.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label htmlFor="initial-prompt">
          Fachvokabular / Kontext{" "}
          <span className="hint">(optional – Namen, Fachbegriffe, Abkürzungen)</span>
        </label>
        <textarea
          id="initial-prompt"
          rows={2}
          value={initialPrompt}
          onChange={(event) => setInitialPrompt(event.target.value)}
        />
      </div>

      <div>
        <label htmlFor="hotwords">
          Schlüsselwörter <span className="hint">(optional – werden bevorzugt erkannt)</span>
        </label>
        <input
          id="hotwords"
          type="text"
          value={hotwords}
          onChange={(event) => setHotwords(event.target.value)}
        />
      </div>

      {/* announced via the central assertive live region; here it is the
          visible text tied to the input through aria-describedby */}
      {error && (
        <p id="upload-error" className="job-status" data-status="error">
          {error}
        </p>
      )}

      <button type="submit" className="action" disabled={busy}>
        {busy ? "Wird hochgeladen …" : "Transkription starten"}
      </button>
    </form>
  );
}
