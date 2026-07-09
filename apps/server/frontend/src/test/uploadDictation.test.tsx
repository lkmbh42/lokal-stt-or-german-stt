/**
 * Diktatmodus must apply to FILE UPLOADS, not only recordings: ticking the
 * toggle in the upload form sends dictation=true with the uploaded file.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnnouncerProvider } from "../announcer";
import { JobsView } from "../views/JobsView";

function mockApi(capturedPosts: FormData[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), { status });
      if (path === "/api/jobs" && init?.method === "POST") {
        capturedPosts.push(init.body as FormData);
        return json(
          {
            id: "j1",
            source: "upload",
            filename: "a.wav",
            status: "queued",
            progress: 0,
            error: null,
            created_at: "2026-07-08T10:00:00Z",
            finished_at: null,
            duration: null,
            queue_position: 1,
            eta_seconds: null,
          },
          201,
        );
      }
      if (path === "/api/jobs/quota") {
        return json({
          daily_limit_minutes: null,
          monthly_limit_minutes: null,
          used_today_minutes: 0,
          used_month_minutes: 0,
        });
      }
      if (path === "/api/jobs") return json([]);
      return json({}, 500);
    }),
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Diktatmodus for file uploads", () => {
  it("sends dictation=true with the uploaded file when the toggle is on", async () => {
    const posts: FormData[] = [];
    mockApi(posts);
    render(
      <AnnouncerProvider>
        <JobsView onAuthExpired={() => undefined} />
      </AnnouncerProvider>,
    );

    // the toggle appears in both sections; the first one is in the upload form
    const toggles = await screen.findAllByRole("checkbox", { name: /Diktatmodus/ });
    await userEvent.click(toggles[0]);

    const file = new File(["riff"], "a.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText(/Audiodateien/), file);
    await userEvent.click(screen.getByRole("button", { name: "Transkription starten" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].get("dictation")).toBe("true");
    expect((posts[0].get("file") as File).name).toBe("a.wav");
  });

  it("omits the flag when the toggle is off", async () => {
    const posts: FormData[] = [];
    mockApi(posts);
    render(
      <AnnouncerProvider>
        <JobsView onAuthExpired={() => undefined} />
      </AnnouncerProvider>,
    );
    const file = new File(["riff"], "b.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText(/Audiodateien/), file);
    await userEvent.click(screen.getByRole("button", { name: "Transkription starten" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].get("dictation")).toBeNull();
  });

  it("both toggles stay in sync (same setting)", async () => {
    mockApi([]);
    render(
      <AnnouncerProvider>
        <JobsView onAuthExpired={() => undefined} />
      </AnnouncerProvider>,
    );
    const toggles = await screen.findAllByRole("checkbox", { name: /Diktatmodus/ });
    expect(toggles).toHaveLength(2);
    await userEvent.click(toggles[0]);
    expect((toggles[0] as HTMLInputElement).checked).toBe(true);
    expect((toggles[1] as HTMLInputElement).checked).toBe(true);
  });
});
