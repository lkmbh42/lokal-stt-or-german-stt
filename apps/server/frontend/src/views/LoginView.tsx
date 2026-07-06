import { useState } from "react";

import { useAnnouncer } from "../announcer";
import { login } from "../api";

export function LoginView({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { announce } = useAnnouncer();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      announce("Anmeldung erfolgreich.", "assertive");
      onLoggedIn();
    } catch (loginError) {
      const message =
        loginError instanceof Error ? loginError.message : "Anmeldung fehlgeschlagen";
      setError(message);
      announce(`Fehler: ${message}`, "assertive");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="login-heading">
      <h1 id="login-heading">Lokal-STT Team – Anmeldung</h1>
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <div>
          <label htmlFor="login-username">Benutzername</label>
          <input
            id="login-username"
            type="text"
            autoComplete="username"
            required
            value={username}
            aria-describedby={error ? "login-error" : undefined}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="login-password">Passwort</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            aria-describedby={error ? "login-error" : undefined}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && (
          <p id="login-error" className="job-status" data-status="error">
            {error}
          </p>
        )}
        <button type="submit" className="action" disabled={busy}>
          {busy ? "Wird angemeldet …" : "Anmelden"}
        </button>
      </form>
    </section>
  );
}
