# ASTRO-VITALS · prototipo 0.1

Una consola funcional pequeña para discutir la experiencia con el equipo. Usa tres procesos reales: **pasarela/simulador → API a bordo → TUI del astronauta**. Se comunican mediante HTTP local; la TUI no recibe sensores directamente. Funciona sin internet después de instalar dependencias y obtener el CSV de ejemplo.

## Probar ahora

En la carpeta del proyecto, abre **Iniciar prototipo.cmd**, o ejecuta en PowerShell:

```powershell
.\.venv\Scripts\python.exe prototype\run.py
```

Maximiza el terminal para ver las tarjetas. En ventanas pequeñas puedes desplazarte verticalmente. `Q` cierra la demo y sus dos servicios. Para comprobar que cerrar solo la TUI no detiene el nodo, usa los comandos separados de abajo.

| Control | Qué demuestra |
| --- | --- |
| `1` Reposo | Señales sintéticas y estado base |
| `2` Actividad | El contexto cambia la interpretación del pulso |
| `3` Cabina | Cambio conjunto de CO₂ y respiración, con hipótesis y evidencia |
| `4` Radiación | Dosímetro simulado; no altera el pulso por una supuesta causa solar |
| `S` | Dentro de radiación, simula refugio y reduce la tasa; la dosis acumulada no disminuye |
| `5` Sin señal | Datos fisiológicos ausentes; evaluación incompleta |
| `6` BIDMC | Reproduce pulso y respiración reales del registro 01 a una muestra por segundo |
| `P` | Pausa/reanuda la fuente; al pasar 5 s la API indica datos desactualizados |
| `A` | Reconoce la alerta; no la resuelve ni cambia las mediciones |
| `Q` | Sale de la consola |

Los botones equivalen a los atajos. Los controles del laboratorio pertenecen a la demostración, no son controles del wearable. Los cambios de escenario modifican datos del simulador; no envían una orden de generar un diagnóstico.

## Alcance de esta entrega

- Textual, FastAPI, HTTPX; refresco de pantalla mediante consulta HTTP cada segundo.
- Evaluación orientativa con **reglas explícitas**, evidencia y límites ilustrativos.
- Referencia de pulso a 60 s por **persistencia**: mantiene el último valor. Aún no se entrena Random Forest ni se reporta precisión predictiva.
- Tasa de dosis en μSv/h integrada a μSv con intervalos válidos. Se indica cobertura parcial tras huecos o registros sin dosímetro.
- Historial reciente y bitácora en memoria. Reiniciar el servicio reinicia la sesión. No hay todavía base de datos, sincronización con Tierra, página web, WebSocket ni integración DONKI.
- No convierte los datos terrestres en un diagnóstico de astronauta. En BIDMC, CO₂ y radiación quedan ausentes: no se agregan columnas sintéticas para aparentar mediciones conjuntas.

El [contrato de datos del MVP](../CONTRATO_DE_DATOS.md) especifica las dos tareas de aprendizaje previstas. En 0.1, el registro BIDMC alimenta solo las tarjetas de FC y FR. SpO₂, la calibración personal, el autorreporte y los modelos entrenados pertenecen a la siguiente etapa. [Arquitectura prevista](../ARQUITECTURA_TECNICA.md)

## Datos disponibles sin esperar al desafío

Se incluye `data/bidmc_01_Numerics.csv`, original sin cambios: 481 muestras de parámetros numéricos a 1 Hz, aproximadamente ocho minutos. `HR` → pulso ECG y `RESP` → respiración. Se conserva `Time [s]` como `original_time_s`; la hora de reproducción es nueva y no se presenta como fecha clínica. `NaN` se convierte a ausencia. Al terminar, el reproductor se pausa; pulsa `6` para reiniciarlo.

Fuente: [BIDMC PPG and Respiration Dataset v1.0.0](https://physionet.org/content/bidmc/1.0.0/), Pimentel, Johnson y Charlton (2018), PhysioNet, [DOI 10.13026/C2208R](https://doi.org/10.13026/C2208R). Licencia [Open Data Commons Attribution v1.0](https://physionet.org/content/bidmc/view-license/1.0.0/). El archivo vecino `.source.json` registra URL, atribución, fecha de descarga y SHA-256. Ver [decisión de fuentes alternativas](../DATOS_ALTERNATIVOS.md).

El aviso del desafío aportado por el equipo indica recursos disponibles el **13 de noviembre de 2026**. No se depende de esa publicación para demostrar esta versión. Este registro real permite probar reproducción e ingestión; las etiquetas y variables necesarias para entrenar la futura fusión son otra tarea.

## Instalar en otro equipo

Se ha usado Python **3.14** disponible en este equipo; el plan original proponía 3.12. El archivo fija las versiones efectivamente instaladas. No hace falta instalar Node para esta entrega.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r prototype\requirements.txt
.\.venv\Scripts\python.exe prototype\run.py
```

El CSV está incluido. Para volver a descargar únicamente ese registro público:

```powershell
.\.venv\Scripts\python.exe prototype\download_data.py
```

## Procesos separados y red local

Desde `prototype/`, abre tres terminales:

```powershell
# Terminal 1: API a bordo
..\.venv\Scripts\python.exe -m uvicorn astro.api:app --host 127.0.0.1 --port 8000

# Terminal 2: pasarela independiente
..\.venv\Scripts\python.exe -m uvicorn astro.gateway:app --host 127.0.0.1 --port 8002

# Terminal 3: vista del astronauta
..\.venv\Scripts\python.exe -m astro.tui
```

`ONBOARD_URL` configura a qué API envían datos la pasarela y la TUI; `GATEWAY_URL` configura los controles de demo. Para otra computadora se debe exponer el servicio correspondiente en la LAN y ajustar estas direcciones. Esta versión se inicia solo en localhost; no implementa autenticación para exponerla públicamente.

La API publica `/health`, `/api/v1/state`, `/api/v1/telemetry`, `/api/v1/ack` y documentación `/docs`. La pasarela publica `/health` y `GET/POST /control`. La simulación solar es una fuente ficticia, todavía no un evento histórico NASA descargado.

## Verificar

Desde `prototype/`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
```

Las pruebas cubren ingestión, duplicados, falta de datos, unidades de dosis y controles de la fuente. `python run.py --services-only` permite ejecutar solo los servicios; con ellos activos, `python check_demo.py` comprueba la interacción de la TUI y guarda capturas SVG en `previews/`. Los registros del lanzador quedan en `prototype/logs/`.

Verificado el 28 de octubre de 2026 en este equipo: **12 pruebas aprobadas**, más el recorrido de la TUI contra los servicios HTTP reales (cambio de escenario, BIDMC, pausa/antigüedad, reconocimiento, pérdida de señal y dosis/refugio). Las capturas corresponden a la aplicación ejecutada en modo de prueba de Textual.
