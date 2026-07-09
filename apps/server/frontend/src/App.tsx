import { useCallback, useEffect, useRef, useState } from "react";

import { AnnouncerProvider, useAnnouncer } from "./announcer";
import { apiJson, AuthExpiredError, isLoggedIn, logout } from "./api";
import type { User } from "./types";
import { AdminView } from "./views/AdminView";
import { JobsView } from "./views/JobsView";
import { LoginView } from "./views/LoginView";
import { VocabularyView } from "./views/VocabularyView";

type ViewId = "jobs" | "vocabulary" | "admin";

const VIEW_TITLES: Record<ViewId, string> = {
  jobs: "Meine Transkriptionen",
  vocabulary: "Wörterbuch",
  admin: "Administration",
};

function AppShell() {
  const { announce } = useAnnouncer();
  const [me, setMe] = useState<User | null>(null);
  const [checking, setChecking] = useState(isLoggedIn());
  const [view, setView] = useState<ViewId>("jobs");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  const loadMe = useCallback(async () => {
    try {
      setMe(await apiJson<User>("/api/auth/me"));
    } catch (error) {
      if (error instanceof AuthExpiredError) setMe(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (isLoggedIn()) void loadMe();
  }, [loadMe]);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [view, me]);

  if (checking) return <main id="main"><p>Anmeldung wird geprüft …</p></main>;

  if (!me) {
    return (
      <main id="main">
        <LoginView
          onLoggedIn={() => {
            setChecking(true);
            void loadMe();
          }}
        />
      </main>
    );
  }

  const handleLogout = () => {
    logout();
    setMe(null);
    setView("jobs");
    announce("Abgemeldet.", "assertive");
  };

  return (
    <>
      <a className="skip-link" href="#main">
        Zum Hauptinhalt springen
      </a>
      <header className="app-header">
        <h1>Lokal-STT Team – Deutsche Spracherkennung</h1>
        <nav className="views" aria-label="Bereiche">
          <ul>
            <li>
              <button
                type="button"
                aria-current={view === "jobs" ? "page" : undefined}
                onClick={() => setView("jobs")}
              >
                Meine Transkriptionen
              </button>
            </li>
            <li>
              <button
                type="button"
                aria-current={view === "vocabulary" ? "page" : undefined}
                onClick={() => setView("vocabulary")}
              >
                Wörterbuch
              </button>
            </li>
            {me.role === "admin" && (
              <li>
                <button
                  type="button"
                  aria-current={view === "admin" ? "page" : undefined}
                  onClick={() => setView("admin")}
                >
                  Administration
                </button>
              </li>
            )}
            <li>
              <button type="button" onClick={handleLogout}>
                Abmelden<span className="visually-hidden"> ({me.username})</span>
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        <section aria-labelledby="section-heading">
          <h2 id="section-heading" tabIndex={-1} ref={headingRef}>
            {VIEW_TITLES[view]}
          </h2>
          {view === "jobs" && <JobsView onAuthExpired={() => setMe(null)} />}
          {view === "vocabulary" && <VocabularyView onAuthExpired={() => setMe(null)} />}
          {view === "admin" && <AdminView onAuthExpired={() => setMe(null)} />}
        </section>
      </main>
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
