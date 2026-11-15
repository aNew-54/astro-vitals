# ASTRO-VITALS · Prototype Guide (`prototype/`)

Local architecture consisting of independent processes connected through a local network:

**Gateway / External Source (`8002` or custom emitter) → Onboard API + AI Engine + SQLite (`8000`) → Web Console (`/` + `WS /telemetry`) or Textual TUI.**

## Quick Installation and Execution

From `astro-vitals/prototype/`:

```zsh
# Create a virtual environment with Python 3.12 / 3.13 and install dependencies
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Start with the Web Console at http://127.0.0.1:8000/
.venv/bin/python run.py --web
```

On Windows (PowerShell):

```powershell
python -m venv .venv
.\\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\\.venv\Scripts\python.exe run.py --web
```

### `run.py` Options

| Flag | Description |
| --- | --- |
| `--web` | Starts the API (`8000`) + gateway (`8002`), prints the URL, and opens the Web Console |
| `--tui` | Starts the interactive terminal console (`Textual`, default mode) |
| `--services-only` | Keeps both HTTP/WS services running without opening an interface |
| `--environment {station,transit,rover,base}` | Selects the initial simulated environment profile |
| `--replay <path>` | Converts a `.csv`, `.tsv`, `.json`, or `.jsonl` file, pauses the gateway, and ingests the samples |
| `--onboard-port <port>` | API and Web Console port (default: `8000`) |
| `--gateway-port <port>` | Simulated gateway port (default: `8002`) |

The local SQLite database is stored by default at `prototype/logs/astro_vitals.db` (configurable through `ASTRO_DB_PATH`).

---

## What to Test in the Web Console (`http://127.0.0.1:8000/`)

### `TELEMETRY INPUT` Panel (`/api/control`)

| Control | What It Demonstrates in Real Time |
| --- | --- |
| `REST` | Baseline state and fixed baseline calibration (`median`/`MAD`) |
| `EXERCISE` | Expected physiological response vs. +60 s HR forecast (`RandomForestRegressor`) |
| `CABIN CO₂` | Direct increase in ppCO₂ and respiration; triggers a non-clinical combined hypothesis |
| `CO₂ RAMP` | Progressive increase according to the profile; after $\ge 24$ samples ($\Delta\text{CO}\_2 \ge 0.40\text{ mmHg}$), activates **OLS sensitivity regression** and **time-to-limit estimation (ETA)** |
| `DONKI STORM` | Historical solar event `2024-05-11T04:07:00-SEP-001` displayed in phases (`watch` → `arrival` → `peak` → `decay`) |
| `SHELTER` | Reduces the simulated dose rate (`shelter_factor = 0.35`) and compares the 1-hour dose projection with and without shelter |
| `SIGNAL LOSS` | Sets biometric channels to `null`; displays `NO SIGNAL` / `--` and explicit abstention |
| `REAL BIDMC` | Replays `data/bidmc_01_Numerics.csv` (1 Hz), preserving `co2` and `dose_rate` as `null` without fabricating space-related data |
| `ENVIRONMENT` | Changes habitat thresholds and radiation multiplier (`station`, `transit`, `rover`, `base`) |
| `ACKNOWLEDGE (ACK)` | Records acknowledgment of an active alert (`+5 pts`) without resolving the underlying condition |

### Module Sidebar (`MODULES`)

- **`MONITOR` / `ALERTS`:** Complete metrics, ML classifier explanation, pulse prediction interval, CO₂/dose projections, and SBAR report viewing/downloading (`.md`).
- **`WELLNESS`:**
  - **Six-attempt psychomotor mini-game:** Sends `/api/v1/checkin` with median reaction time in ms, false starts, lapses $> 500\text{ ms}$, sleep, and mood.
  - **Engagement Coach:** Preventive routines (`+10 pts` per routine, `+15 pts` per check-in, `+5 pts` per ACK); points and badges reward participation only.
  - **Privacy Toggle:** By default, `share_behavioral=False` hides sleep, mood, and reaction data from the external SBAR report.
- **`HISTORY` / `PROFILE` / `SETTINGS`:** Time series from SQLite, `ASTRA-001` profile, and visual/audio settings.

---

## Independent Processes and Endpoints

To run each service in its own terminal from `prototype/`:

```zsh
# Terminal 1: Onboard API + Web Console + WebSocket
.venv/bin/python -m uvicorn astro.api:app --host 127.0.0.1 --port 8000

# Terminal 2: Simulated Gateway / BIDMC Player
.venv/bin/python -m uvicorn astro.gateway:app --host 127.0.0.1 --port 8002

# Terminal 3 (optional): Terminal TUI
.venv/bin/python -m astro.tui
```

### API Available on `:8000`

- **Engine and Domain (`/api/v1/*`):**
  - `GET /health` · `GET /docs`
  - `POST /api/v1/telemetry` · `GET /api/v1/state` · `GET /api/v1/trends` · `GET /api/v1/glossary`
  - `POST /api/v1/ack` · `POST /api/v1/checkin`
  - `GET /api/v1/routines` · `POST /api/v1/routines/{routine_id}/done`
  - `POST /api/v1/context/activity` · `POST /api/v1/context/event` · `POST /api/v1/context/environment`
  - `POST /api/v1/privacy` · `GET /api/v1/report`
- **SQLite and Web Bridge (`/api/*` + WebSocket):**
  - `GET/POST /api/astronauts/` · `GET /api/astronauts/{id}`
  - `GET/POST /api/measurements/` · `GET /api/measurements/latest`
  - `GET/POST /api/alerts/` · `PATCH /api/alerts/{id}/ack`
  - `GET/POST /api/logs/` · `GET/POST /api/insights/`
  - `GET/POST /api/control` · `WS /telemetry`

---

## Automated Verification

From `astro-vitals/prototype/`:

```zsh
# Run all 50 tests (backend, gateway, domain, ML, coach/SBAR, adapters, WebBridge, and E2E)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Check Web Console JavaScript syntax
for f in web/js/*.js; do node --check "$f" || exit 1; done
```

Command-line file adapter (`csv`, `tsv`, `json`, `jsonl`):

```zsh
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader inspect path/to/file.csv
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader convert path/to/file.csv --output-dir logs/replay
```