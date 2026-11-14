# ASTRO-VITALS · Guía del prototipo TUI (`prototype/`)

Arquitectura local en procesos independientes conectados por red local (**100 % terminal Textual + HUD gráfico**, sin interfaz web):

**Pasarela (`8002`) / Simulador externo (`run.py --simulator`) → API a bordo + Motor IA + SQLite (`8000`) → Consola Operacional TUI (`run.py` / `--tui` / `--ui-only`)**.

## Instalación y ejecución rápida (2 ventanas)

Desde `astro-vitals-operacional/prototype/`:

```zsh
# Crear entorno virtual con Python 3.12 / 3.13 e instalar dependencias
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Ventana 1: inicia API (8000) + pasarela (8002) + Consola Operacional TUI
.venv/bin/python run.py
# o usando los alias explícitos:
.venv/bin/python run.py --tui
.venv/bin/python run.py --ui-only

# Ventana 2: abre el Simulador de Escenarios y Sensores conectado a los servicios activos
.venv/bin/python run.py --simulator
# Alias equivalentes: --sim / --sim-tui
```

Desde la raíz del repo (`astro-vitals-operacional/`) reutilizando el entorno de `../astro-vitals`:

```zsh
PYTHONPATH=prototype ../astro-vitals/prototype/.venv/bin/python prototype/run.py --ui-only
# En otra terminal:
PYTHONPATH=prototype ../astro-vitals/prototype/.venv/bin/python prototype/run.py --sim-tui
```

En Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
# En otra terminal:
.\.venv\Scripts\python.exe run.py --simulator
```

### Opciones de `run.py`

| Flag | Descripción |
| --- | --- |
| `--tui` / `--ui-only` | Inicia (o reutiliza) API (`8000`) + pasarela (`8002`) y abre la Consola Operacional TUI (modo por defecto) |
| `--simulator` / `--sim` / `--sim-tui` | Abre la TUI externa de simulación y sensores de traje (reutiliza servicios activos si `/health` responde `ok`) |
| `--services-only` | Mantiene activos ambos servicios HTTP/WS sin abrir TUI |
| `--environment {station,transit,rover,base}` | Selecciona el perfil inicial de entorno simulado |
| `--replay <ruta>` | Convierte un `.csv`, `.tsv`, `.json` o `.jsonl`, pausa la pasarela e ingesta las muestras |
| `--onboard-port <puerto>` | Puerto de la API y puente de control/WS (por defecto `8000`) |
| `--gateway-port <puerto>` | Puerto de la pasarela simulada (por defecto `8002`) |

La base SQLite local se guarda por defecto en `prototype/logs/astro_vitals.db` (configurable mediante `ASTRO_DB_PATH`).

---

## Ventana 1 · Consola Operacional (`astro/tui.py` + `astro/tui_graphics.py`)

Consola limpia de tripulación con ayuda contextual al pasar el mouse (*hover tooltips* y barra inspectora inferior) enfocada únicamente en información útil para el astronauta:

- **`01 · MONITOR E IA` (`m` / `1`):** 8 tarjetas con medidores horizontales de zona nominal (`▰▰▰◆▱▱`), ondas ECG/respiratorias en Braille `2×4`, *sparklines* continuos (`SIN SEÑAL (—)` ante cortes, sin relleno con ceros), silueta de traje en vivo, panel visual `EVALUACIÓN A BORDO E IA LOCAL` con recuadros dobles comparativos (`♥ AHORA` ◀▶ `◆ EN 1M`), barra de confianza del patrón detectado, referencia en descanso, respuesta al CO₂ y declaración rápida de actividad (`x`).
- **`02 · TENDENCIAS 1H` (`t`):** tarjeta HUD `RESUMEN DE TENDENCIAS EN CABINA` con barra de cobertura y medidores por canal (valor actual, promedio, rango y base personal), 4 gráficas Braille (`FC`, `FR`, `ppCO₂`, `Dosis`), tabla estadística y *sparklines* en ventanas `5 min`, `15 min` y `1 hora` (alternar con `v`).
- **`03 · CHECK-IN / REACCIÓN` (`c`):** **Cabina de Reflejos Ópticos** en 3 luces dobles, diana visual de 6 cápsulas (`[1 ⚡168]`, `[2 ◎ YA!]`), barras graduadas de velocidad, batería gráfica de sueño (`🔋`), estrellas de ánimo (`✨ ★`) y tarjeta `RESULTADO DE TU CHEQUEO HOY` (`⚡ HOY` ◀▶ `🎯 BASE`).
- **`04 · RUTINAS Y COACH` (`r`):** cabecera HUD en 3 recuadros dobles (`Puntos`, `Racha`, `Nivel`), barra de nivel, vitrina de medallas y tarjetas de contramedidas/rutinas con insignias (`▲ TOCA AHORA`, `● AL DÍA`, `◌ SOLO TORMENTA`), barra de repeticiones y puntos **exclusivamente por participación**.
- **`05 · INFORME SBAR` (`i`):** banner visual de privacidad (`SOLO EN LA NAVE` / `COMPARTIDO AL GUARDAR`), cuadrantes gráficos `[S]`, `[B]`, `[A]`, `[R]`, barras comparativas a `+1 hora` (CO₂ y radiación con/sin refugio), pasos sugeridos, línea de tiempo vertical del episodio (`●──▶`) y exportación `.md` en `prototype/reports/`.
- **`06 · GLOSARIO` (`h`):** niveles de aviso en recuadros dobles (`ESTABLE`, `REVISAR`, `ATENCIÓN`, `SIN EVALUACIÓN`) y reglas visuales de rango habitual (`[ min ── ▰▰▰▰▰▰ ── max unidad ]`) para cada señal.

---

## Ventana 2 · Simulador de Escenarios y Sensores (`astro/sim_tui.py`)

Ventana independiente para operar la demostración o pruebas de sensores desde otra terminal:

| Control | Qué ejecuta |
| --- | --- |
| `1`–`7` / `#scn-*` | Cambia escenario en pasarela (`rest`, `exercise`, `cabin`, `co2_ramp`, `solar_event`, `signal_loss`, `bidmc`) |
| `e` / `#env-*` | Cambia entorno simulado (`station`, `transit`, `rover`, `base`) |
| `f` / `#phase-*` | Cambia fase solar DONKI (`watch`, `arrival`, `peak`, `decay`) |
| `s` / `#btn-sim-shelter` | Activa/desactiva refugio de radiación (`shelter_factor = 0.35`) |
| `p` / `#btn-sim-pause` | Pausa o reanuda la emisión automática de la pasarela |
| Constructor de traje (`n` / `b`) | Ajusta valores canal por canal, envía 1 paquete (`n`) o stream 1 Hz (`b`) hacia `POST /api/v1/telemetry` |
| `SIN SEÑAL (—)` | Anula un canal individual (`None`/`null` estricto) sin rellenar con ceros |

---

## Procesos independientes y endpoints

Si quieres lanzar cada proceso manualmente desde `prototype/`:

```zsh
# Terminal 1: API a bordo + puente de control/WS
.venv/bin/python -m uvicorn astro.api:app --host 127.0.0.1 --port 8000

# Terminal 2: Pasarela simulada / reproductor BIDMC
.venv/bin/python -m uvicorn astro.gateway:app --host 127.0.0.1 --port 8002

# Terminal 3: Consola Operacional TUI
.venv/bin/python -m astro.tui

# Terminal 4: Simulador Externo TUI
.venv/bin/python -m astro.sim_tui
```

Nota: `GET /` devuelve `404` porque la interfaz web (`prototype/web/`) fue eliminada en esta rama. La API conserva `/health`, `/docs`, `/api/v1/*`, `/api/control`, `/api/*` y `WS /telemetry`.

---

## Verificación automatizada (52 tests)

Desde `astro-vitals-operacional/prototype/`:

```zsh
PYTHONPATH=. ../astro-vitals/prototype/.venv/bin/pytest tests/ -v
# o usando el .venv local si lo creaste dentro de astro-vitals-operacional/prototype/.venv:
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Adaptador de archivos en línea de comandos (`csv`, `tsv`, `json`, `jsonl`):

```zsh
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader inspect ruta/al/archivo.csv
PYTHONPATH=. .venv/bin/python -m astro.adapters.loader convert ruta/al/archivo.csv --output-dir logs/replay
```
