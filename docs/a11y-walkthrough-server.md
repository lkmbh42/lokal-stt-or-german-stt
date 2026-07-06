# NVDA-Walkthrough — Variant B (Team Server)

Manual screen-reader regression suite for the multi-user frontend, same bar
as the desktop walkthrough. Scope per project brief: **login → submit job →
check queue → retrieve transcript**, plus the admin panel. Run with NVDA on
Firefox/Chrome against a running stack; every step by audio alone. Fill
Result with `PASS`/`FAIL` + note.

## A. Login

| # | Step | Expected | Result |
|---|------|----------|--------|
| A1 | Open the server URL | Title "Lokal-STT Team – Deutsche Spracherkennung"; German pronunciation (page lang=de) | |
| A2 | `Tab` through the form | "Benutzername – Eingabefeld", "Passwort – Eingabefeld (geschützt)", "Anmelden – Schaltfläche"; labels announced | |
| A3 | Submit wrong credentials | Generic error announced assertively; `Tab` back to the fields reads the error via `aria-describedby`; no username-vs-password hint | |
| A4 | Submit valid credentials | "Anmeldung erfolgreich." announced; focus lands on the "Meine Transkriptionen" heading | |

## B. Submit a job & watch the queue

| # | Step | Expected | Result |
|---|------|----------|--------|
| B1 | `Tab` to "Audiodateien" | Native file input (no drag-and-drop required); pick a German WAV via keyboard | |
| B2 | Activate "Transkription starten" | Announcement includes the **queue status as text**: "… eingereicht. Position N in der Warteschlange, voraussichtlich M Minuten." | |
| B3 | Wait without touching anything | Status transitions are announced: "Transkription gestartet: \<name\>" (polite), then "Transkription abgeschlossen: \<name\>" (assertive) | |
| B4 | Read the job entry in the Verlauf list | Status is text ("Position …", "Wird transkribiert – NN %", "Fertig") — never a visual-only indicator | |
| B5 | Check the quota line (if limits configured) | "Kontingent: heute X von Y Minuten verwendet." readable as plain text | |
| B6 | Exceed the quota (test account with tiny limit) | Upload rejected; specific German quota error announced assertively | |

## C. Retrieve the transcript

| # | Step | Expected | Result |
|---|------|----------|--------|
| C1 | `Tab` into the export group of a finished job | Group announced "Export für \<name\>"; buttons name format **and** file | |
| C2 | Activate "Text (.txt)" | Download starts; "Download gestartet: \<name\>.txt" announced | |
| C3 | Activate "Alle (.zip)" | Zip downloads with all five formats | |

## D. Recording (record-and-upload)

| # | Step | Expected | Result |
|---|------|----------|--------|
| D1 | Activate "Aufnahme starten" | "Aufnahme gestartet" assertive; mic permission flow keyboard-operable | |
| D2 | Speak, then "Aufnahme stoppen und hochladen" | "Aufnahme beendet, wird hochgeladen …" then the submit announcement with queue position | |

## E. Admin panel (admin account)

| # | Step | Expected | Result |
|---|------|----------|--------|
| E1 | Nav shows "Administration" only for admins | Regular account: button absent | |
| E2 | Systemstatus | Queue/model/speed readable as one sentence; per-user usage table has proper column headers | |
| E3 | Create a user via the form | Labels announced; success announced assertively | |
| E4 | Deactivate a user / set a quota | Action buttons name their target user (visually hidden text); result announced | |
| E5 | Auditprotokoll | Filter select labeled; table navigable with column headers (Zeitpunkt/Benutzer/Aktion/Details) | |
| E6 | "Als CSV exportieren" | Download announced and delivered | |

## F. Structure (both roles)

| # | Step | Expected | Result |
|---|------|----------|--------|
| F1 | First `Tab` on any page | Skip link "Zum Hauptinhalt springen" | |
| F2 | `H` through headings | h1 (app) → h2 (section) → h3 (subsections), no skipped levels | |
| F3 | Full `Tab` cycle | No keyboard trap; visible focus everywhere; logical order | |

---

**Sign-off:** date, NVDA version, browser, tester — all A–F steps PASS.

> Status 2026-07-06: script authored against the implementation; automated
> axe-core gate passes on login/jobs/admin views. Manual NVDA execution by a
> human tester remains the open sign-off item (same as Phase 1).
