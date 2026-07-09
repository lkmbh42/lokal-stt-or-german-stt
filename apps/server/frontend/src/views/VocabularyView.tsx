import { useCallback, useEffect, useState } from "react";

import { useAnnouncer } from "../announcer";
import { apiFetch, apiJson, AuthExpiredError } from "../api";
import type { VocabularyEntry } from "../types";

/**
 * Per-user custom dictionary. Each entry is a correct term (boosted so the
 * model recognizes it) plus optional common mishears (auto-corrected to the
 * term). Applied automatically to every transcription — set once, benefit
 * on every job.
 */
export function VocabularyView({ onAuthExpired }: { onAuthExpired: () => void }) {
  const { announce } = useAnnouncer();
  const [entries, setEntries] = useState<VocabularyEntry[]>([]);
  const [term, setTerm] = useState("");
  const [variants, setVariants] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEntries(await apiJson<VocabularyEntry[]>("/api/vocabulary"));
      setError(null);
    } catch (loadError) {
      if (loadError instanceof AuthExpiredError) onAuthExpired();
    }
  }, [onAuthExpired]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addEntry(event: React.FormEvent) {
    event.preventDefault();
    if (!term.trim()) {
      setError("Bitte einen Begriff eingeben.");
      announce("Fehler: kein Begriff eingegeben", "assertive");
      return;
    }
    try {
      const response = await apiFetch("/api/vocabulary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ term: term.trim(), variants: variants.trim() }),
      });
      if (!response.ok) throw new Error(`Speichern fehlgeschlagen (${response.status})`);
      announce(`Begriff „${term.trim()}“ gespeichert.`, "assertive");
      setTerm("");
      setVariants("");
      setError(null);
      await load();
    } catch (addError) {
      if (addError instanceof AuthExpiredError) {
        onAuthExpired();
        return;
      }
      const message = addError instanceof Error ? addError.message : "Fehler";
      setError(message);
      announce(`Fehler: ${message}`, "assertive");
    }
  }

  async function removeEntry(entry: VocabularyEntry) {
    try {
      const response = await apiFetch(`/api/vocabulary/${entry.id}`, { method: "DELETE" });
      if (response.ok) {
        announce(`Begriff „${entry.term}“ gelöscht.`);
        await load();
      }
    } catch (deleteError) {
      if (deleteError instanceof AuthExpiredError) onAuthExpired();
    }
  }

  return (
    <div>
      <p>
        Begriffe aus Ihrem Wörterbuch werden bei jeder Transkription bevorzugt
        erkannt. Häufige Fehlschreibungen (Feld „Wird oft falsch erkannt als“)
        werden automatisch zum richtigen Begriff korrigiert.
      </p>

      <form className="stack" onSubmit={addEntry} noValidate>
        <div>
          <label htmlFor="vocab-term">
            Begriff <span className="hint">(korrekte Schreibweise, z.&nbsp;B. Cappel)</span>
          </label>
          <input
            id="vocab-term"
            type="text"
            value={term}
            aria-describedby={error ? "vocab-error" : undefined}
            onChange={(event) => setTerm(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="vocab-variants">
            Wird oft falsch erkannt als{" "}
            <span className="hint">(optional, mit Komma trennen: Kabel, Kappel)</span>
          </label>
          <input
            id="vocab-variants"
            type="text"
            value={variants}
            onChange={(event) => setVariants(event.target.value)}
          />
        </div>
        {error && (
          <p id="vocab-error" className="job-status" data-status="error">
            {error}
          </p>
        )}
        <button type="submit" className="action">
          Begriff hinzufügen
        </button>
      </form>

      <h3>Gespeicherte Begriffe</h3>
      {entries.length === 0 && <p>Noch keine Begriffe gespeichert.</p>}
      {entries.length > 0 && (
        <table className="shortcuts">
          <caption className="visually-hidden">Ihr persönliches Wörterbuch</caption>
          <thead>
            <tr>
              <th scope="col">Begriff</th>
              <th scope="col">Wird korrigiert von</th>
              <th scope="col">Aktion</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.term}</td>
                <td>{entry.variants || "—"}</td>
                <td>
                  <button
                    type="button"
                    className="action danger"
                    onClick={() => void removeEntry(entry)}
                  >
                    Löschen<span className="visually-hidden">: {entry.term}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
