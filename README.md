# ASTRO-VITALS

A project for **NASA Space Apps Cajamarca**. ASTRO-VITALS helps a crew member interpret changes in their vital signs, taking into account their activity, their personal baseline, sensor quality and the cabin or radiation environment, working **autonomously on board** without depending on latency with Earth.

> **Scope notice:** Every assessment is **indicative and non-clinical** (*"Indicative hypothesis (simulated scenario): ..."*). When channels are missing or telemetry drops out, the system keeps `null`/`None` and abstains from assessing; it never fills gaps with zero.

## Project status (v0.2 · web console + AI engine + SQLite)

**Available today on `main`:**

- **On-board engine ([`prototype/astro/engine.py`](prototype/astro/engine.py)):**
  - Calibration of a **fixed personal baseline** (`median` and `MAD`) during stable rest, and sustained detection of elevation outside exercise.
  - **Personal CO₂ sensitivity (`OLS`)** over windows of up to 5 minutes and **time-to-limit projection (`ETA`)** on a 120 s slope (using as the only reference NASA `3.0 mmHg` 1 h average, NASA OCHMO-TB-004, with a historical note of headache from `2.3 mmHg`).
  - **1 h radiation dose projection** comparing exposure without shelter vs. with shelter activated (`shelter_factor = 0.35`), integrated by the trapezoidal rule only over valid continuous intervals ($\le 5\text{ s}$).
  - **Simulated environment profiles:** `station` (Orbital Station), `transit` (Transit / Spacecraft), `rover` (Rover / EVA) and `base` (Lunar Habitat/Base).
  - **Historical NASA DONKI solar context:** event `2024-05-11T04:07:00-SEP-001` divided into 4 phases (`watch`, `arrival`, `peak`, `decay`), evaluated independently of the pulse.
- **Integrated AI models ([`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/)):**
  - **HR +60 s forecast** (`RandomForestRegressor`, `heart_rate_forecast/colab-v1`) with an uncertainty band and persistence fallback while it calibrates.
  - **Pattern classifier** (`RandomForestClassifier`, `physiological_patterns/colab-v1`) on 30 s and 120 s windows with automatic abstention on low coverage ($< 80\%$), stale data ($> 5\text{ s}$), `bidmc` source or confidence $< 0.60$.
- **Web Console + API + WebSocket ([`prototype/web/`](prototype/web/index.html)):**
  - Live dashboard over **REST + WebSocket (`WS /telemetry`)** backed by **SQLite** (`logs/astro_vitals.db`), with real-time charts, a 7-zone body scanner, a scenario bank, a behavioral check-in with a **reaction mini-game**, a participation-based routines Coach, a privacy filter (`share_behavioral=False` by default) and a downloadable **SBAR** report in Markdown.
- **Universal file adapter ([`prototype/astro/adapters/`](prototype/astro/adapters/loader.py)):**
  - Ingestion and explicit conversion of `.csv`, `.tsv`, `.json` and `.jsonl` records (e.g. `ppm` → `mmHg` with known total pressure, `kPa` → `mmHg`, `mSv/h` → `μSv/h`, rejecting incompatible units such as `Gy`).

![Prototype console during a simulated cabin change](prototype/previews/consola-cabina.png)

## Quick guide to try this version

### 1. Requirements and installation

**Python 3.12 or 3.13** is recommended (compatible with `scikit-learn` and `joblib`, included in `prototype/requirements.txt`).

**macOS / Linux:**

```zsh
git clone https://github.com/aNew-54/astro-vitals.git
cd astro-vitals
python3.13 -m venv prototype/.venv
prototype/.venv/bin/pip install -r prototype/requirements.txt
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/aNew-54/astro-vitals.git
cd astro-vitals
python -m venv prototype\.venv
prototype\.venv\Scripts\python.exe -m pip install -r prototype\requirements.txt
```

*(If you use `uv`, you can create the environment in seconds with `uv venv --python 3.13 prototype/.venv && uv pip install --python prototype/.venv/bin/python -r prototype/requirements.txt`.)*

### 2. Launch the Web Console (recommended)

**macOS / Linux:**

```zsh
prototype/.venv/bin/python prototype/run.py --web
```

**Windows (PowerShell):**

```powershell
prototype\.venv\Scripts\python.exe prototype\run.py --web
```

Then open in the browser: **`http://127.0.0.1:8000/`** (also available at `/ui/`).

- The footer should show **`API: ONLINE`** in green and the **`● LINK ACTIVE`** indicator (streaming every 1 s via `WS /telemetry`).
- From the **`TELEMETRY INPUT`** panel you can test live:
  - `REST` / `EXERCISE` (compare HR +60 s prediction vs. persistence).
  - `CO₂ RAMP` (after $\ge 24$ samples with variation $\ge 0.40\text{ mmHg}$ you will see the personal `OLS` sensitivity and the `ETA` activate).
  - `DONKI STORM` + `SHELTER` (solar phases and dose reduction to 35 %).
  - `SIGNAL LOSS` / `REAL BIDMC` (shows `NO SIGNAL` / `--` and explicit AI abstention without filling with zeros).
- In the left sidebar (**`WELLBEING`** and **`MONITOR`**): try the **6-attempt reaction mini-game**, complete Coach routines, toggle the **behavioral privacy** switch and download the **SBAR report (`.md`)**.

### 3. Other ways to run

```zsh
# Start with a specific initial profile (station | transit | rover | base)
prototype/.venv/bin/python prototype/run.py --web --environment rover

# Open in terminal console mode (Textual TUI)
prototype/.venv/bin/python prototype/run.py --tui

# Replay your own file (.csv, .tsv, .json, .jsonl) at startup
prototype/.venv/bin/python prototype/run.py --web --replay path/to/record.csv
```

### 4. Connect an external Python emitter (simulated suit sensors)

While `run.py --web` is active, you can pause the internal generator and send packets from any Python application to `POST http://127.0.0.1:8000/api/v1/telemetry` with `source="measured"`:

```python
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx

API = "http://127.0.0.1:8000"
with httpx.Client(timeout=2.0) as client:
    client.post(f"{API}/api/control", json={"paused": True})
    for i in range(30):
        client.post(f"{API}/api/v1/telemetry", json={
            "sample_id": str(uuid4()),
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "crew_id": "ASTRA-001",
            "location_id": "suit-eva-01",
            "hr": 86.0 + i * 0.4,
            "rr": 18.0 + i * 0.1,
            "co2": 2.3 + i * 0.05,
            "dose_rate": 0.45,
            "spo2": 97.6,
            "bp_sys": 124.0,
            "bp_dia": 78.0,
            "temp_c": 37.0,
            "hydration_pct": 83.0,
            "activity": "exercise",
            "source": "measured",
        })
        time.sleep(1.0)
```

### 5. Run the verification tests (50 tests)

```zsh
PYTHONPATH=prototype prototype/.venv/bin/pytest prototype/tests/ -v
```

---

## Architecture and technology stack

| Component | Technology | Location |
| --- | --- | --- |
| On-board API + Web/WS bridge | Python, FastAPI, Pydantic, Uvicorn, `websockets` | [`prototype/astro/api.py`](prototype/astro/api.py), [`web_bridge.py`](prototype/astro/web_bridge.py) |
| Physiological and environmental engine | `MAD` calibration, CO₂ OLS, radiation trapezoid, DONKI | [`prototype/astro/engine.py`](prototype/astro/engine.py), [`donki.py`](prototype/astro/donki.py) |
| Local AI models | `scikit-learn` (`RandomForest`), `joblib`, NumPy | [`prototype/astro/ml_models.py`](prototype/astro/ml_models.py), [`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/) |
| Local persistence | SQLite (`sqlite3`, preserving strict `NULL`s) | [`prototype/astro/storage.py`](prototype/astro/storage.py) |
| Web Console | HTML5, CSS3, vanilla JS + ECG Canvas + WebSocket | [`prototype/web/`](prototype/web/index.html) |
| Terminal Console (TUI) | Textual + HTTPX | [`prototype/astro/tui.py`](prototype/astro/tui.py) |
| Automated tests | `pytest` (50 tests: unit, contracts, ML, E2E) | [`prototype/tests/`](prototype/tests/) |


## AI / Super Intelligence Use Disclosure
Our team used ChatGPT, Google Gemini, Claude, OpenCode, and GitHub Copilot to assist with code drafting, debugging, code review, and documentation. 
Generative AI was not used to create or alter project images, video, or audio. No NASA logos, flags, or mission identifiers were generated or modified using AI. Based on our project workflow, the datasets come from the sources identified in this project or from programmatic simulations; generative AI was not used to create the datasets. ASTRO-VITALS is a software prototype and does not include AI-generated visual or audio assets.AI-generated visual or audio assets.

## Prepared data and trained models

| Model / Dataset | Detail |
| --- | --- |
| **HR +60 s forecast** | `RandomForestRegressor` trained on real [BIDMC](data/bidmc/README.md) windows (`14` features from 30 s / 120 s windows). |
| **Pattern classification** | `RandomForestClassifier` trained on a [synthetic cohort](data/fusion_simulada/README.md) (`25` features, 4 classes, abstention threshold `0.60`). |
| [PPG-DaLiA](data/ppg_dalia/README.md) | 11,693 windows of land-based activity. |
| [WESAD](data/wesad/README.md) | 1,060 windows of baseline and stress conditions. |
| [MMASH](data/mmash/README.md) | 22 sleep episodes from 21 participants. |
| [NASA EDA · RR-1](data/iss_rr1/README.md) | 12,087 ISS cabin readings and 39 daily records of ambient radiation. |
| [NASA DONKI](data/donki/README.md) | Historical solar event `2024-05-11T04:07:00-SEP-001` used for phase-based context. |

[Detailed prototype guide](prototype/README.md) · [Data contract](CONTRATO_DE_DATOS.md) · [MVP scope](MVP_ASTRO_VITALS.md) · [Technical architecture](ARQUITECTURA_TECNICA.md)
