/**
 * axe-core gate for the multi-user frontend: zero violations on login,
 * jobs and admin views (same bar as the Phase 1 desktop UI).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";

import { App } from "../App";

const AXE_OPTIONS: axe.RunOptions = {
  rules: { "color-contrast": { enabled: false } },
};

async function expectNoViolations() {
  const results = await axe.run(document.body, AXE_OPTIONS);
  const summary = results.violations.map(
    (violation) => `${violation.impact}: ${violation.id} — ${violation.help}`,
  );
  expect(summary).toEqual([]);
}

function mockApi(role: "admin" | "user" = "user") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), { status });
      if (path === "/api/auth/login") {
        return json({ access_token: "acc", refresh_token: "ref" });
      }
      if (path === "/api/auth/me") {
        return json({
          id: "u1",
          username: "erika",
          role,
          is_active: true,
          created_at: "2026-07-06T10:00:00Z",
          daily_minutes_limit: null,
          monthly_minutes_limit: null,
        });
      }
      if (path === "/api/jobs/quota") {
        return json({
          daily_limit_minutes: 60,
          monthly_limit_minutes: null,
          used_today_minutes: 12.3,
          used_month_minutes: 40,
        });
      }
      if (path === "/api/jobs") {
        return json([
          {
            id: "j1",
            source: "upload",
            filename: "besprechung.wav",
            status: "queued",
            progress: 0,
            error: null,
            created_at: "2026-07-06T10:00:00Z",
            finished_at: null,
            duration: null,
            queue_position: 2,
            eta_seconds: 180,
          },
        ]);
      }
      if (path === "/api/admin/users") {
        return json([
          {
            id: "u1",
            username: "erika",
            role: "admin",
            is_active: true,
            created_at: "2026-07-06T10:00:00Z",
            daily_minutes_limit: 60,
            monthly_minutes_limit: null,
          },
        ]);
      }
      if (path === "/api/admin/audit") {
        return json([
          {
            id: "a1",
            created_at: "2026-07-06T10:00:00Z",
            username: "erika",
            action: "auth.login",
            detail: "",
            ip: "10.0.0.5",
          },
        ]);
      }
      if (path === "/api/admin/stats") {
        return json({
          queue_depth: 1,
          processing: 0,
          speed_factor: 2.1,
          model: "large-v3",
          device: "cuda",
          max_concurrent_jobs: 1,
          users: [
            { username: "erika", job_count: 3, minutes_total: 42.5, storage_bytes: 123456 },
          ],
        });
      }
      return json({ detail: `unmocked ${init?.method ?? "GET"} ${path}` }, 500);
    }),
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("axe-core", () => {
  it("login view has no violations", async () => {
    mockApi();
    render(<App />);
    await screen.findByRole("button", { name: "Anmelden" });
    await expectNoViolations();
  });

  it("jobs view has no violations and shows queue position as text", async () => {
    mockApi();
    localStorage.setItem("stt.access", "acc");
    localStorage.setItem("stt.refresh", "ref");
    render(<App />);
    await screen.findByText(/Position 2 in der Warteschlange, voraussichtlich 3 Minuten/);
    expect(screen.getByText(/Kontingent: heute 12.3 von 60 Minuten/)).toBeInTheDocument();
    await expectNoViolations();
  });

  it("admin view has no violations", async () => {
    mockApi("admin");
    localStorage.setItem("stt.access", "acc");
    localStorage.setItem("stt.refresh", "ref");
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Administration" }));
    await screen.findByRole("heading", { name: "Auditprotokoll" });
    expect(screen.getByText("auth.login")).toBeInTheDocument();
    await expectNoViolations();
  });
});

describe("auth flow", () => {
  it("login stores tokens and lands on the jobs view", async () => {
    mockApi();
    render(<App />);
    await userEvent.type(screen.getByLabelText("Benutzername"), "erika");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheimes-passwort");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    await screen.findByRole("heading", { level: 2, name: "Meine Transkriptionen" });
    expect(localStorage.getItem("stt.access")).toBe("acc");
  });

  it("failed login shows the server message tied to the fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Anmeldung fehlgeschlagen" }), { status: 401 }),
      ),
    );
    render(<App />);
    await userEvent.type(screen.getByLabelText("Benutzername"), "erika");
    await userEvent.type(screen.getByLabelText("Passwort"), "falsch");
    await userEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    const message = await screen.findByText("Anmeldung fehlgeschlagen");
    expect(message).toHaveAttribute("id", "login-error");
    expect(screen.getByLabelText("Benutzername")).toHaveAttribute(
      "aria-describedby",
      "login-error",
    );
  });

  it("non-admin users see no admin navigation", async () => {
    mockApi("user");
    localStorage.setItem("stt.access", "acc");
    localStorage.setItem("stt.refresh", "ref");
    render(<App />);
    await screen.findByRole("heading", { level: 2, name: "Meine Transkriptionen" });
    expect(screen.queryByRole("button", { name: "Administration" })).not.toBeInTheDocument();
  });

  it("expired session falls back to the login view", async () => {
    // access rejected, refresh rejected -> logout path
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.startsWith("/api/auth/refresh")) return new Response(null, { status: 401 });
        return new Response(null, { status: 401 });
      }),
    );
    localStorage.setItem("stt.access", "stale");
    localStorage.setItem("stt.refresh", "stale");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Anmelden" })).toBeInTheDocument(),
    );
    expect(localStorage.getItem("stt.access")).toBeNull();
  });
});
