import { useEffect, useRef } from "react";

import { COMMANDS } from "../voice/commands";

const SHORTCUTS: Array<{ keys: string; action: string }> = [
  { keys: "Strg + Alt + 1", action: "Bereich „Datei hochladen“ öffnen" },
  { keys: "Strg + Alt + 2", action: "Bereich „Aufnahme“ öffnen" },
  { keys: "Strg + Alt + 3", action: "Bereich „Verlauf & Export“ öffnen" },
  { keys: "Strg + Alt + R", action: "Aufnahme starten / stoppen" },
  { keys: "Strg + Alt + K", action: "Diese Tastenkürzel-Übersicht öffnen" },
  { keys: "Escape", action: "Dialog schließen" },
  { keys: "Tab / Umschalt + Tab", action: "Zwischen Bedienelementen wechseln" },
];

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={dialogRef} onClose={onClose} aria-labelledby="shortcuts-heading">
      <h2 id="shortcuts-heading">Tastenkürzel</h2>
      <table className="shortcuts">
        <caption className="visually-hidden">
          Alle Tastenkürzel der Anwendung mit ihrer Funktion
        </caption>
        <thead>
          <tr>
            <th scope="col">Tasten</th>
            <th scope="col">Funktion</th>
          </tr>
        </thead>
        <tbody>
          {SHORTCUTS.map((shortcut) => (
            <tr key={shortcut.keys}>
              <td>
                <kbd>{shortcut.keys}</kbd>
              </td>
              <td>{shortcut.action}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Alle Funktionen sind auch ohne Tastenkürzel per <kbd>Tab</kbd>-Navigation erreichbar.
      </p>
      <h3 id="voice-commands-heading">Sprachbefehle</h3>
      <p>
        Nach dem Aktivieren der Sprachsteuerung (Schaltfläche in der Navigation)
        stehen folgende Befehle zur Verfügung:
      </p>
      <ul aria-labelledby="voice-commands-heading">
        {COMMANDS.map((command) => (
          <li key={command.action}>{command.label}</li>
        ))}
      </ul>
      <p>
        Während einer Audio-Aufnahme ist die Sprachsteuerung pausiert (das
        Mikrofon gehört dann der Aufnahme).
      </p>
      <button type="button" className="action" onClick={onClose}>
        Schließen
      </button>
    </dialog>
  );
}
