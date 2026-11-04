# ASTRO-VITALS · Contrato de datos y salidas del MVP

Decisión de diseño del 3 de noviembre de 2026. Este contrato define lo que comparten los equipos de datos, simulación e interfaz. La [arquitectura](ARQUITECTURA_TECNICA.md) describe cómo implementarlo y la [guía del prototipo 0.1](prototype/README.md) describe lo que ya se puede ejecutar.

La pregunta del producto es «¿cómo evolucionan mis señales durante esta actividad y qué cambios conviene revisar?». A bordo se calculan por separado el pronóstico de frecuencia cardíaca, el patrón del escenario y el estado ambiental. Cada componente comunica su disponibilidad y la evidencia que lo respalda.

## Entradas

| Variable | Definición y unidad | Quién la usa |
| --- | --- | --- |
| Frecuencia cardíaca (FC) | Latidos/minuto (bpm). En BIDMC usar `HR`, derivada del ECG. `PULSE` es una medición óptica distinta. | Obligatoria para ambos modelos. Visible en la consola. |
| Frecuencia respiratoria (FR) | Respiraciones/minuto. En BIDMC usar `RESP`. | Obligatoria para ambos modelos. Visible en la consola. |
| Actividad | `rest`, `exercise`, `recovery` o `unknown`. Registrar la fase conocida y cuándo se comunicó. | El clasificador requiere fase conocida. La interfaz puede mostrar «desconocida». |
| Tiempo en la actividad | Segundos desde el inicio conocido de la fase hasta el instante de análisis. | Obligatorio para el clasificador. Si falta el inicio, la duración queda ausente. |
| Referencias personales de FC y FR | Valores en las unidades de cada señal, calculados en un tramo anterior de reposo válido de la misma persona o recuperados de una calibración previa identificada. Se mantienen fijos durante el episodio. | El clasificador usa diferencias respecto a esas referencias. Sin calibración, la interfaz indica «calibrando». |
| CO₂ de cabina | Presión parcial en mmHg del módulo ocupado en ese momento. Convertir desde ppm solo cuando se conozca también la presión total. | Obligatorio para el clasificador de los cuatro patrones. Las reglas ambientales pueden evaluar este canal por separado. |
| SpO₂ | Saturación periférica de oxígeno en %. Campo opcional para visualización cuando la fuente lo permita. | La columna existe en el CSV BIDMC. Su integración en pantalla queda para una etapa posterior. |
| Tasa de dosis | Lectura del dosímetro local en μSv/h, simulada en la demo. Conservar el tipo de magnitud y la unidad de origen. | El módulo ambiental integra dosis en μSv sobre intervalos válidos y registra su cobertura. |
| Autorreporte | Esfuerzo percibido, malestar y observaciones con hora y autor. | La interfaz lo asocia al episodio para revisión humana. |

Cada medición conserva sesión, persona o ubicación según corresponda, tiempo de medición, unidad, fuente, calidad y tiempo de recepción. Si el registro trae solo segundos relativos, se conserva ese desplazamiento junto al reloj de reproducción. Un valor ausente se representa como `null`. Identidades, nombres de escenarios y semillas sirven para trazabilidad, partición o evaluación y quedan fuera de las variables predictoras.

## Qué aprende cada modelo

Una fila representa una ventana de **una persona en una sesión**, con instante final `t`. La propuesta de ingeniería calcula una fila cada 5 s usando los 120 s previos, incluido `t`. Para cada señal requerida se obtiene el último valor y se calculan media, dispersión y pendiente en ventanas de 30 y 120 s. Se usan únicamente datos conocidos a bordo al emitir el análisis. El manifiesto de cada modelo fijará la definición numérica y el orden de sus columnas.

| Componente | Entradas al emitir el análisis | Objetivo durante el entrenamiento | Salida en la interfaz |
| --- | --- | --- | --- |
| Pronóstico básico | FC y FR de esa ventana. Puede funcionar en BIDMC aunque se desconozca la actividad. | FC válida observada en la **misma sesión** en `t + 60 s`. Se excluyen ejemplos sin esa observación. | Estimación en bpm, instante objetivo y método. |
| Clasificador experimental | FC, FR, CO₂ local, fase conocida, duración y diferencias de FC/FR respecto a su referencia personal. | Patrón etiquetado para esa ventana del escenario sintético. | Patrón simulado, observaciones, duración del cambio y siguiente paso de revisión. |

Las cuatro etiquetas del clasificador son `baseline_expected` (reposo esperado), `activity_expected` (actividad o recuperación esperada), `persistent_recovery_deviation` (desviación persistente durante la recuperación) y `combined_cabin_physiology_pattern` (cambio conjunto de cabina y fisiología). Las etiquetas se guardan aparte de la telemetría que recibe el modelo. La referencia de reposo por sí sola es insuficiente para etiquetar una recuperación como desviada. El generador debe especificar qué recuperación espera para esa actividad y qué desviación persiste.

**Ejemplo verificable.** En el segundo 120 del registro BIDMC 01, la FC es 92 bpm y la FR es 22/min. Para preparar una fila de pronóstico usamos solo la historia hasta ese segundo. La respuesta de entrenamiento es la FC del segundo 180, **91 bpm**. La referencia de persistencia habría pronosticado **92 bpm**. Este registro carece del contexto de actividad y cabina requerido por el clasificador. [CSV incluido en el proyecto](prototype/data/bidmc_01_Numerics.csv)

## Qué calcula el sistema y qué muestra la interfaz

| Salida | Responsable | Comportamiento previsto |
| --- | --- | --- |
| Disponibilidad por componente | Reglas de calidad | Indicar si el resultado es evaluable, está calibrando, falta historia/señal, hay datos antiguos o falta el modelo. Conservar el motivo y el instante del último análisis. |
| Evidencia del cambio | Motor a bordo | Mostrar valores observados, tendencias, duración y referencia utilizada. Una clase se presenta con su origen simulado. |
| Estado de cabina y radiación | Reglas ambientales | Mostrar CO₂ local, tasa y dosis acumulada con cobertura. Un evento histórico DONKI aporta fecha y contexto externo. La exposición personal se calcula a partir del dosímetro. |
| Mensaje de revisión | Plantillas del episodio | Explicar qué señal revisar y permitir registrar una observación o reconocer el aviso. El reconocimiento se guarda separado del estado de la condición. |

Cada modelo evalúa **sus propias entradas obligatorias**. Los criterios iniciales del diseño exigen al menos 80 % de muestras válidas por canal requerido en la ventana y una antigüedad máxima de 5 s para su última lectura válida. Se ajustarán en validación. Ante datos insuficientes, la salida del modelo afectado queda sin valor. Si hay una FC vigente, la interfaz puede mostrar por separado la referencia de persistencia con su método. Una abstención del clasificador se muestra con su motivo, separada de las cuatro clases.

## Datos y evaluación

- **Pronóstico.** Empezar por los registros numéricos de BIDMC. Separar personas antes de crear ventanas, manteniendo cada registro completo en una sola partición. Si la fuente solo permite separar registros, documentar esa limitación. Comparar el error absoluto medio en bpm contra persistencia y extrapolación de tendencia en las mismas ventanas. Elegir el método con validación y reportar su rendimiento en prueba reservada.
- **Clasificación.** Generar sesiones coherentes con fisiología, actividad y ambiente sincronizados. Separar perfiles y semillas entre entrenamiento, validación y prueba. Medir macro-F1, confusiones, abstenciones, falsas alertas por hora simulada y demora por episodio. Los resultados describen esos escenarios.
- **Otras fuentes.** PPG-DaLiA y WESAD disponen de ventanas terrestres separadas por persona. MMASH aporta episodios de sueño y DONKI un evento solar histórico. RR-1 aporta series de cabina en ppm y radiación ambiental en mGy/día. Estas fuentes se utilizan con sus propias etiquetas, unidades y relojes. [Inventario y criterios de uso](DATOS_ALTERNATIVOS.md)

Al 4 de noviembre hay 3.170 ventanas reales de pronóstico separadas por participante y 9.470 ventanas sintéticas del clasificador separadas por perfil. Se conservan la telemetría, las anotaciones y la lista explícita de predictores. [Pronóstico](data/bidmc/README.md) · [Clasificación](data/fusion_simulada/README.md)

## Decisiones pendientes

| Cuándo | Qué queda por definir | Qué permite cerrarlo |
| --- | --- | --- |
| Antes de conectar fuentes en vivo | Política de llegada tardía y desfase admisible entre cuerpo y cabina. El procesamiento BIDMC por tiempo de registro ya está definido. | Reproducir datos fuera de orden y verificar qué información conocía el nodo en cada análisis. |
| Antes de entrenar el clasificador | Fijar qué errores y demoras son aceptables para la demostración y qué casos deben producir abstención. | Revisar los escenarios y criterios de aceptación antes de usar la partición de prueba. |
| Antes de integrar la calibración a bordo | En la cohorte se usa la media de los primeros 120 s de reposo válido por sesión. Falta definir la vigencia y recuperación de una referencia entre sesiones reales. | Compartir las transformaciones entre entrenamiento e inferencia y comprobar cuándo corresponde mostrar «calibrando». |
| Antes de elegir un modelo para la demo | Criterios de aceptación del clasificador y de sus alertas, incluida la tolerancia a falsas alertas y a la demora. | Fijar criterios antes de abrir la prueba reservada. Ajustar la abstención con validación. Mantener identificado el método que mejor funcione para el pronóstico. |
| Antes de integrar la interfaz | Escala del autorreporte, alta/cierre/reconocimiento de episodios, texto de revisión y presentación cuando solo algunos componentes son evaluables. | Revisar un episodio completo con el equipo y los términos de salud con un mentor. |
| Al revisar los recursos anunciados para el 13 de noviembre | Archivos accesibles, unidades, permisos, población, etiquetas y utilidad para cada componente. El evento DONKI y la serie de referencia RR-1 ya están disponibles. | Registrar qué recurso cambia una entrada, una regla o una pantalla y qué aporta solo contexto. |

El alcance implementado hoy es el de la **versión 0.1**. Reproduce FC y FR de un registro BIDMC, simula actividad y ambiente, aplica reglas y muestra el último pulso como referencia a 60 s. El entrenamiento, la calibración personal, el autorreporte, la persistencia en disco y el enlace con Tierra corresponden al MVP planificado.
