export type JobStatus = "queued" | "processing" | "done" | "error" | "canceled";

export interface Job {
  id: string;
  source: string;
  filename: string;
  status: JobStatus;
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  duration: number | null;
  queue_position: number | null;
  eta_seconds: number | null;
  text_preview?: string | null;
  username?: string | null;
}

export interface User {
  id: string;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  daily_minutes_limit: number | null;
  monthly_minutes_limit: number | null;
}

export interface Quota {
  daily_limit_minutes: number | null;
  monthly_limit_minutes: number | null;
  used_today_minutes: number;
  used_month_minutes: number;
}

export interface AuditEntry {
  id: string;
  created_at: string;
  username: string;
  action: string;
  detail: string;
  ip: string | null;
}

export interface SystemStats {
  queue_depth: number;
  processing: number;
  speed_factor: number | null;
  model: string;
  device: string;
  max_concurrent_jobs: number;
  users: Array<{
    username: string;
    job_count: number;
    minutes_total: number;
    storage_bytes: number;
  }>;
}

export const EXPORT_FORMATS = [
  { id: "txt", label: "Text (.txt)" },
  { id: "srt", label: "Untertitel (.srt)" },
  { id: "vtt", label: "WebVTT (.vtt)" },
  { id: "json", label: "JSON (.json)" },
  { id: "docx", label: "Word (.docx)" },
  { id: "all", label: "Alle (.zip)" },
] as const;
