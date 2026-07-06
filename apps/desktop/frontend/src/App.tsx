import { useCallback, useEffect, useRef, useState } from "react";

import { AnnouncerProvider, useAnnouncer } from "./announcer";
import { JobsView } from "./views/JobsView";
import { RecordView } from "./views/RecordView";
import { ShortcutsDialog } from "./views/ShortcutsDialog";
import { UploadView } from "./views/UploadView";

type ViewId = "upload" | "record" | "jobs";

const VIEWS: Array<{ id: ViewId; label: string; shortcut: string }> = [
  { id: "upload", label: "Datei hochladen", shortcut: "1" },
  { id: "record", label: "Aufnahme", shortcut: "2" },
  { id: "jobs", label: "Verlauf & Export", shortcut: "3" },
];

function AppShell() {
  const [view, setView] = useState<ViewId>("upload");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const skipFocusOnMount = useRef(true);
  const { announce, liveTranscriptMuted, setLiveTranscriptMuted, earconsEnabled, setEarconsEnabled } =
    useAnnouncer();

  const switchView = useCallback((next: ViewId) => {
    setView(next);
  }, []);

  // move focus to the section heading on view change (not on first render)
  useEffect(() => {
    if (skipFocusOnMount.current) {
      skipFocusOnMount.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [view]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!event.ctrlKey || !event.altKey || event.shiftKey || event.metaKey) return;
      const key = event.key.toLowerCase();
      const target = VIEWS.find((v) => v.shortcut === key);
      if (target) {
        event.preventDefault();
        switchView(target.id);
        announce(`Bereich: ${target.label}`);
      } else if (key === "k") {
        event.preventDefault();
        setShortcutsOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [announce, switchView]);

  const activeView = VIEWS.find((v) => v.id === view)!;

  return (
    <>
      <a className="skip-link" href="#main">
        Zum Hauptinhalt springen
      </a>
      <header className="app-header">
        <h1>Lokal-STT – Deutsche Spracherkennung</h1>
        <nav className="views" aria-label="Bereiche">
          <ul>
            {VIEWS.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  aria-current={view === v.id ? "page" : undefined}
                  onClick={() => switchView(v.id)}
                >
                  {v.label}
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={() => setShortcutsOpen(true)}
                aria-haspopup="dialog"
              >
                Tastenkürzel
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        <section aria-labelledby="section-heading">
          <h2 id="section-heading" tabIndex={-1} ref={headingRef}>
            {activeView.label}
          </h2>
          {view === "upload" && <UploadView onSubmitted={() => switchView("jobs")} />}
          {view === "record" && <RecordView />}
          {view === "jobs" && <JobsView active />}
        </section>

        <section aria-labelledby="settings-heading">
          <h2 id="settings-heading">Einstellungen zur Vorlesefunktion</h2>
          <fieldset>
            <legend className="visually-hidden">Ansagen und Klänge</legend>
            <label>
              <input
                type="checkbox"
                checked={liveTranscriptMuted}
                onChange={(event) => setLiveTranscriptMuted(event.target.checked)}
              />{" "}
              Live-Transkript nicht automatisch vorlesen (nur Abschluss-Hinweis)
            </label>
            <label>
              <input
                type="checkbox"
                checked={earconsEnabled}
                onChange={(event) => setEarconsEnabled(event.target.checked)}
              />{" "}
              Audio-Signale bei Start/Stopp/Abschluss/Fehler abspielen
            </label>
          </fieldset>
        </section>
      </main>
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </>
  );
}

export function App() {
  return (
    <AnnouncerProvider>
      <AppShell />
    </AnnouncerProvider>
  );
}
