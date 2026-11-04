# Datos de fusión de cabina y fisiología

La cohorte sintética v2 contiene **108.000 mediciones a 1 Hz**. Son cuatro sesiones de 15 minutos para cada uno de los 30 perfiles ficticios. Cada sesión registra FC en bpm, FR en respiraciones/minuto, presión parcial de CO₂ en mmHg, fase de actividad y segundo de inicio de la fase. Su uso es entrenar y evaluar el reconocimiento de los cuatro patrones definidos por el simulador. [Contrato del modelo](../../CONTRATO_DE_DATOS.md) · [Guiones de referencia](../../scenarios/README.md)

| Partición | Perfiles | Sesiones | Reposo | Actividad o recuperación habitual | Desviación de recuperación | Cambio de cabina y fisiología | Ventanas utilizables |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Entrenamiento | 20 | 80 | 3.409 | 1.822 | 476 | 599 | 6.306 |
| Validación | 5 | 20 | 895 | 421 | 130 | 124 | 1.570 |
| Prueba reservada | 5 | 20 | 905 | 421 | 128 | 140 | 1.594 |

## Uso en el modelo

Usar la lista ordenada `features` y el objetivo `pattern` del manifiesto. Los identificadores de persona y sesión y el tiempo relativo sirven para rastrear una fila. Se reserva a cada persona completa en una sola partición antes de generar sesiones y ventanas. Cada sesión recibe una semilla propia derivada de partición, perfil y guion. [Manifiesto](manifest.json) · [Entrenamiento](ventanas_train.csv) · [Validación](ventanas_validation.csv) · [Prueba](ventanas_test.csv)

Cada 5 s se resumen las mediciones hasta ese instante. Para cada canal se calcula el último valor válido y la media, desviación poblacional y pendiente por segundo en las ventanas de 30 y 120 s. Se exige un mínimo del 80 % de muestras válidas en cada ventana y canal, con última lectura de hasta 5 s de antigüedad. La fase, su duración y la diferencia de FC y FR respecto a la calibración completan las 25 variables. La calibración es la media de cada señal en los primeros 120 s de reposo de esa sesión, redondeada a cinco decimales. [Telemetría con procedencia por fila](telemetria.csv.gz)

## Generación y etiquetas

- El perfil fija los niveles basales de FC, FR y CO₂ en intervalos de 60–85 bpm, 11–18 respiraciones/min y 1,5–3,0 mmHg, respectivamente. Son parámetros de simulación. El esfuerzo de cada sesión eleva los valores objetivo de FC en 28–64 bpm y de FR en 6–13 respiraciones/min. Las señales se acercan gradualmente a sus objetivos con una constante de tiempo de 24–46 s. Se añade oscilación y ruido antes de registrar las mediciones.
- En una recuperación lenta, la constante de tiempo aumenta por un factor de 3–5. En una intervención de cabina se incrementan los objetivos de CO₂ en 1,4–3,4 mmHg, de FR en 4–8 respiraciones/min y de FC en 1–8 bpm. Cada sesión conserva en auditoría la diferencia respecto a una evolución ordinaria con el mismo perfil y esfuerzo.
- En los guiones habituales se desplazan los límites internos hasta 18 s. En el guion de cabina se distribuye el comienzo de la intervención entre aproximadamente 140 y 590 s dentro de cada partición. Así hay reposo ordinario y reposo con intervención con duraciones comparables. Cada sesión también introduce una interrupción de 3–15 s en un canal a partir del segundo 180. El guion de cabina incorpora, además, una pérdida de FR de 43–56 s durante el episodio.
- La etiqueta latente se activa después de 30 s de intervención aislada. Para entrenamiento se exige una ventana de 120 s con fase y clase únicas, mediciones suficientes y un cambio que persista frente al control. En recuperación se exigen diferencias de al menos 2 bpm y 0,5 respiraciones/min. En cabina se exigen al menos 0,5 mmHg y 1 respiración/min. Las coincidencias de dos intervenciones, los cambios débiles y las transiciones quedan identificados para evaluación por episodio.

Hay 21.600 instantes anotados en total. De ellos, 9.470 son ventanas candidatas, 2.880 corresponden a calibración, 6.650 a transición, 1.152 a señal insuficiente, 1.444 a patrones coincidentes y 4 a contraste débil. Las semillas, el guion y las diferencias frente al control permanecen en archivos de auditoría. [Sesiones](sesiones.csv) · [Anotaciones](anotaciones.csv.gz)

## Reproducción y comprobación

Desde la raíz del proyecto, con el Python del proyecto y su biblioteca estándar:

```powershell
.\.venv\Scripts\python.exe -B ml\preparar_fusion.py
.\.venv\Scripts\python.exe -B -m unittest discover -s ml -p test_fusion.py
```

Las pruebas reconstruyen los valores de cada ventana a partir de su telemetría, verifican la correspondencia con la anotación y comprueban la separación de perfiles, sesiones y semillas. En esta cohorte, **cada ventana de cambio de cabina tiene al menos una ventana de reposo ordinario con idéntica duración de fase en su propia partición**. Se comprobó esa coincidencia para las 599, 124 y 140 ventanas de cabina, respectivamente. El entrenamiento posterior deberá informar resultados por clase y perfil, ya que el reposo es más frecuente y las ventanas vecinas se solapan. La generalización que se podrá medir aquí corresponde a perfiles nuevos de este simulador.
