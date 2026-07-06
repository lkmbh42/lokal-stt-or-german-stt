# Variant A — Desktop-Tool: Deployment & Start, Schritt für Schritt

Single-User-Tool: ein Rechner, eine Person, kein Login, läuft nur auf
`127.0.0.1`. Diese Anleitung führt von einem leeren Rechner bis zur laufenden
Anwendung.

---

## Teil 1 — Voraussetzungen installieren (einmalig)

Benötigt wird:

| Software | Version | Prüfen mit |
|---|---|---|
| Python | ≥ 3.10 | `python --version` |
| Node.js | ≥ 20 (nur zum Bauen der Oberfläche) | `node --version` |
| ffmpeg | beliebig aktuell, auf dem PATH | `ffmpeg -version` |
| git | beliebig | `git --version` |

**Windows zusätzlich:** Microsoft Visual C++ Redistributable x64
(ohne dieses lädt die Inferenz-Bibliothek nicht):

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

ffmpeg unter Windows z. B.: `winget install Gyan.FFmpeg` (danach neues
Terminal öffnen, damit der PATH greift).

Linux (Debian/Ubuntu): `sudo apt install python3-venv nodejs npm ffmpeg git`

---

## Teil 2 — Projekt holen und installieren (einmalig)

Alle Befehle im Projektstamm ausführen. Windows-Beispiele mit PowerShell;
Linux/macOS-Abweichungen stehen jeweils dabei.

**Schritt 1 — Code holen:**

```powershell
git clone <repo-url> lokal-stt
cd lokal-stt
```

**Schritt 2 — Python-Umgebung anlegen und aktivieren:**

```powershell
python -m venv .venv
.\.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
```

(Die Aktivierung erkennt man am `(.venv)` vor dem Prompt.)

**Schritt 3 — Backend-Pakete installieren** (Engine + Desktop-App, dauert
einige Minuten, lädt u. a. faster-whisper):

```powershell
pip install -e ./engine -e ./apps/desktop/backend
```

**Schritt 4 — Oberfläche bauen** (einmalig; Node wird danach zur Laufzeit
nicht mehr gebraucht):

```powershell
cd apps\desktop\frontend
npm ci
npm run build
cd ..\..\..
```

**Schritt 5 — Konfiguration anlegen:**

```powershell
copy apps\desktop\config.example.yaml apps\desktop\config.yaml
```

Dann `apps\desktop\config.yaml` in einem Editor öffnen und das Modell
wählen:

```yaml
engine:
  model: large-v3     # beste Qualität, ~3 GB Download beim ersten Auftrag
  # model: small      # guter Kompromiss auf CPU-Rechnern
  # model: base       # schnellster Test-Modus
  device: auto        # nutzt CUDA-GPU falls vorhanden, sonst CPU
```

**Schritt 6 (nur für Rechner ohne Internet / Air-Gap):** Modell auf einem
Rechner *mit* Internet vorab herunterladen und rüberkopieren:

```powershell
python engine\scripts\download_model.py large-v3 --dest models
```

Ordner `models\faster-whisper-large-v3` auf den Zielrechner übertragen und
in `config.yaml` eintragen:

```yaml
engine:
  model: ./models/faster-whisper-large-v3
  local_files_only: true    # verhindert jeden Download-Versuch
```

---

## Teil 3 — Starten und benutzen

**Starten:**

```powershell
cd apps\desktop
..\..\.venv\Scripts\python.exe run.py --config config.yaml
```

Der Standardbrowser öffnet sich automatisch mit `http://127.0.0.1:8710`.
(Öffnet er sich nicht: Adresse manuell eingeben.)

**Benutzen:**

1. **Datei hochladen** — Audiodatei(en) wählen (mp3/wav/m4a/mp4/flac),
   optional Fachbegriffe eintragen, „Transkription starten". Fortschritt
   erscheint im Bereich „Verlauf & Export".
2. **Aufnahme** — „Aufnahme starten" (oder `Strg+Alt+R`), Mikrofonzugriff
   erlauben, sprechen. Text erscheint live; nach dem Stoppen wird die
   Aufnahme in voller Qualität transkribiert.
3. **Verlauf & Export** — fertige Transkripte als txt/srt/vtt/json/docx oder
   komplett als zip herunterladen.
4. `Strg+Alt+K` zeigt alle Tastenkürzel und Sprachbefehle;
   „Sprachsteuerung starten" aktiviert die Bedienung per Sprachbefehl.

**Beenden:** `Strg+C` im Terminal. Alle Daten (Verlauf, Transkripte) liegen
in `apps\desktop\data\` und sind beim nächsten Start wieder da.

**Nützliche Startvarianten:**

```powershell
python run.py --config config.yaml --port 0          # freien Port wählen
python run.py --config config.yaml --no-browser      # ohne Browser-Start
python run.py --config config.yaml -v                # ausführliche Logs
```

---

## Teil 4 — Aktualisieren

```powershell
git pull
.\.venv\Scripts\activate
pip install -e ./engine -e ./apps/desktop/backend
cd apps\desktop\frontend && npm ci && npm run build
```

Verlauf und Konfiguration bleiben erhalten.

---

## Wenn etwas nicht funktioniert

| Problem | Lösung |
|---|---|
| `Could not find module ... ctranslate2.dll` (Windows) | VC++ Redistributable installieren (Teil 1) |
| Meldung „PyAV decoding unavailable … falling back to ffmpeg" | Normal auf abgesicherten Windows-Rechnern — ffmpeg muss auf dem PATH sein |
| `Port already in use` | `--port 0` verwenden oder `port:` in config.yaml ändern |
| Erster Auftrag dauert lange | Das Modell wird beim ersten Auftrag geladen (bei large-v3 zusätzlich einmalig heruntergeladen, sofern nicht vorab bereitgestellt) |
| Browser zeigt nur JSON unter `/` | Oberfläche nicht gebaut — Teil 2, Schritt 4 nachholen |
| Mikrofon geht nicht | Browser-Berechtigung prüfen; aktueller Browser nötig |

Weiterführend: [docs/runbook-desktop.md](docs/runbook-desktop.md) (Betrieb),
[docs/model-management.md](docs/model-management.md) (Modellwechsel),
[apps/desktop/README.md](apps/desktop/README.md) (Architektur).
