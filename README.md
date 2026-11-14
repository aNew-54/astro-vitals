# ASTRO-VITALS

Proyecto para **NASA Space Apps Cajamarca**. ASTRO-VITALS ayuda a un tripulante a interpretar cambios en sus signos vitales teniendo en cuenta su actividad, su línea base personal, la calidad de los sensores y el entorno de cabina o radiación, funcionando **de forma autónoma a bordo** sin depender de latencia con la Tierra.

> **Aviso de alcance:** Toda evaluación es **orientativa y no clínica** (*"Hipótesis orientativa (escenario simulado): ..."*). Cuando faltan canales o hay cortes de telemetría, el sistema conserva `null`/`None` y se abstiene de evaluar; nunca rellena ausencias con cero.

## Estado del proyecto (v0.2 · consola web + motor IA + SQLite)

**Disponible hoy en `main`:**

- **Motor a bordo ([`prototype/astro/engine.py`](prototype/astro/engine.py)):**
  - Calibración de **línea base personal fija** (`mediana` y `MAD`) durante reposo estable y detección sostenida de elevación fuera de ejercicio.
  - **Sensibilidad personal al CO₂ (`OLS`)** en ventanas de hasta 5 minutos y **proyección de tiempo hasta límite (`ETA`)** sobre pendiente de 120 s (usando como única referencia NASA `3.0 mmHg` promedio de 1 h, NASA OCHMO-TB-004, con nota histórica de cefalea desde `2.3 mmHg`).
  - **Proyección de dosis de radiación a 1 h** comparando exposición sin refugio vs. con refugio activado (`shelter_factor = 0.35`), integrada por trapecio solo en intervalos continuos válidos ($\le 5\text{ s}$).
  - **Perfiles de entorno simulado:** `station` (Estación Orbital), `transit` (Tránsito / Nave), `rover` (Rover / EVA) y `base` (Hábitat Lunar/Base).
  - **Contexto solar histórico NASA DONKI:** evento `2024-05-11T04:07:00-SEP-001` dividido en 4 fases (`watch`, `arrival`, `peak`, `decay`), evaluado de forma independiente al pulso.
- **Modelos de IA integrados ([`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/)):**
  - **Pronóstico FC +60 s** (`RandomForestRegressor`, `heart_rate_forecast/colab-v1`) con banda de incertidumbre y respaldo por persistencia mientras calibra.
  - **Clasificador de patrones** (`RandomForestClassifier`, `physiological_patterns/colab-v1`) sobre ventanas de 30 s y 120 s con abstención automática ante baja cobertura ($< 80\%$), datos antiguos ($> 5\text{ s}$), fuente `bidmc` o confianza $< 0.60$.
- **Consola Web + API + WebSocket ([`prototype/web/`](prototype/web/index.html)):**
  - Panel en vivo por **REST + WebSocket (`WS /telemetry`)** respaldado en **SQLite** (`logs/astro_vitals.db`), con gráficas en tiempo real, escáner corporal de 7 zonas, banco de escenarios, check-in conductual con **minijuego de reacción**, Coach de rutinas por participación, filtro de privacidad (`share_behavioral=False` por defecto) e informe **SBAR** descargable en Markdown.
- **Adaptador universal de archivos ([`prototype/astro/adapters/`](prototype/astro/adapters/loader.py)):**
  - Ingesta y conversión explícita de registros `.csv`, `.tsv`, `.json` y `.jsonl` (p. ej. `ppm` → `mmHg` con presión total conocida, `kPa` → `mmHg`, `mSv/h` → `μSv/h`, rechazando unidades incompatibles como `Gy`).

![Consola del prototipo durante un cambio simulado de cabina](prototype/previews/consola-cabina.png)

## Guía rápida para probar esta versión

### 1. Requisitos e instalación

Se recomienda **Python 3.12 o 3.13** (compatible con `scikit-learn` y `joblib` incluidos en `prototype/requirements.txt`).

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

*(Si usas `uv`, puedes crear el entorno en segundos con `uv venv --python 3.13 prototype/.venv && uv pip install --python prototype/.venv/bin/python -r prototype/requirements.txt`.)*

### 2. Lanzar la Consola Web (recomendado)

**macOS / Linux:**

```zsh
prototype/.venv/bin/python prototype/run.py --web
```

**Windows (PowerShell):**

```powershell
prototype\.venv\Scripts\python.exe prototype\run.py --web
```

Luego abre en el navegador: **`http://127.0.0.1:8000/`** (también disponible en `/ui/`).

- En el pie de página debe aparecer **`API: EN LÍNEA`** en verde y el indicador **`● ENLACE ACTIVO`** (streaming cada 1 s vía `WS /telemetry`).
- Desde el panel **`ENTRADA DE TELEMETRÍA`** puedes probar en vivo:
  - `REPOSO` / `EJERCICIO` (comparar predicción FC +60 s vs. persistencia).
  - `RAMPA CO₂` (tras $\ge 24$ muestras con variación $\ge 0.40\text{ mmHg}$ verás activarse la sensibilidad personal `OLS` y el `ETA`).
  - `TORMENTA DONKI` + `REFUGIO (SHELTER)` (fases solares y reducción de dosis al 35 %).
  - `PÉRDIDA SEÑAL` / `BIDMC REAL` (muestra `SIN SEÑAL` / `--` y abstención explícita de la IA sin rellenar con ceros).
- En la barra lateral izquierda (**`BIENESTAR`** y **`MONITOR`**): prueba el **minijuego de reacción de 6 intentos**, completa rutinas del Coach, cambia el switch de **privacidad conductual** y descarga el **informe SBAR (`.md`)**.

### 3. Otras formas de ejecución

```zsh
# Arrancar con perfil inicial específico (station | transit | rover | base)
prototype/.venv/bin/python prototype/run.py --web --environment rover

# Abrir en modo consola de terminal (Textual TUI)
prototype/.venv/bin/python prototype/run.py --tui

# Reproducir un archivo propio (.csv, .tsv, .json, .jsonl) al iniciar
prototype/.venv/bin/python prototype/run.py --web --replay ruta/al/registro.csv
```

### 4. Conectar un emisor Python externo (sensores de traje simulados)

Mientras `run.py --web` esté activo, puedes pausar el generador interno y enviar paquetes desde cualquier aplicación Python hacia `POST http://127.0.0.1:8000/api/v1/telemetry` con `source="measured"`:

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

### 5. Ejecutar las pruebas de verificación (50 tests)

```zsh
PYTHONPATH=prototype prototype/.venv/bin/pytest prototype/tests/ -v
```

---

## Arquitectura y stack tecnológico

| Componente | Tecnología | Ubicación |
| --- | --- | --- |
| API a bordo + puente Web/WS | Python, FastAPI, Pydantic, Uvicorn, `websockets` | [`prototype/astro/api.py`](prototype/astro/api.py), [`web_bridge.py`](prototype/astro/web_bridge.py) |
| Motor fisiológico y ambiental | Calibración `MAD`, OLS CO₂, trapecio radiación, DONKI | [`prototype/astro/engine.py`](prototype/astro/engine.py), [`donki.py`](prototype/astro/donki.py) |
| Modelos de IA locales | `scikit-learn` (`RandomForest`), `joblib`, NumPy | [`prototype/astro/ml_models.py`](prototype/astro/ml_models.py), [`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/) |
| Persistencia local | SQLite (`sqlite3`, preservando `NULL` estrictos) | [`prototype/astro/storage.py`](prototype/astro/storage.py) |
| Consola Web | HTML5, CSS3, JS vanilla + Canvas ECG + WebSocket | [`prototype/web/`](prototype/web/index.html) |
| Consola Terminal (TUI) | Textual + HTTPX | [`prototype/astro/tui.py`](prototype/astro/tui.py) |
| Pruebas automatizadas | `pytest` (50 pruebas: unitarias, contratos, ML, E2E) | [`prototype/tests/`](prototype/tests/) |

## Datos preparados y modelos entrenados

| Modelo / Dataset | Detalle |
| --- | --- |
| **Pronóstico FC +60 s** | `RandomForestRegressor` entrenado sobre ventanas reales de [BIDMC](data/bidmc/README.md) (`14` características de ventanas 30 s / 120 s). |
| **Clasificación de patrones** | `RandomForestClassifier` entrenado sobre [cohorte sintética](data/fusion_simulada/README.md) (`25` características, 4 clases, umbral de abstención `0.60`). |
| [PPG-DaLiA](data/ppg_dalia/README.md) | 11.693 ventanas de actividad terrestre. |
| [WESAD](data/wesad/README.md) | 1.060 ventanas de condición basal y estrés. |
| [MMASH](data/mmash/README.md) | 22 episodios de sueño de 21 participantes. |
| [NASA EDA · RR-1](data/iss_rr1/README.md) | 12.087 lecturas de cabina ISS y 39 registros diarios de radiación ambiental. |
| [NASA DONKI](data/donki/README.md) | Evento solar histórico `2024-05-11T04:07:00-SEP-001` usado para contexto por fases. |

[Guía detallada del prototipo](prototype/README.md) · [Contrato de datos](CONTRATO_DE_DATOS.md) · [Alcance del MVP](MVP_ASTRO_VITALS.md) · [Arquitectura técnica](ARQUITECTURA_TECNICA.md)
