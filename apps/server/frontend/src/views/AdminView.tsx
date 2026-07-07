import { useCallback, useEffect, useState } from "react";

import { useAnnouncer } from "../announcer";
import { apiFetch, apiJson, AuthExpiredError, formatDetail } from "../api";
import type { AuditEntry, SystemStats, User } from "../types";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AdminView({ onAuthExpired }: { onAuthExpired: () => void }) {
  const { announce } = useAnnouncer();
  const [users, setUsers] = useState<User[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [auditFilter, setAuditFilter] = useState("");

  const guard = useCallback(
    (loadError: unknown) => {
      if (loadError instanceof AuthExpiredError) {
        onAuthExpired();
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Serverfehler");
    },
    [onAuthExpired],
  );

  const loadAll = useCallback(async () => {
    try {
      const query = auditFilter ? `?action=${encodeURIComponent(auditFilter)}` : "";
      const [userList, auditList, systemStats] = await Promise.all([
        apiJson<User[]>("/api/admin/users"),
        apiJson<AuditEntry[]>(`/api/admin/audit${query}`),
        apiJson<SystemStats>("/api/admin/stats"),
      ]);
      setUsers(userList);
      setAudit(auditList);
      setStats(systemStats);
      setError(null);
    } catch (loadError) {
      guard(loadError);
    }
  }, [auditFilter, guard]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  function rejectCreate(message: string) {
    setCreateError(message);
    announce(`Fehler: ${message}`, "assertive");
  }

  async function createUser(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    const username = newUsername.trim();
    // mirror the server's rules client-side: instant, specific feedback
    if (username.length < 3) {
      rejectCreate("Benutzername muss mindestens 3 Zeichen lang sein.");
      return;
    }
    if (!/^[a-zA-Z0-9_.-]+$/.test(username)) {
      rejectCreate(
        "Benutzername darf nur Buchstaben, Zahlen sowie . _ - enthalten (keine Leer- oder Sonderzeichen).",
      );
      return;
    }
    if (newPassword.length < 10) {
      rejectCreate(
        `Passwort muss mindestens 10 Zeichen lang sein (aktuell ${newPassword.length}).`,
      );
      return;
    }
    try {
      const response = await apiFetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password: newPassword }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          formatDetail((payload as { detail?: unknown } | null)?.detail) ??
            "Anlegen fehlgeschlagen",
        );
      }
      announce(`Benutzer ${username} angelegt.`, "assertive");
      setNewUsername("");
      setNewPassword("");
      await loadAll();
    } catch (submitError) {
      if (submitError instanceof AuthExpiredError) {
        onAuthExpired();
        return;
      }
      rejectCreate(
        submitError instanceof Error ? submitError.message : "Anlegen fehlgeschlagen",
      );
    }
  }

  async function patchUser(user: User, patch: object, description: string) {
    try {
      const response = await apiFetch(`/api/admin/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!response.ok) {
        const detail = await response.json().then((d) => d.detail).catch(() => null);
        throw new Error(typeof detail === "string" ? detail : "Änderung fehlgeschlagen");
      }
      announce(`${user.username}: ${description}.`);
      await loadAll();
    } catch (patchError) {
      guard(patchError);
      if (patchError instanceof Error) announce(`Fehler: ${patchError.message}`, "assertive");
    }
  }

  async function exportAuditCsv() {
    try {
      const response = await apiFetch("/api/admin/audit/export");
      if (!response.ok) throw new Error(`Export fehlgeschlagen (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "audit-log.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      announce("Download gestartet: audit-log.csv");
    } catch (exportError) {
      guard(exportError);
    }
  }

  async function setDailyQuota(user: User) {
    const raw = window.prompt(
      `Tageskontingent in Minuten für ${user.username} (leer = Serverstandard):`,
      user.daily_minutes_limit?.toString() ?? "",
    );
    if (raw === null) return;
    const value = raw.trim() === "" ? null : Number(raw);
    if (value !== null && (!Number.isFinite(value) || value < 0)) {
      announce("Fehler: ungültige Minutenangabe", "assertive");
      return;
    }
    await patchUser(
      user,
      { daily_minutes_limit: value },
      value === null ? "Kontingent auf Serverstandard zurückgesetzt" : `Kontingent ${value} min/Tag`,
    );
  }

  return (
    <div>
      {error && (
        <p className="job-status" data-status="error">
          {error}
        </p>
      )}

      <section aria-labelledby="stats-heading">
        <h3 id="stats-heading">Systemstatus</h3>
        {stats && (
          <>
            <p>
              Warteschlange: {stats.queue_depth} wartend, {stats.processing} in Arbeit.
              Modell: {stats.model} ({stats.device}), {stats.max_concurrent_jobs} paralleler
              Auftrag/Aufträge.
              {stats.speed_factor !== null &&
                ` Verarbeitungsgeschwindigkeit: ${stats.speed_factor}× Echtzeit.`}
            </p>
            <table className="shortcuts">
              <caption className="visually-hidden">Nutzung je Benutzer</caption>
              <thead>
                <tr>
                  <th scope="col">Benutzer</th>
                  <th scope="col">Aufträge</th>
                  <th scope="col">Minuten gesamt</th>
                  <th scope="col">Speicher</th>
                </tr>
              </thead>
              <tbody>
                {stats.users.map((row) => (
                  <tr key={row.username}>
                    <td>{row.username}</td>
                    <td>{row.job_count}</td>
                    <td>{row.minutes_total}</td>
                    <td>{formatBytes(row.storage_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section aria-labelledby="users-heading">
        <h3 id="users-heading">Benutzerverwaltung</h3>
        <form className="stack" onSubmit={createUser} noValidate>
          <div>
            <label htmlFor="new-username">
              Benutzername{" "}
              <span className="hint">(mindestens 3 Zeichen; Buchstaben, Zahlen, . _ -)</span>
            </label>
            <input
              id="new-username"
              type="text"
              value={newUsername}
              aria-describedby={createError ? "create-user-error" : undefined}
              onChange={(event) => setNewUsername(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="new-password">
              Passwort <span className="hint">(mindestens 10 Zeichen)</span>
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              aria-describedby={createError ? "create-user-error" : undefined}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </div>
          {createError && (
            <p id="create-user-error" className="job-status" data-status="error">
              {createError}
            </p>
          )}
          <button type="submit" className="action">
            Benutzer anlegen
          </button>
        </form>

        <table className="shortcuts">
          <caption className="visually-hidden">Alle Benutzerkonten</caption>
          <thead>
            <tr>
              <th scope="col">Benutzer</th>
              <th scope="col">Rolle</th>
              <th scope="col">Status</th>
              <th scope="col">Kontingent/Tag</th>
              <th scope="col">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>
                <td>{user.role === "admin" ? "Administrator" : "Benutzer"}</td>
                <td>{user.is_active ? "Aktiv" : "Deaktiviert"}</td>
                <td>
                  {user.daily_minutes_limit !== null
                    ? `${user.daily_minutes_limit} min`
                    : "Standard"}
                </td>
                <td>
                  <div className="exports">
                    <button
                      type="button"
                      className="action secondary"
                      onClick={() =>
                        void patchUser(
                          user,
                          { is_active: !user.is_active },
                          user.is_active ? "deaktiviert" : "aktiviert",
                        )
                      }
                    >
                      {user.is_active ? "Deaktivieren" : "Aktivieren"}
                      <span className="visually-hidden">: {user.username}</span>
                    </button>
                    <button
                      type="button"
                      className="action secondary"
                      onClick={() => void setDailyQuota(user)}
                    >
                      Kontingent<span className="visually-hidden"> für {user.username}</span>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="audit-heading">
        <h3 id="audit-heading">Auditprotokoll</h3>
        <div className="stack">
          <div>
            <label htmlFor="audit-filter">Nach Aktion filtern</label>
            <select
              id="audit-filter"
              value={auditFilter}
              onChange={(event) => setAuditFilter(event.target.value)}
            >
              <option value="">Alle Aktionen</option>
              <option value="auth.login">Anmeldungen</option>
              <option value="auth.login_failed">Fehlgeschlagene Anmeldungen</option>
              <option value="job.submitted">Eingereichte Aufträge</option>
              <option value="job.completed">Abgeschlossene Aufträge</option>
              <option value="quota.rejected">Kontingent-Ablehnungen</option>
              <option value="user.created">Angelegte Benutzer</option>
              <option value="user.updated">Benutzeränderungen</option>
            </select>
          </div>
          <button
            type="button"
            className="action secondary"
            onClick={() => void exportAuditCsv()}
          >
            Als CSV exportieren
          </button>
        </div>
        <table className="shortcuts">
          <caption className="visually-hidden">Auditprotokoll, neueste zuerst</caption>
          <thead>
            <tr>
              <th scope="col">Zeitpunkt</th>
              <th scope="col">Benutzer</th>
              <th scope="col">Aktion</th>
              <th scope="col">Details</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_at).toLocaleString("de-DE")}</td>
                <td>{entry.username}</td>
                <td>{entry.action}</td>
                <td>{entry.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
