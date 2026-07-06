import type { Job } from "../types";
import { formatEta, statusText } from "../views/JobsView";

function job(overrides: Partial<Job>): Job {
  return {
    id: "j1",
    source: "upload",
    filename: "a.wav",
    status: "queued",
    progress: 0,
    error: null,
    created_at: "2026-07-06T10:00:00Z",
    finished_at: null,
    duration: null,
    queue_position: null,
    eta_seconds: null,
    ...overrides,
  };
}

describe("formatEta", () => {
  it("renders sub-minute, singular and plural cases", () => {
    expect(formatEta(30)).toBe("voraussichtlich unter einer Minute");
    expect(formatEta(70)).toBe("voraussichtlich 1 Minute");
    expect(formatEta(200)).toBe("voraussichtlich 3 Minuten");
    expect(formatEta(null)).toBe("");
  });
});

describe("statusText", () => {
  it("queued jobs expose position and ETA as one sentence", () => {
    const text = statusText(job({ queue_position: 3, eta_seconds: 240 }));
    expect(text).toBe("Position 3 in der Warteschlange, voraussichtlich 4 Minuten");
  });

  it("queued without ETA history omits the estimate instead of guessing", () => {
    expect(statusText(job({ queue_position: 1, eta_seconds: null }))).toBe(
      "Position 1 in der Warteschlange",
    );
  });

  it("processing shows percent, errors show the message", () => {
    expect(statusText(job({ status: "processing", progress: 0.42 }))).toBe(
      "Wird transkribiert – 42 %",
    );
    expect(statusText(job({ status: "error", error: "Defekte Datei" }))).toBe(
      "Fehler: Defekte Datei",
    );
  });
});
