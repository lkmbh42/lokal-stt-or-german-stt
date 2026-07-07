/**
 * Regression for the "Anlegen fehlgeschlagen" UX bug: user creation must
 * explain WHAT is wrong (short password etc.), not fail generically.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { formatDetail } from "../api";
import { AnnouncerProvider } from "../announcer";
import { AdminView } from "../views/AdminView";

describe("formatDetail", () => {
  it("passes plain HTTPException strings through", () => {
    expect(formatDetail("Benutzername bereits vergeben")).toBe(
      "Benutzername bereits vergeben",
    );
  });

  it("renders pydantic 422 arrays as readable German", () => {
    const detail = [
      {
        loc: ["body", "password"],
        msg: "String should have at least 10 characters",
        type: "string_too_short",
      },
    ];
    expect(formatDetail(detail)).toBe("Passwort: mindestens 10 Zeichen erforderlich");
  });

  it("returns null for unknown shapes (caller falls back to generic)", () => {
    expect(formatDetail(undefined)).toBeNull();
    expect(formatDetail({ weird: true })).toBeNull();
  });
});

describe("AdminView user creation validation", () => {
  function renderAdmin() {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = url.split("?")[0];
        if (path === "/api/admin/users") return new Response("[]", { status: 200 });
        if (path === "/api/admin/audit") return new Response("[]", { status: 200 });
        if (path === "/api/admin/stats") {
          return new Response(
            JSON.stringify({
              queue_depth: 0,
              processing: 0,
              speed_factor: null,
              model: "x",
              device: "cpu",
              max_concurrent_jobs: 1,
              users: [],
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 500 });
      }),
    );
    render(
      <AnnouncerProvider>
        <AdminView onAuthExpired={() => undefined} />
      </AnnouncerProvider>,
    );
  }

  afterEach(() => vi.unstubAllGlobals());

  it("rejects a too-short password locally with a specific message", async () => {
    renderAdmin();
    await userEvent.type(await screen.findByLabelText(/Benutzername/), "Hani");
    await userEvent.type(screen.getByLabelText(/Passwort/), "kurz12");
    await userEvent.click(screen.getByRole("button", { name: "Benutzer anlegen" }));

    const error = await screen.findByText(/mindestens 10 Zeichen lang sein \(aktuell 6\)/);
    expect(error).toHaveAttribute("id", "create-user-error");
    expect(screen.getByLabelText(/Passwort/)).toHaveAttribute(
      "aria-describedby",
      "create-user-error",
    );
    // no POST was attempted — rejected before the network
    const posts = (fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(posts).toHaveLength(0);
  });

  it("rejects usernames with spaces or special characters", async () => {
    renderAdmin();
    await userEvent.type(await screen.findByLabelText(/Benutzername/), "Hani Alkas");
    await userEvent.type(screen.getByLabelText(/Passwort/), "langes-passwort-123");
    await userEvent.click(screen.getByRole("button", { name: "Benutzer anlegen" }));
    expect(
      await screen.findByText(/nur Buchstaben, Zahlen sowie . _ -/),
    ).toBeInTheDocument();
  });
});
