import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnnouncerProvider } from "../announcer";
import { RecordView } from "../views/RecordView";

const recorderStop = vi.fn(async () => undefined);
vi.mock("../audio/recorder", () => ({
  startRecorder: vi.fn(async (_onChunk: (c: ArrayBuffer) => void) => ({
    stop: recorderStop,
  })),
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  binaryType = "";
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.();
    });
  }

  send(data: string | ArrayBuffer) {
    if (typeof data === "string") this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  serverSays(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => vi.unstubAllGlobals());

function renderView() {
  render(
    <AnnouncerProvider>
      <RecordView />
    </AnnouncerProvider>,
  );
}

async function startRecording(): Promise<MockWebSocket> {
  await userEvent.click(screen.getByRole("button", { name: "Aufnahme starten" }));
  await screen.findByRole("button", { name: "Aufnahme stoppen" });
  return MockWebSocket.instances[0];
}

describe("RecordView", () => {
  it("starts a session and announces the state change assertively", async () => {
    renderView();
    const socket = await startRecording();
    expect(JSON.parse(socket.sent[0])).toEqual({ type: "start", options: {} });
    expect(screen.getByText("Aufnahme läuft.")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("live-assertive")).toHaveTextContent("Aufnahme gestartet"),
    );
  });

  it("renders committed segments and clears the partial line", async () => {
    renderView();
    const socket = await startRecording();
    socket.serverSays({ type: "partial", text: "Guten Ta" });
    await screen.findByText("Guten Ta");
    socket.serverSays({
      type: "final",
      segment: { id: 0, start: 0, end: 2, text: "Guten Tag." },
    });
    await screen.findByText("Guten Tag.");
    expect(screen.queryByText("Guten Ta")).not.toBeInTheDocument();
  });

  it("stop sends the save flag and returns to idle on server confirmation", async () => {
    renderView();
    const socket = await startRecording();
    await userEvent.click(screen.getByRole("button", { name: "Aufnahme stoppen" }));
    const stopMessage = JSON.parse(socket.sent[1]);
    expect(stopMessage).toEqual({ type: "stop", save: true });
    expect(recorderStop).toHaveBeenCalled();

    socket.serverSays({ type: "stopped", job_id: "abc123" });
    await screen.findByRole("button", { name: "Aufnahme starten" });
    expect(
      screen.getByText(/Vollständige Transkription läuft/),
    ).toBeInTheDocument();
  });

  it("announces server errors assertively", async () => {
    renderView();
    const socket = await startRecording();
    socket.serverSays({ type: "error", message: "Mikrofon nicht gefunden" });
    await waitFor(() =>
      expect(screen.getByTestId("live-assertive")).toHaveTextContent(
        "Fehler: Mikrofon nicht gefunden",
      ),
    );
  });

  it("supports Ctrl+Alt+R to toggle recording", async () => {
    renderView();
    await userEvent.keyboard("{Control>}{Alt>}r{/Alt}{/Control}");
    await screen.findByRole("button", { name: "Aufnahme stoppen" });
  });
});
