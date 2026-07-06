/**
 * Automated accessibility gate: axe-core must report zero violations on
 * every main view (CI fails otherwise — see project brief, Testing
 * requirement). color-contrast is checked manually instead: jsdom does not
 * render, so axe's contrast probe is unreliable here.
 */

import { render, screen } from "@testing-library/react";
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

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("axe-core", () => {
  it("upload view has no violations", async () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { level: 1, name: /Lokal-STT/ }),
    ).toBeInTheDocument();
    await expectNoViolations();
  });

  it("record view has no violations", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Aufnahme" }));
    await screen.findByRole("button", { name: "Aufnahme starten" });
    await expectNoViolations();
  });

  it("jobs view has no violations", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Verlauf & Export" }));
    await screen.findByText("Noch keine Transkriptionen vorhanden.");
    await expectNoViolations();
  });

  it("shortcuts dialog has no violations and lists every core action", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Tastenkürzel" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Aufnahme starten / stoppen");
    expect(dialog).toHaveTextContent("Verlauf & Export");
    await expectNoViolations();
  });
});

describe("structural accessibility", () => {
  it("has a skip link targeting main", async () => {
    render(<App />);
    const skipLink = screen.getByRole("link", { name: "Zum Hauptinhalt springen" });
    expect(skipLink).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")?.tagName).toBe("MAIN");
  });

  it("moves focus to the section heading when switching views", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Aufnahme" }));
    const heading = screen.getByRole("heading", { level: 2, name: "Aufnahme" });
    expect(heading).toHaveFocus();
  });

  it("exposes polite and assertive live regions", () => {
    render(<App />);
    expect(screen.getByTestId("live-polite")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByTestId("live-assertive")).toHaveAttribute("aria-live", "assertive");
  });
});
