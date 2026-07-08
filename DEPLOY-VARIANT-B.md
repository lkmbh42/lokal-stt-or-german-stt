# Variant B — Team-Server: Deployment & Start, Schritt für Schritt

Mehrbenutzer-Server für ein kleines Team (~10 Personen) mit gemeinsamer
GPU/CPU: Login, Rollen, Kontingente, Auditprotokoll, Warteschlange. Läuft
komplett in Docker (nginx, API, Worker, Postgres, Redis). Diese Anleitung
führt von einem leeren Server bis zum ersten Transkript — inklusive
Offline-/Air-Gap-Weg.

---

## Teil 1 — Voraussetzungen

Auf dem **Server**:

| Software | Prüfen mit |
|---|---|
| Docker Engine + Compose-Plugin (bzw. Docker Desktop) | `docker compose version` |
| git (nur wenn direkt auf dem Server gebaut wird) | `git --version` |

Auf der **Build-Maschine** (kann derselbe Server sein, wenn er Internet hat):
zusätzlich Node.js ≥ 20 und Python ≥ 3.10 (für Frontend-Build und
Modell-Staging).

**GPU-Server:** zusätzlich NVIDIA-Treiber + `nvidia-container-toolkit`
installieren (`nvidia-smi` muss auf dem Host funktionieren).

---

## Teil 2 — Build vorbereiten (auf der Maschine mit Internet)

**Schritt 1 — Code holen:**

```bash
git clone <repo-url> lokal-stt && cd lokal-stt
```

**Schritt 2 — Web-Oberfläche bauen** (wird von nginx ausgeliefert):

```bash
cd apps/server/frontend
npm ci
npm run build
cd ../../..
```

**Schritt 3 — Modell bereitstellen** (landet als Volume im Container,
wird nie zur Laufzeit heruntergeladen):

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .\.venv\Scripts\activate
pip install huggingface_hub
python engine/scripts/download_model.py large-v3 --dest infra/models
```

Ergebnis: `infra/models/faster-whisper-large-v3/`.

**Schritt 4 — Konfiguration anlegen:**

```bash
cd infra
cp .env.example .env
```

`.env` im Editor öffnen und **mindestens** setzen:

```bash
STT_SECRET_KEY=            # erzeugen mit:  openssl rand -hex 32
POSTGRES_PASSWORD=         # frei wählen, sicher aufbewahren
STT_BOOTSTRAP_ADMIN_USERNAME=admin
STT_BOOTSTRAP_ADMIN_PASSWORD=   # Passwort des ersten Admin-Kontos (min. 10 Zeichen)
STT_ENGINE__MODEL=/models/faster-whisper-large-v3
STT_ENGINE__LOCAL_FILES_ONLY=true
```

**Genauigkeit:** `large-v3` liefert die beste Qualität und gehört auf einen
GPU-Server. Läuft der Server **ohne GPU**, stattdessen `large-v3-turbo`
verwenden (Schritt 3: `download_model.py large-v3-turbo`, dann
`STT_ENGINE__MODEL=/models/faster-whisper-large-v3-turbo`) — nahezu gleiche
deutsche Genauigkeit bei rund vierfacher Geschwindigkeit. Aufnahmen im
Browser werden immer als vollständige Datei mit diesem Modell transkribiert.

Optionale Regler (Standardwerte sind sinnvoll): `STT_HTTP_PORT` (Standard
8080), `STT_MAX_CONCURRENT_JOBS` (GPU-Slots, siehe Teil 5),
`STT_DEFAULT_DAILY_MINUTES` / `STT_DEFAULT_MONTHLY_MINUTES`
(Kontingent-Standard, 0 = unbegrenzt), `STT_MAX_UPLOAD_MB`.

**Schritt 5 — TLS einrichten (empfohlen):**

```bash
./tls/generate-self-signed.sh stt.firma.intern    # oder Zertifikat der internen CA als tls/cert.pem + tls/key.pem ablegen
cp nginx/tls.conf.example nginx/default.conf
```

Danach in `docker-compose.yml` beim Dienst `nginx` die zwei auskommentierten
Zeilen aktivieren (Port `8443:443` und Volume `./tls:/etc/nginx/tls:ro`).
Selbstsigniertes Zertifikat: `tls/cert.pem` auf den Client-Rechnern in den
Zertifikatsspeicher importieren, sonst warnt der Browser.

*(Ohne TLS läuft der Server über HTTP auf Port 8080 — nur in vertrauens-
würdigen internen Netzen vertretbar.)*

---

## Teil 3 — Starten

### Weg A: Server hat Internet (oder ist die Build-Maschine)

```bash
cd infra
docker compose up --build -d
```

### Weg B: Air-Gap (Server ohne Internet)

Auf der Build-Maschine zusätzlich:

```bash
cd infra
docker compose build
docker save lokal-stt-api lokal-stt-worker | gzip > lokal-stt-image.tar.gz
docker pull nginx:1.27-alpine postgres:16-alpine redis:7-alpine
docker save nginx:1.27-alpine postgres:16-alpine redis:7-alpine | gzip > lokal-stt-infra.tar.gz
```

Übertragen auf den Zielserver: beide `.tar.gz`, den kompletten Ordner
`infra/` (inkl. `models/`, `.env`, `tls/`) und
`apps/server/frontend/dist/`** (Pfad-Struktur beibehalten — nginx mountet
`../apps/server/frontend/dist`). Dann auf dem Zielserver:

```bash
docker load < lokal-stt-image.tar.gz
docker load < lokal-stt-infra.tar.gz
cd infra
docker compose up -d --no-build
```

Details und Prüfliste: [infra/PROVISIONING.md](infra/PROVISIONING.md).

### Startkontrolle (beide Wege)

```bash
docker compose ps                                  # 5 Dienste, postgres/redis "healthy"
curl http://localhost:8080/api/health              # {"status":"ok", ...}
# bzw. mit TLS: curl -k https://localhost:8443/api/health
```

Datenbank-Migrationen laufen beim API-Start automatisch; das Admin-Konto
aus `.env` wird beim allerersten Start angelegt.

---

## Teil 4 — Erste Schritte als Team

1. **Anmelden:** Browser → `http://<server>:8080` (bzw. `https://…:8443`),
   Login mit dem Bootstrap-Admin aus `.env`.
2. **Benutzer anlegen:** „Administration" → „Benutzerverwaltung" →
   Benutzername + Passwort (min. 10 Zeichen). Optional pro Benutzer ein
   Tages-Kontingent in Minuten setzen.
3. **Als Benutzer arbeiten:** anmelden → Audiodatei hochladen oder direkt
   aufnehmen → Warteschlangen-Position und geschätzte Wartezeit erscheinen
   als Text → nach Fertigstellung Export als txt/srt/vtt/json/docx/zip.
4. **Überwachen (Admin):** „Systemstatus" zeigt Warteschlange, gemessene
   Verarbeitungsgeschwindigkeit und Speicherverbrauch pro Benutzer; das
   „Auditprotokoll" zeigt Anmeldungen und alle Aufträge (CSV-Export).

### Diktatmodus (Satzzeichen ansagen)

Setzen Sie vor Aufnahme/Upload das Häkchen **„Diktatmodus"**, um Satzzeichen
mitzusprechen — die einzige Möglichkeit, Zeichen zu erhalten, die Whisper
nicht hören kann (Klammern, Doppelpunkt, Semikolon, Gedankenstrich,
Anführungszeichen). Sagen Sie die Befehlswörter im Text mit:

`Komma` → , · `Punkt` → . · `Fragezeichen` → ? · `Ausrufezeichen` → ! ·
`Doppelpunkt` → : · `Semikolon` → ; · `Klammer auf/zu` → ( ) ·
`Anführungszeichen auf/zu` → „ " · `Gedankenstrich` → – · `neue Zeile`.

Nur die exakte Einzahlform ist ein Befehl, daher bleiben Inhaltswörter im
Plural erhalten: „…mit Doppelpunkt Kommas Semikolon Punkten" → „…mit:
Kommas; Punkten". Für normale Sprache ausgeschaltet lassen — dort setzt
Whisper die Basis-Satzzeichen selbst.

---

## Teil 5 — GPU aktivieren (empfohlen für large-v3)

1. In `docker-compose.yml` beim Dienst `worker` die Zeile `gpus: all`
   aktivieren (Kommentar entfernen).
2. In `.env`: `STT_ENGINE__DEVICE=cuda`.
3. `STT_MAX_CONCURRENT_JOBS` an den GPU-Speicher anpassen: large-v3 mit
   float16 braucht ≈ 4,7 GB pro parallelem Auftrag (24-GB-GPU ⇒ bis zu 4;
   konservativ mit 1–2 starten).
4. `docker compose up -d` — danach den Lasttest wiederholen
   ([docs/load-test-phase3.md](docs/load-test-phase3.md)) und die gemessenen
   Werte dokumentieren.

---

## Teil 6 — Betrieb: die wichtigsten Handgriffe

```bash
docker compose logs -f api worker      # Logs verfolgen
docker compose restart worker          # z. B. nach Modellwechsel
docker compose down                    # stoppen (Daten bleiben in Volumes)
docker compose up -d                   # wieder starten
```

- **Backup:** drei Orte — Postgres-Dump, `stt-data`-Volume (Audio +
  Transkripte), `infra/.env` + `infra/tls/`. Befehle:
  [infra/PROVISIONING.md §5](infra/PROVISIONING.md).
- **Update einspielen / Modell wechseln:**
  [docs/runbook-server.md](docs/runbook-server.md) und
  [docs/model-management.md](docs/model-management.md).

## Wenn etwas nicht funktioniert

| Problem | Lösung |
|---|---|
| Aufträge bleiben „In Warteschlange" | `docker compose logs worker` — meist stimmt `STT_ENGINE__MODEL` nicht oder `infra/models/` fehlt |
| API startet nicht, Log nennt `secret_key` | `STT_SECRET_KEY` in `.env` fehlt — absichtlich Pflichtfeld |
| Port 8080 schon belegt | `STT_HTTP_PORT=<anderer Port>` in `.env`, dann `docker compose up -d` |
| 429 „Zu viele Anmeldeversuche" | Schutzmechanismus; kurz warten oder `STT_AUTH_RATE_LIMIT_ATTEMPTS` erhöhen (z. B. hinter Firmen-NAT) |
| Browser warnt vor dem Zertifikat | Selbstsigniertes `tls/cert.pem` auf den Clients importieren oder Zertifikat der internen CA verwenden |
| Upload schlägt mit „Kontingent erschöpft" fehl | Gewollt: Tages-/Monatslimit erreicht — Admin kann es pro Benutzer anpassen |
