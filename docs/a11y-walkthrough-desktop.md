# NVDA-Walkthrough — Variant A (Desktop)

**Purpose:** manual screen-reader regression suite. Run before every release
and after any frontend change. This artifact gates Phase 1 sign-off (project
brief, Testing requirement) and stays a living checklist afterwards.

**Setup:** Windows 10/11, current NVDA (free, nvaccess.org), Firefox or
Chrome, app started via `python run.py`. Screen **turned off or ignored** —
every step must succeed by audio alone. Fill the Result column with
`PASS` / `FAIL` + note.

Conventions: `NVDA` = Insert (default). Browse/focus mode switches with
`NVDA+Space`.

## A. Orientation & structure

| # | Step | Expected | Result |
|---|------|----------|--------|
| A1 | Open `http://127.0.0.1:8710`, press `Ctrl+Home` | Page title "Lokal-STT – Deutsche Spracherkennung" is announced; document language is German (NVDA reads German text with German pronunciation) | |
| A2 | Press `Tab` once | "Zum Hauptinhalt springen – Link" is the first focusable element | |
| A3 | Activate the skip link with `Enter` | Focus moves into the main region (next `Tab` lands on main content, not the nav) | |
| A4 | Press `H` repeatedly in browse mode | Headings arrive in order: h1 app title → h2 section title → h2 "Einstellungen zur Vorlesefunktion" — no skipped levels | |
| A5 | Press `D` | Landmarks navigation reaches banner (header), navigation "Bereiche", main | |
| A6 | Walk the whole page with `Tab`/`Shift+Tab` | Every interactive element gets focus in a logical order; no keyboard trap; each announces role + accessible name in German | |

## B. Upload workflow (blind-only)

| # | Step | Expected | Result |
|---|------|----------|--------|
| B1 | `Ctrl+Alt+1` | "Bereich: Datei hochladen" announced; focus on the section heading | |
| B2 | `Tab` to the file field | Announced as "Audiodateien … Schaltfläche Durchsuchen" (native file input) — **no drag-and-drop needed** | |
| B3 | `Enter`, pick a `.wav` via the file dialog (keyboard only) | Back in the app: "Datei ausgewählt: \<name\>" announced automatically | |
| B4 | `Tab` through Fachvokabular/Schlüsselwörter, type into each | Labels announced; typed text echoed | |
| B5 | `Tab` to "Transkription starten", `Enter` | "Datei hochgeladen, Transkription gestartet." announced (assertive); focus context switches to Verlauf | |
| B6 | Submit again **without** a file | Error announced immediately; `Tab` back to the file input reads the error via `aria-describedby` | |

## C. Progress & export (blind-only)

| # | Step | Expected | Result |
|---|------|----------|--------|
| C1 | In "Verlauf & Export" while a job runs | Status is real text: "Wird transkribiert – NN %" (not a visual-only bar) | |
| C2 | Wait for completion without touching anything | "Transkription abgeschlossen: \<name\>" announced assertively + completion earcon (if enabled) | |
| C3 | `Tab` into the export group | Group announced as "Export für \<name\>"; six links: txt, srt, vtt, json, docx, zip — each names its format and file | |
| C4 | `Enter` on "Text (.txt)" | Browser download dialog/notification; file is retrievable | |
| C5 | `Tab` to "Löschen", `Enter` | "Auftrag \<name\> gelöscht." announced; item gone from list | |
| C6 | Job with an unsupported file (e.g. rename `.txt`→`.wav` of garbage) | Failure state announced with the specific German error text, not color-only | |

## D. Live recording (blind-only)

| # | Step | Expected | Result |
|---|------|----------|--------|
| D1 | `Ctrl+Alt+2`, then `Ctrl+Alt+R` | "Aufnahme gestartet" (assertive) + rising earcon; browser mic permission handled via keyboard | |
| D2 | Speak two short German sentences, pause between them | Committed sentences are read out **batched** (one announcement per sentence/pause, never word-by-word flooding) | |
| D3 | Check the mute setting: enable "Live-Transkript nicht automatisch vorlesen", record again | No transcript announcements during recording; completion cue still arrives at stop | |
| D4 | `Ctrl+Alt+R` to stop | "Aufnahme beendet …" announced + falling earcon; if saving was checked: hint that the full transcription continues in Verlauf | |
| D5 | Deny mic permission (browser settings), start recording | Specific error announced assertively ("Fehler: …"), error earcon, app returns to idle — no silent failure | |
| D6 | During recording, move NVDA focus elsewhere (e.g. settings) | State changes still perceivable (assertive region + earcons) | |

## E. Shortcuts & dialog

| # | Step | Expected | Result |
|---|------|----------|--------|
| E1 | `Ctrl+Alt+K` | Modal dialog announced with title "Tastenkürzel"; focus inside dialog | |
| E2 | Read the table in browse mode (`T`, then table nav `Ctrl+Alt+arrows`) | Proper table semantics: column headers "Tasten"/"Funktion" announced per cell; every core action listed | |
| E3 | `Escape` | Dialog closes; focus returns to the page | |

## F. Exported DOCX

| # | Step | Expected | Result |
|---|------|----------|--------|
| F1 | Open an exported `.docx` in Word with NVDA | Document language German (correct synthesizer); "Transkript" is a real Heading 1, "Inhalt" Heading 2 — navigable by heading commands | |

---

**Sign-off:** date, NVDA version, browser, tester — all A–F steps PASS.

> Status 2026-07-06: script authored and cross-checked against the
> implementation; automated `axe-core` gate passes on all views. The manual
> NVDA execution requires a human tester with audio output and is the
> remaining open item for Phase 1 sign-off (tracked at the phase gate).
