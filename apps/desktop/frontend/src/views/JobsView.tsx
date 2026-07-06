import { useEffect, useRef, useState } from "react";

import { useAnnouncer } from "../announcer";
import { playEarcon } from "../audio/earcons";
import { EXPORT_FORMATS, type Job } from "../types";

const STATUS_LABELS: Record<Job["status"], string> = {
  queued: "In Warteschlange",
  processing: "Wird transkribiert",
  done: "Fertig",
  error: "Fehler",
  canceled: "Abgebrochen",
};

function statusText(job: Job): string {
  if (job.status === "processing" && job.progress > 0) {
    return `${STATUS_LABELS.processing} – ${Math.round(job.progress * 100)} %`;
  }
  if (job.status === "error" && job.error) {
    return `${STATUS_LABELS.error}: ${job.error}`;
  }
  return STATUS_LABELS[job.status];
}

export function JobsView({ active }: { active: boolean }) {
  const { announce, earconsEnabled } = useAnnouncer();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const previousStatuses = useRef<Map<string, Job["status"]>>(new Map());

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    async function poll() {
      try {
        const response = await fetch("/api/jobs");
        if (!response.ok) throw new Error(`Serverfehler (${response.status})`);
        const data = (await response.json()) as Job[];
        if (cancelled) return;
        setJobs(data);
        setLoadError(null);
        for (const job of data) {
          const before = previousStatuses.current.get(job.id);
          if (before && before !== job.status) {
            if (job.status === "done") {
              announce(`Transkription abgeschlossen: ${job.filename}`, "assertive");
              playEarcon("complete", earconsEnabled);
            } else if (job.status === "error") {
              announce(
                `Transkription fehlgeschlagen: ${job.filename}. ${job.error ?? ""}`,
                "assertive",
              );
              playEarcon("error", earconsEnabled);
            }
          }
          previousStatuses.current.set(job.id, job.status);
        }
      } catch (pollError) {
        if (!cancelled) {
          setLoadError(
            pollError instanceof Error ? pollError.message : "Verlauf konnte nicht geladen werden",
          );
        }
      }
    }

    void poll();
    const interval = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [active, announce, earconsEnabled]);

  async function deleteJob(job: Job) {
    const verb = job.status === "queued" || job.status === "processing" ? "abgebrochen" : "gelöscht";
    const response = await fetch(`/api/jobs/${job.id}`, { method: "DELETE" });
    if (response.ok) {
      announce(`Auftrag ${job.filename} ${verb}.`);
      setJobs((current) => current.filter((candidate) => candidate.id !== job.id));
    } else {
      announce(`Auftrag konnte nicht ${verb} werden.`, "assertive");
    }
  }

  return (
    <div>
      {loadError && (
        <p className="job-status" data-status="error">
          {loadError}
        </p>
      )}
      {jobs.length === 0 && !loadError && <p>Noch keine Transkriptionen vorhanden.</p>}
      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id} aria-labelledby={`job-${job.id}-name`}>
            <div className="job-head">
              <span id={`job-${job.id}-name`}>
                <strong>{job.filename}</strong>
                {job.source === "live" && " (Aufnahme)"}
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
                  <a
                    key={format.id}
                    className="export-link"
                    href={`/api/jobs/${job.id}/export?format=${format.id}`}
                    download
                  >
                    {format.label}
                    <span className="visually-hidden"> – {job.filename}</span>
                  </a>
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
