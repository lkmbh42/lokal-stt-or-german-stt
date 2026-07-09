import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnnouncerProvider } from "../announcer";
import { VocabularyView } from "../views/VocabularyView";

interface Entry {
  id: string;
  term: string;
  variants: string;
  created_at: string;
}

function mockApi(store: Entry[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), { status });
      if (path === "/api/vocabulary" && (!init || init.method === undefined)) {
        return json(store);
      }
      if (path === "/api/vocabulary" && init?.method === "POST") {
        const body = JSON.parse(init.body as string);
        const entry: Entry = {
          id: `v${store.length + 1}`,
          term: body.term,
          variants: body.variants ?? "",
          created_at: "2026-07-08T10:00:00Z",
        };
        store.push(entry);
        return json(entry, 201);
      }
      if (path.startsWith("/api/vocabulary/") && init?.method === "DELETE") {
        const id = path.split("/").pop();
        const idx = store.findIndex((e) => e.id === id);
        if (idx >= 0) store.splice(idx, 1);
        return new Response(null, { status: 204 });
      }
      return json({}, 500);
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

function renderView() {
  render(
    <AnnouncerProvider>
      <VocabularyView onAuthExpired={() => undefined} />
    </AnnouncerProvider>,
  );
}

describe("VocabularyView", () => {
  it("adds a term with variants and shows it in the table", async () => {
    const store: Entry[] = [];
    mockApi(store);
    renderView();
    await screen.findByText("Noch keine Begriffe gespeichert.");

    await userEvent.type(screen.getByLabelText(/Begriff/), "Cappel");
    await userEvent.type(screen.getByLabelText(/falsch erkannt/), "Kabel, Kappel");
    await userEvent.click(screen.getByRole("button", { name: "Begriff hinzufügen" }));

    expect(await screen.findByText("Cappel")).toBeInTheDocument();
    expect(screen.getByText("Kabel, Kappel")).toBeInTheDocument();
    expect(store).toHaveLength(1);
  });

  it("requires a term", async () => {
    mockApi([]);
    renderView();
    await screen.findByText("Noch keine Begriffe gespeichert.");
    await userEvent.click(screen.getByRole("button", { name: "Begriff hinzufügen" }));
    expect(await screen.findByText(/Bitte einen Begriff eingeben/)).toBeInTheDocument();
  });

  it("deletes a term", async () => {
    const store: Entry[] = [
      { id: "v1", term: "Cappel", variants: "Kabel", created_at: "2026-07-08T10:00:00Z" },
    ];
    mockApi(store);
    renderView();
    const del = await screen.findByRole("button", { name: /Löschen.*Cappel/ });
    await userEvent.click(del);
    await waitFor(() => expect(store).toHaveLength(0));
    expect(await screen.findByText("Noch keine Begriffe gespeichert.")).toBeInTheDocument();
  });
});
