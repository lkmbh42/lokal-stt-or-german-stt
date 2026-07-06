export type JobStatus = "queued" | "processing" | "done" | "error" | "canceled";

export interface Job {
  id: string;
  source: "upload" | "live";
  filename: string;
  status: JobStatus;
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  duration: number | null;
  text_preview?: string | null;
}

export interface HealthInfo {
  status: string;
  model: string;
  device: string;
  formats: string[];
  max_upload_mb: number;
}

export type LiveServerMessage =
  | { type: "ready" }
  | { type: "partial"; text: string }
  | {
      type: "final";
      segment: { id: number; start: number; end: number; text: string };
    }
  | { type: "stopped"; job_id: string | null }
  | { type: "error"; message: string };

export const EXPORT_FORMATS = [
  { id: "txt", label: "Text (.txt)" },
  { id: "srt", label: "Untertitel (.srt)" },
  { id: "vtt", label: "WebVTT (.vtt)" },
  { id: "json", label: "JSON mit Wort-Zeitstempeln (.json)" },
  { id: "docx", label: "Word-Dokument (.docx)" },
  { id: "all", label: "Alle Formate (.zip)" },
] as const;
