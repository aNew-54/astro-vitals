# Guion v1 del clasificador experimental

Cuatro sesiones ficticias de 15 minutos permiten revisar qué etiqueta se esperaría en cada ventana antes de generar señales de entrenamiento. Los tiempos son relativos al inicio de cada sesión y los intervalos incluyen el comienzo y excluyen el final. [Guion por intervalos](guion_v1.csv) · [Anotaciones cada 5 s](anotaciones_v1.csv)

| Sesión | Qué ocurre en el guion | Qué debe poder distinguirse |
| --- | --- | --- |
| Habitual | Reposo inicial, ejercicio desde 240 s, recuperación desde 480 s y reposo desde 720 s. | Ejercicio y recuperación habitual comparten `activity_expected`. El reposo se etiqueta `baseline_expected`. |
| Recuperación | Ejercicio desde 200 s. Desde 420 s se inyecta una recuperación más lenta que la curva esperada para ese perfil y esfuerzo. | A partir de 450 s, `persistent_recovery_deviation`. La primera ventana completa candidata termina en 570 s. |
| Cabina | En reposo, suben conjuntamente CO₂ local y respuesta respiratoria desde 240 s hasta 630 s. La FR falta entre 570 y 630 s. | El patrón `combined_cabin_physiology_pattern` empieza a los 270 s. Una interrupción del sensor conserva la verdad del guion y limita la evaluación. |
| Coincidencia | Tras el ejercicio, se inyectan juntos recuperación lenta y cambio de cabina entre 420 y 660 s. | Es un caso ambiguo para un clasificador de una sola etiqueta. Se conserva para evaluar el comportamiento ante combinaciones. |

**Reglas de anotación de la demo.** Los primeros 120 s de cada sesión sirven para calibración en reposo. Una intervención aislada se considera sostenida tras 30 s sin interrupción. Cambiar la disponibilidad de un sensor no reinicia la intervención. En las sesiones habituales, la etiqueta se obtiene de la fase. En las intervenidas, se obtiene del cambio inyectado y su duración. Estas son decisiones experimentales del guion sintético.

`pattern_at_t` guarda la verdad del escenario al final de la ventana. `window_status` indica si puede usarse como ejemplo de una sola clase. Una ventana candidata abarca 120 s con la misma fase y etiqueta. Las ventanas mixtas se conservan como transiciones. Una coincidencia de intervenciones deja vacía la etiqueta única. Las pérdidas programadas de sensor se evalúan con la misma cobertura y antigüedad que en el contrato. Si una ventana cumple varias condiciones de exclusión, se registra en este orden calibración, coincidencia de patrones, señal insuficiente y transición.

El guion produce **720 instantes**, de los cuales **313** son candidatos antes de generar telemetría. Se reparten en 160 de reposo, 92 de actividad/recuperación esperada, 24 de desviación de recuperación y 37 de cambio de cabina. Los 233 instantes de transición se pueden usar para medir demora desde el inicio de un episodio. También se conservan 96 de calibración, 30 de señal insuficiente y 48 de coincidencia.

**Aplicación del guion.** La cohorte de fusión v2 amplía estas plantillas con 30 perfiles, tiempos de intervención variables y controles de reposo de igual duración. Sus particiones contienen las mediciones generadas y pasan filtros adicionales de calidad y contraste. Los conteos anteriores describen exclusivamente las cuatro plantillas del guion. [Datos de entrenamiento del clasificador](../data/fusion_simulada/README.md) · [Contrato de entradas y salidas](../CONTRATO_DE_DATOS.md)

Las anotaciones se reproducen desde la raíz del proyecto con el siguiente comando.

```powershell
.\.venv\Scripts\python.exe ml\preparar_etiquetas.py
```
