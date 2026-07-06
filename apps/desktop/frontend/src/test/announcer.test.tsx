import { render, screen, waitFor } from "@testing-library/react";

import { AnnouncerProvider, TranscriptBatcher, useAnnouncer } from "../announcer";

describe("TranscriptBatcher", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("joins fragments arriving within the batch window", () => {
    const emitted: string[] = [];
    const batcher = new TranscriptBatcher((text) => emitted.push(text), 2500);
    batcher.add("Guten Tag.");
    batcher.add("Wie geht es Ihnen?");
    expect(emitted).toEqual([]); // nothing announced token-by-token
    vi.advanceTimersByTime(2500);
    expect(emitted).toEqual(["Guten Tag. Wie geht es Ihnen?"]);
  });

  it("starts a new batch after the window closes", () => {
    const emitted: string[] = [];
    const batcher = new TranscriptBatcher((text) => emitted.push(text), 2500);
    batcher.add("Erster Satz.");
    vi.advanceTimersByTime(2500);
    batcher.add("Zweiter Satz.");
    vi.advanceTimersByTime(2500);
    expect(emitted).toEqual(["Erster Satz.", "Zweiter Satz."]);
  });

  it("flush emits immediately and ignores empty fragments", () => {
    const emitted: string[] = [];
    const batcher = new TranscriptBatcher((text) => emitted.push(text), 2500);
    batcher.add("   ");
    batcher.flush();
    expect(emitted).toEqual([]);
    batcher.add("Fertig.");
    batcher.flush();
    expect(emitted).toEqual(["Fertig."]);
  });

  it("dispose drops pending fragments", () => {
    const emitted: string[] = [];
    const batcher = new TranscriptBatcher((text) => emitted.push(text), 2500);
    batcher.add("Verworfen");
    batcher.dispose();
    vi.advanceTimersByTime(5000);
    expect(emitted).toEqual([]);
  });
});

function Probe() {
  const { announce } = useAnnouncer();
  return (
    <button type="button" onClick={() => announce("Testansage", "assertive")}>
      Senden
    </button>
  );
}

describe("AnnouncerProvider", () => {
  it("routes announcements into the requested live region", async () => {
    render(
      <AnnouncerProvider>
        <Probe />
      </AnnouncerProvider>,
    );
    screen.getByRole("button", { name: "Senden" }).click();
    await waitFor(() =>
      expect(screen.getByTestId("live-assertive")).toHaveTextContent("Testansage"),
    );
    expect(screen.getByTestId("live-polite")).toBeEmptyDOMElement();
  });
});
