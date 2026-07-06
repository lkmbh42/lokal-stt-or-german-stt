import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnnouncerProvider } from "../announcer";
import { UploadView } from "../views/UploadView";

function renderView(onSubmitted = vi.fn()) {
  render(
    <AnnouncerProvider>
      <UploadView onSubmitted={onSubmitted} />
    </AnnouncerProvider>,
  );
  return onSubmitted;
}

afterEach(() => vi.unstubAllGlobals());

describe("UploadView", () => {
  it("uses a real labeled file input (no drag-and-drop dependency)", () => {
    renderView();
    const input = screen.getByLabelText(/Audiodateien/);
    expect(input).toBeInstanceOf(HTMLInputElement);
    expect((input as HTMLInputElement).type).toBe("file");
  });

  it("rejects submit without a file, ties the error to the input and announces it", async () => {
    renderView();
    await userEvent.click(screen.getByRole("button", { name: "Transkription starten" }));
    const error = await screen.findByText(/mindestens eine Audiodatei/);
    expect(error).toHaveAttribute("id", "upload-error");
    expect(screen.getByLabelText(/Audiodateien/)).toHaveAttribute(
      "aria-describedby",
      "upload-error",
    );
    await waitFor(() =>
      expect(screen.getByTestId("live-assertive")).toHaveTextContent("keine Datei ausgewählt"),
    );
  });

  it("posts multipart form data including vocabulary options", async () => {
    const calls: Array<{ url: string; body: FormData }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push({ url, body: init.body as FormData });
        return new Response(JSON.stringify({ id: "job1", status: "queued" }), { status: 201 });
      }),
    );
    const onSubmitted = renderView();

    const file = new File(["riff"], "besprechung.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText(/Audiodateien/), file);
    await userEvent.type(screen.getByLabelText(/Fachvokabular/), "Anthropic");
    await userEvent.type(screen.getByLabelText(/Schlüsselwörter/), "Müller GmbH");
    await userEvent.click(screen.getByRole("button", { name: "Transkription starten" }));

    await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/jobs");
    expect((calls[0].body.get("file") as File).name).toBe("besprechung.wav");
    expect(calls[0].body.get("initial_prompt")).toBe("Anthropic");
    expect(calls[0].body.get("hotwords")).toBe("Müller GmbH");
  });

  it("surfaces server-side rejection messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Dateityp .exe wird nicht unterstützt." }), {
          status: 400,
        }),
      ),
    );
    renderView();
    const file = new File(["x"], "boese.exe");
    // applyAccept off: the point is server-side validation of a bad type
    await userEvent.upload(screen.getByLabelText(/Audiodateien/), file, {
      applyAccept: false,
    });
    await userEvent.click(screen.getByRole("button", { name: "Transkription starten" }));
    expect(await screen.findByText(/wird nicht unterstützt/)).toBeInTheDocument();
  });
});
