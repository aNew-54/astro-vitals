# ASTRO-VITALS · Guía del prototipo (`prototype/`)

Arquitectura local en procesos independientes conectados por red local:

**Pasarela / fuente externa (`8002` o emisor propio) → API a bordo + Motor IA + SQLite (`8000`) → Consola Web (`/` + `WS /telemetry`) o TUI Textual**.

## Instalación y ejecución rápida

Desde `astro-vitals/prototype/`:

```zsh
# Crear entorno virtual con Python 3.12 / 3.13 e instalar dependencias
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Iniciar con Consola Web en http://127.0.0.1:8000/
.venv/bin/python run.py --web
```

En Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --web
```

### Opciones de `run.py`

| Flag | Descripción |
| --- | --- |
| `--web` | Inicia API (`8000`) + pasarela (`8002`), imprime URL y abre la consola web |
| `--tui` | Inicia la consola interactiva de terminal (`Textual`, modo por defecto) |
| `--services-only` | Mantiene activos ambos servicios HTTP/WS sin abrir interfaz |
| `--environment {station,transit,rover,base}` | Selecciona el perfil inicial de entorno simulado |
| `--replay <ruta>` | Convierte un `.csv`, `.tsv`, `.json` o `.jsonl`, pausa la pasarela e ingesta las muestras |
| `--onboard-port <puerto>` | Puerto de la API y consola web (por defecto `8000`) |
| `--gateway-port <puerto>` | Puerto de la pasarela simulada (por defecto `8002`) |

La base SQLite local se guarda por defecto en `prototype/logs/astro_vitals.db` (configurable mediante `ASTRO_DB_PATH`).

---

## Qué probar en la Consola Web (`http://127.0.0.1:8000/`)

### Panel `ENTRADA DE TELEMETRÍA` (`/api/control`)

| Control | Qué demuestra en vivo |
| --- | --- |
| `REPOSO` | Estado basal y calibración fija de línea base (`mediana`/`MAD`) |
| `EJERCICIO` | Respuesta fisiológica esperada vs. pronóstico FC +60 s (`RandomForestRegressor`) |
| `CABINA CO₂` | Elevación directa de ppCO₂ y respiración; dispara hipótesis combinada no clínica |
| `RAMPA CO₂` | Subida progresiva según el perfil; tras $\ge 24$ muestras ($\Delta\text{CO}_2 \ge 0.40\text{ mmHg}$) activa regresión **OLS de sensibilidad** y **ETA al límite** |
| `TORMENTA DONKI` | Evento solar histórico `2024-05-11T04:07:00-SEP-001` por fases (`watch` → `arrival` → `peak` → `decay`) |
| `REFUGIO (SHELTER)` | Reduce la tasa de dosis simulada (`shelter_factor = 0.35`) y compara proyección de dosis a 1 h con/sin refugio |
| `PÉRDIDA SEÑAL` | Pone canales biométricos en `null`; muestra `SIN SEÑAL` / `--` y abstención explícita |
| `BIDMC REAL` | Reproduce `data/bidmc_01_Numerics.csv` (1 Hz) conservando `co2` y `dose_rate` en `null` sin fabricar datos espaciales |
| `ENTORNO` | Cambia umbrales de hábitat y multiplicador de radiación (`station`, `transit`, `rover`, `base`) |
| `RECONOCER (ACK)` | Registra el reconocimiento de una alerta vigente (`+5 pts`) sin resolver la condición subyacente |

### Barra lateral de módulos (`MÓDULOS`)

- **`MONITOR` / `ALERTAS`:** métricas completas, explicación del clasificador ML, intervalo de predicción de pulso, proyecciones CO₂/dosis y vista/descarga del **informe SBAR (`.md`)**.
- **`BIENESTAR`:**
  - **Minijuego psicomotor de 6 intentos:** envía `/api/v1/checkin` con mediana en ms, falsas salidas, lapsos $> 500\text{ ms}$, sueño y ánimo.
  - **Coach de participación:** rutinas preventivas (`+10 pts` rutina, `+15 pts` check-in, `+5 pts` ACK); puntos e insignias premian únicamente participación.
  - **Switch de privacidad:** por defecto `share_behavioral=False` oculta sueño, ánimo y reacción del informe SBAR externo.
- **`HISTORIAL` / `PERFIL` / `AJUSTES`:** series temporales desde SQLite, ficha de `ASTRA-001` y ajustes visuales/sonoros.

---

## Procesos independientes y endpoints

Si quieres correr cada servicio en su propia terminal desde `prototype/`:

```zsh
# Terminal 1: API a bordo + Consola Web + WebSocket
.venv/bin/python -m uvicorn astro.api:app --host 127.0.0.1 --port 8000

# Terminal 2: Pasarela simulada / reproductor BIDMC
.venv/bin/python -m uvicorn astro.gateway:app --host 127.0.0.1 --port 8002

# Terminal 3 (opcional): TUI de terminal
.venv/bin/python -m astro.tui
```

### API publicada en `:8000`

- **Motor y dominio (`/api/v1/*`):**
  - `GET /health` · `GET /docs`
  - `POST /api/v1/telemetry` · `GET /api/v1/state` · `GET /api/v1/trends` · `GET /api/v1/glossary`
  - `POST /api/v1/ack` · `POST /api/v1/checkin`
  - `GET /api/v1/routines` · `POST /api/v1/routines/{routine_id}/done`
  - `POST /api/v1/context/activity` · `POST /api/v1/context/event` · `POST /api/v1/context/environment`
  - `POST /api/v1/privacy` · `GET /api/v1/report`
- **Puente SQLite y Web (`/api/*` + WebSocket):**
  - `GET/POST /api/astronauts/` · `GET /api/astronauts/{id}`
  - `GET/POST /api/measurements/` · `GET /api/measurements/latest`
  - `GET/POST /api/alerts/` · `PATCH /api/alerts/{id}/ack`
  - `GET/POST /api/logs/` · `GET/POST /api/insights/`
  - `GET/POST /api/control` · `WS /telemetry`

---

## Verificación automatizada

Desde `astro-vitals/prototype/`:

```zsh
# Ejecutar las 50 pruebas (backend, pasarela, dominio, ML, coach/SBAR, adaptadores, WebBridge y E2E)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Revisar sintaxis JS de la consola web
for f in web/js/*.js; do node --check "$f" || exit 1; done
```

Adaptador de archivos en línea de comandos (`csv`, `tsv`, `json`, `jsonl`):

```zsh
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader inspect ruta/al/archivo.csv
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader convert ruta/al/archivo.csv --output-dir logs/replay
```
