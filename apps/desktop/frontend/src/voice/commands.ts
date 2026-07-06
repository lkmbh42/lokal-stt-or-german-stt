/**
 * Fixed German command grammar for voice-controlled UI navigation.
 *
 * Deliberately small and closed (project brief: "restricted to a small
 * fixed command grammar for reliability"): free-form phrases are ignored,
 * only listed triggers fire. Recording start/stop is intentionally NOT
 * voice-controllable — the microphone belongs to the recording session
 * then, and two concurrent capture pipelines are a reliability trap.
 */

export type VoiceAction =
  | "open-upload"
  | "open-record"
  | "open-jobs"
  | "open-shortcuts"
  | "read-status"
  | "stop-voice-control";

interface Command {
  action: VoiceAction;
  /** announced label, e.g. in the shortcuts dialog */
  label: string;
  triggers: string[];
}

export const COMMANDS: Command[] = [
  {
    action: "open-upload",
    label: "„Bereich hochladen“ — Datei-Upload öffnen",
    triggers: ["bereich hochladen", "hochladen offnen", "datei hochladen"],
  },
  {
    action: "open-record",
    label: "„Bereich Aufnahme“ — Aufnahmebereich öffnen",
    triggers: ["bereich aufnahme", "aufnahme offnen"],
  },
  {
    action: "open-jobs",
    label: "„Bereich Verlauf“ — Verlauf und Export öffnen",
    triggers: ["bereich verlauf", "verlauf offnen", "export offnen"],
  },
  {
    action: "open-shortcuts",
    label: "„Tastenkürzel anzeigen“ — Hilfe-Dialog öffnen",
    triggers: ["tastenkurzel anzeigen", "hilfe anzeigen", "zeige hilfe"],
  },
  {
    action: "read-status",
    label: "„Status vorlesen“ — aktuellen Zustand ansagen",
    triggers: ["status vorlesen", "lies den status"],
  },
  {
    action: "stop-voice-control",
    label: "„Sprachsteuerung beenden“ — Sprachmodus ausschalten",
    triggers: ["sprachsteuerung beenden", "sprachsteuerung aus", "steuerung beenden"],
  },
];

/** lowercase, fold umlauts/ß, strip punctuation, collapse whitespace —
 * makes matching robust against ASR spelling variance ("Tastenkürzel" vs
 * "Tastenkuerzel") */
export function normalizeUtterance(text: string): string {
  return text
    .toLowerCase()
    .replace(/ä/g, "a")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .replace(/ß/g, "ss")
    .replace(/ae/g, "a")
    .replace(/oe/g, "o")
    .replace(/ue/g, "u")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Match one recognized utterance against the grammar. Trigger phrases must
 * appear as a whole-word sequence inside the utterance. Both sides run
 * through the same normalization so the folding rules stay symmetric. */
export function matchCommand(utterance: string): VoiceAction | null {
  const normalized = ` ${normalizeUtterance(utterance)} `;
  for (const command of COMMANDS) {
    for (const trigger of command.triggers) {
      if (normalized.includes(` ${normalizeUtterance(trigger)} `)) {
        return command.action;
      }
    }
  }
  return null;
}
