# ASTRO-VITALS · Edición Operacional 100% TUI

Proyecto para **NASA Space Apps Cajamarca**. ASTRO-VITALS ayuda a un tripulante a interpretar cambios en sus signos vitales teniendo en cuenta su actividad, su línea base personal, la calidad de los sensores y el entorno de cabina o radiación, funcionando **de forma autónoma a bordo** sin depender de latencia con la Tierra.

> **Aviso de alcance:** Toda evaluación es **orientativa y no clínica** (*"Hipótesis orientativa (escenario simulado): ..."*). Cuando faltan canales o hay cortes de telemetría, el sistema conserva `null`/`None` internamente y se abstiene de evaluar; en pantalla siempre muestra `SIN SEÑAL (—)` y nunca rellena ausencias con cero.

## Arquitectura de esta rama (`feat/interfaz-operacional`: 100% Terminal TUI + HUD gráfico)

A diferencia de `main` (consola web integrada para demostración rápida), esta versión elimina la interfaz web (`prototype/web/` y `--web`) y separa por completo la **operación real en cabina** de la **simulación externa**, usando **dos aplicaciones Textual independientes** potenciadas por el motor gráfico HUD ([`prototype/astro/tui_graphics.py`](prototype/astro/tui_graphics.py)):

1. **Terminal 1 — Consola Operacional del Astronauta ([`prototype/astro/tui.py`](prototype/astro/tui.py) + [`prototype/astro/tui_graphics.py`](prototype/astro/tui_graphics.py)):**
   - Interfaz limpia de tripulación enfocada únicamente en lo necesario para el astronauta, con ayuda contextual interactiva al pasar el mouse (*hover tooltips* y barra inspectora inferior) en lenguaje directo, sin tecnicismos informáticos ni identificadores internos `snake_case`.
   - Organizada en **6 vistas gráficas navegables por teclado**:
     - `01 · MONITOR E IA` (`m` / `1`): 8 tarjetas con medidores horizontales de zona nominal (`▰▰▰◆▱▱`), ondas ECG y respiratorias en Braille de alta resolución (`2×4`), *sparklines* continuos (corte explícito en `SIN SEÑAL (—)`), silueta de traje con telemetría en vivo y panel visual **`EVALUACIÓN A BORDO E IA LOCAL`** con recuadros dobles comparativos (`♥ AHORA` ◀▶ `◆ EN 1M`), barra de confianza del patrón detectado, referencia en descanso y respuesta al CO₂.
     - `02 · TENDENCIAS 1H` (`t`): tarjeta HUD **`RESUMEN DE TENDENCIAS EN CABINA`** con barra de cobertura y medidores por canal (valor actual, promedio, rango y base personal), 4 gráficas Braille (`FC`, `FR`, `ppCO₂`, `Dosis`), tabla estadística y *sparklines* en ventanas de `5 min`, `15 min` y `1 hora` (`v`).
     - `03 · CHECK-IN / REACCIÓN` (`c`): **Cabina de Reflejos Ópticos** (semáforo visual de 3 luces en recuadros dobles), diana de 6 cápsulas de intento (`[1 ⚡168]`, `[2 ◎ YA!]`), barras graduadas de velocidad frente a tu marca personal, batería gráfica de sueño (`🔋`), selector de ánimo por estrellas (`✨ ★`) y tarjeta **`RESULTADO DE TU CHEQUEO HOY`** (`⚡ HOY` ◀▶ `🎯 BASE`).
     - `04 · RUTINAS Y COACH` (`r`): cabecera HUD con 3 recuadros dobles (`Puntos`, `Racha`, `Nivel`), barra de progreso al siguiente nivel, vitrina de medallas (`★ 1ª Rutina`, `⚡ 1er Check-in`, `🔥 Racha x3`, `🛡 Refugio`) y tarjetas de rutinas con insignias de estado (`▲ TOCA AHORA`, `● AL DÍA`, `◌ SOLO TORMENTA`) y barra de repeticiones (`▰▱▱▱▱`) con puntos **exclusivamente por participación**.
     - `05 · INFORME SBAR` (`i`): banner visual de privacidad (`SOLO EN LA NAVE` vs `COMPARTIDO AL GUARDAR`), cuadrantes gráficos `[S] Situación`, `[B] Antecedentes`, `[A] Lectura de signos`, `[R] Siguiente paso recomendado`, barras comparativas a `+1 hora` (CO₂ y radiación con/sin refugio), pasos sugeridos, línea de tiempo vertical del episodio (`●──▶`) y guardado en `prototype/reports/episodio_sbar.md`.
     - `06 · GLOSARIO` (`h`): tarjetas de niveles de aviso en recuadros dobles (`ESTABLE`, `REVISAR`, `ATENCIÓN`, `SIN EVALUACIÓN`) y reglas visuales de rango habitual (`[ min ── ▰▰▰▰▰▰ ── max unidad ]`) para las 9 señales del traje y la cabina.
2. **Terminal 2 — Simulador de Escenarios y Sensores de Traje ([`prototype/astro/sim_tui.py`](prototype/astro/sim_tui.py)):**
   - Se ejecuta en una **ventana aparte** (`python prototype/run.py --simulator`, o los alias `--sim` / `--sim-tui`) y reutiliza automáticamente la API (`8000`) y pasarela (`8002`) ya iniciadas.
   - Controla en vivo los 7 escenarios (`1`–`7`), 4 entornos (`e`), 4 fases solares DONKI (`f`), refugio (`s`) y pausa (`p`).
   - Incluye **Constructor de Paquete de Traje** (`POST /api/v1/telemetry`) con ajuste paso a paso por canal, emisión unitaria (`n`), stream 1 Hz (`b`) y botones **`SIN SEÑAL (—)`** por canal para validar el comportamiento ante fallos reales de sensores.

## Motor y modelos integrados

- **Motor a bordo ([`prototype/astro/engine.py`](prototype/astro/engine.py)):** calibración fija de línea base (`mediana`/`MAD`), sensibilidad personal al CO₂ (`OLS`), ETA a `3.0 mmHg` (NASA OCHMO-TB-004), radiación integrada por trapecio en intervalos $\le 5\text{ s}$ y fases solares NASA DONKI (`2024-05-11T04:07:00-SEP-001`).
- **Modelos de IA locales ([`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/)):** `RandomForestRegressor` (FC +60 s) y `RandomForestClassifier` (patrones con abstención automática ante baja cobertura $< 80\%$, datos antiguos $> 5\text{ s}$, `bidmc` o confianza $< 0.60$).
- **Persistencia local ([`prototype/astro/storage.py`](prototype/astro/storage.py)):** SQLite (`prototype/logs/astro_vitals.db`) conservando `NULL` estrictos.
- **Adaptador universal ([`prototype/astro/adapters/loader.py`](prototype/astro/adapters/loader.py)):** conversión explícita de `.csv`, `.tsv`, `.json` y `.jsonl` (`ppm`/`kPa` $\to$ `mmHg`, `mSv/h` $\to$ `μSv/h`).

---

## Guía rápida para probar las 2 ventanas en terminal

### 1. Requisitos e instalación

Se recomienda **Python 3.12 o 3.13**.

**macOS / Linux:**

```zsh
cd astro-vitals-operacional
python3.13 -m venv prototype/.venv
prototype/.venv/bin/pip install -r prototype/requirements.txt
```

*(Si ya creaste `prototype/.venv` en el directorio principal `astro-vitals`, puedes usar directamente ese intérprete apuntando con `PYTHONPATH=prototype`, como se muestra abajo.)*

### 2. Abrir Terminal 1: Consola Operacional del Astronauta

Con entorno virtual local:

```zsh
prototype/.venv/bin/python prototype/run.py
# Equivalente explícito:
prototype/.venv/bin/python prototype/run.py --tui
# O usando el alias --ui-only:
prototype/.venv/bin/python prototype/run.py --ui-only
```

O reutilizando el entorno virtual del directorio `../astro-vitals`:

```zsh
PYTHONPATH=prototype ../astro-vitals/prototype/.venv/bin/python prototype/run.py --ui-only
```

Cualquiera de estos comandos levanta automáticamente (o reutiliza si ya está activa) la **API a bordo (`127.0.0.1:8000`)**, la **pasarela (`127.0.0.1:8002`)** y abre la **Consola Operacional TUI**.

### 3. Abrir Terminal 2: Ventana del Simulador de Escenarios y Sensores

En otra pestaña o ventana de terminal:

```zsh
prototype/.venv/bin/python prototype/run.py --simulator
# También disponibles los alias --sim / --sim-tui, o reutilizando ../astro-vitals:
PYTHONPATH=prototype ../astro-vitals/prototype/.venv/bin/python prototype/run.py --sim-tui
```

`run.py` detecta que los puertos `8000` y `8002` ya tienen `/health` en estado `ok` y conecta el Simulador directamente sin conflictos de puerto.

- Prueba los escenarios `1`–`7` (`rest`, `exercise`, `cabin`, `co2_ramp`, `solar_event`, `signal_loss`, `bidmc`), cambia de entorno (`e`), activa fase solar (`f`) + refugio (`s`).
- En el **Constructor de Paquete de Traje**, anula canales individuales con `SIN SEÑAL (—)` y pulsa `n` (paquete único) o `b` (stream 1 Hz) para observar en Terminal 1 cómo la Consola Operacional mantiene `SIN SEÑAL (—)` sin rellenar con ceros.

### 4. Otras formas de ejecución y emisor externo Python

```zsh
# Solo servicios backend + pasarela (para conectar tus propios clientes o scripts)
prototype/.venv/bin/python prototype/run.py --services-only

# Arrancar con perfil de entorno inicial y/o reproducción de archivo
prototype/.venv/bin/python prototype/run.py --environment rover --replay ruta/al/registro.csv
```

Ejemplo mínimo de emisor externo hacia `POST /api/v1/telemetry` respetando el contrato estricto (`Telemetry`, `extra="forbid"`):

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
            "original_time_s": None,
        })
        time.sleep(1.0)
```

### 5. Ejecutar las pruebas de verificación (52 tests)

```zsh
PYTHONPATH=prototype prototype/.venv/bin/pytest prototype/tests/ -v
# o reutilizando ../astro-vitals:
PYTHONPATH=prototype ../astro-vitals/prototype/.venv/bin/pytest prototype/tests/ -v
```

---

## Arquitectura y stack tecnológico

| Componente | Tecnología | Ubicación |
| --- | --- | --- |
| API a bordo + puente control/WS | Python, FastAPI, Pydantic, Uvicorn | [`prototype/astro/api.py`](prototype/astro/api.py), [`web_bridge.py`](prototype/astro/web_bridge.py) |
| Motor fisiológico y ambiental | Calibración `MAD`, OLS CO₂, trapecio radiación, DONKI | [`prototype/astro/engine.py`](prototype/astro/engine.py), [`donki.py`](prototype/astro/donki.py) |
| Modelos de IA locales | `scikit-learn` (`RandomForest`), `joblib`, NumPy | [`prototype/astro/ml_models.py`](prototype/astro/ml_models.py), [`ASTRO-VITALS-AI-Modelos-v1/`](ASTRO-VITALS-AI-Modelos-v1/) |
| Persistencia local | SQLite (`sqlite3`, preservando `NULL` estrictos) | [`prototype/astro/storage.py`](prototype/astro/storage.py) |
| Consola Operacional TUI | Textual (`AstroVitalsApp`, 6 vistas HUD, sin demo) | [`prototype/astro/tui.py`](prototype/astro/tui.py) |
| Motor gráfico HUD en terminal | Canvas Braille `2×4`, ECG, medidores, cabina óptica y tarjetas | [`prototype/astro/tui_graphics.py`](prototype/astro/tui_graphics.py) |
| Simulador Externo TUI | Textual (`SimulatorTUIApp`, escenarios + traje) | [`prototype/astro/sim_tui.py`](prototype/astro/sim_tui.py) |
| Pruebas automatizadas | `pytest` + Pilot headless de Textual (52 pruebas) | [`prototype/tests/`](prototype/tests/) |

[Guía detallada del prototipo](prototype/README.md) · [Contrato de datos](CONTRATO_DE_DATOS.md) · [Alcance del MVP](MVP_ASTRO_VITALS.md) · [Arquitectura técnica](ARQUITECTURA_TECNICA.md)
