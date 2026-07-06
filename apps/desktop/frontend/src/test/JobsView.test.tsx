import { render, screen, waitFor } from "@testing-library/react";

import { AnnouncerProvider } from "../announcer";
import { JobsView } from "../views/JobsView";
import type { Job } from "../types";

function job(overrides: Partial<Job>): Job {
  return {
    id: "j1",
    source: "upload",
    filename: "besprechung.wav",
    status: "processing",
    progress: 0.4,
    error: null,
    created_at: "2026-07-05T10:00:00Z",
    finished_at: null,
    duration: null,
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

function mockJobsSequence(...responses: Job[][]) {
  let call = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      const payload = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return new Response(JSON.stringify(payload), { status: 200 });
    }),
  );
}

describe("JobsView", () => {
  it("shows progress as text, not only visually", async () => {
    mockJobsSequence([job({ progress: 0.4 })]);
    render(
      <AnnouncerProvider>
        <JobsView active />
      </AnnouncerProvider>,
    );
    expect(await screen.findByText("Wird transkribiert – 40 %")).toBeInTheDocument();
  });

  it("offers all export formats as real download links when done", async () => {
    mockJobsSequence([job({ status: "done", progress: 1, duration: 12.4 })]);
    render(
      <AnnouncerProvider>
        <JobsView active />
      </AnnouncerProvider>,
    );
    await screen.findByText("Fertig");
    const group = screen.getByRole("group", { name: /Export für besprechung.wav/ });
    const links = group.querySelectorAll("a[download]");
    expect(links).toHaveLength(6); // 5 formats + zip
    expect(links[0]).toHaveAttribute("href", "/api/jobs/j1/export?format=txt");
  });

  it("announces completion when a job transitions to done", async () => {
    vi.useFakeTimers();
    try {
      mockJobsSequence([job({ status: "processing" })], [job({ status: "done", progress: 1 })]);
      render(
        <AnnouncerProvider>
          <JobsView active />
        </AnnouncerProvider>,
      );
      await vi.waitFor(() => screen.getByText(/Wird transkribiert/));
      await vi.advanceTimersByTimeAsync(2000); // next poll: done
      await vi.waitFor(() =>
        expect(screen.getByTestId("live-assertive")).toHaveTextContent(
          "Transkription abgeschlossen: besprechung.wav",
        ),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows errors as text associated with the job", async () => {
    mockJobsSequence([job({ status: "error", error: "Datei konnte nicht dekodiert werden" })]);
    render(
      <AnnouncerProvider>
        <JobsView active />
      </AnnouncerProvider>,
    );
    expect(
      await screen.findByText(/Fehler: Datei konnte nicht dekodiert werden/),
    ).toBeInTheDocument();
  });

  it("delete asks the API and announces the removal", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      return new Response(JSON.stringify([job({ status: "done" })]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AnnouncerProvider>
        <JobsView active />
      </AnnouncerProvider>,
    );
    const deleteButton = await screen.findByRole("button", {
      name: /Löschen.*besprechung\.wav/,
    });
    deleteButton.click();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/jobs/j1", { method: "DELETE" }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("live-polite")).toHaveTextContent("gelöscht"),
    );
  });
});
