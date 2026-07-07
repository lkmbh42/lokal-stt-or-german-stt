/**
 * Regression for the "dead record button": microphone failures must be
 * VISIBLE at the button, not only announced to the screen-reader region.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnnouncerProvider } from "../announcer";
import { JobsView } from "../views/JobsView";

vi.mock("../audio/recorder", async () => {
  const actual = await vi.importActual<typeof import("../audio/recorder")>(
    "../audio/recorder",
  );
  return {
    ...actual,
    startRecorder: vi.fn(async () => {
      throw new DOMException("Permission denied", "NotAllowedError");
    }),
  };
});

function mockJobsApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.split("?")[0];
      if (path === "/api/jobs/quota") {
        return new Response(
          JSON.stringify({
            daily_limit_minutes: null,
            monthly_limit_minutes: null,
            used_today_minutes: 0,
            used_month_minutes: 0,
          }),
          { status: 200 },
        );
      }
      if (path === "/api/jobs") return new Response("[]", { status: 200 });
      return new Response("{}", { status: 500 });
    }),
  );
}

beforeEach(() => {
  // jsdom has no mediaDevices; the DOMException branch requires it to exist
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn() },
    configurable: true,
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("record button mic failure", () => {
  it("shows the specific reason visibly, tied to the button", async () => {
    mockJobsApi();
    render(
      <AnnouncerProvider>
        <JobsView onAuthExpired={() => undefined} />
      </AnnouncerProvider>,
    );
    const button = await screen.findByRole("button", { name: "Aufnahme starten" });
    await userEvent.click(button);

    const error = await screen.findByText(/Mikrofonzugriff wurde blockiert/);
    expect(error).toHaveAttribute("id", "record-error");
    expect(button).toHaveAttribute("aria-describedby", "record-error");
    // and it is announced assertively for screen-reader users as well
    await waitFor(() =>
      expect(screen.getByTestId("live-assertive")).toHaveTextContent(
        /Mikrofonzugriff wurde blockiert/,
      ),
    );
  });
});
