ASTRO-VITALS — MVP y estrategia de presentación
===============================================

Alcance revisado el 3 de noviembre de 2026 para el equipo de Cajamarca, Perú. Sustituye como guía de alcance a la exploración inicial de Órbita. El equipo reúne conocimientos de software, datos, diseño y electrónica. Quedan pendientes el número de integrantes, las horas disponibles y la revisión de los mensajes por un mentor de salud.

La [versión 0.1](prototype/README.md) implementa la pasarela, el servicio a bordo y la consola del astronauta. El MVP previsto añade modelos Random Forest, almacenamiento SQLite y un nodo Tierra con vista web. El [contrato de datos](CONTRATO_DE_DATOS.md) define las entradas, salidas y fuentes por tarea. La [arquitectura](ARQUITECTURA_TECNICA.md) define cómo integrarlas.

**Concepto acordado.** Un asistente de monitoreo para astronautas que reúne biometría, actividad y contexto ambiental; genera hipótesis diagnósticas orientativas en escenarios de demostración; explica su evidencia y mantiene un registro compartible con Tierra durante retrasos o interrupciones de comunicación. Incluye predicción experimental y un escenario de tormenta solar.

La meta del MVP es demostrar esa experiencia integrada. Las hipótesis y proyecciones producidas con escenarios sintéticos se presentan como resultados de simulación. El equipo revisará el caso con los recursos anunciados para el 13 de noviembre de 2026.

**Premios que orientan el diseño.** Las categorías y descripciones de esta tabla proceden de las tres imágenes de Space Apps Cajamarca compartidas por el usuario. La prioridad es una recomendación de planificación, no una probabilidad de ganar ni una confirmación de elegibilidad, ponderaciones o mecánica de selección local/global.

| Categoría | Prioridad propuesta | Qué tendría que demostrar ASTRO-VITALS |
| --- | --- | --- |
| Best Use of Technology | Principal | Integración funcional de señales, inferencia local, explicación y sincronización con comunicación interrumpida |
| Best Use of Storytelling | Secundaria | Una historia comprensible desde nave y Tierra que muestre cómo se utiliza un dato abierto real |
| Best Use of Data | Condicionada a los recursos disponibles | Un uso sustantivo, trazable y útil de datos NASA en el procesamiento o interpretación; conservar procedencia y transformaciones |
| Galactic Impact | Potencial complementario | Problema relevante, usuario definido y ruta plausible de evaluación/adopción; separar beneficios potenciales de los demostrados |
| Best Use of Science | Potencial complementario | Hipótesis explícitas, comparación con referencias, experimentos reproducibles y límites bien descritos |
| Most Inspirational | Complementaria a la narrativa | Conectar con la experiencia humana de recibir apoyo cuando la comunicación es limitada |
| Local Impact | Exploración futura | Investigar con actores locales si el funcionamiento sin conexión resuelve una necesidad real en Cajamarca |
| Best Mission Concept | Afinidad parcial con el alcance actual | Explicar dónde opera el sistema, sus recursos, usuarios y restricciones de misión |
| Art & Technology | Afinidad secundaria | Una contribución creativa sustantiva que mejore la experiencia; una estética espacial por sí sola no es la propuesta |
| Global Community | Afinidad menor por ahora | Una conexión real entre comunidades; las dos vistas nave–Tierra por sí solas no demuestran esa dimensión |

La estrategia es construir una sola solución coherente. Tecnología y narrativa se refuerzan con las mismas funciones; no requieren crear productos adicionales para cada premio. El rigor de los datos y las mediciones se mantiene como criterio transversal.

**Promesa para presentar.** «ASTRO-VITALS ayuda a una tripulación a interpretar señales de salud y del entorno cuando Tierra recibe información tarde. Nuestro prototipo integra datos, genera hipótesis orientativas, explica las alertas y conserva los episodios aun sin conexión».

**Alcance funcional.**

| Módulo | Entrega mínima | Evidencia observable |
| --- | --- | --- |
| Vista astronauta | Pulso, respiración, actividad, calidad de señal y estado de comunicación | Datos se actualizan con tiempos, unidades y disponibilidad |
| Evaluación orientativa | Patrón simulado con evidencia, alternativas e información faltante. El astronauta puede registrar esfuerzo, malestar u observaciones. | El episodio indica qué cambió, durante cuánto tiempo y qué señal requiere revisión |
| Predicción experimental | FC a 60 s a partir del historial de FC y FR | Estimación identificada por método e instante. Error en bpm frente a referencias simples en registros reservados |
| Contexto de cabina | Canal de CO₂ simulado con origen identificado | Se puede comparar temporalmente con biometría sin afirmar causalidad aprendida inexistente |
| Tormenta solar | Evento histórico DONKI y dosímetro local simulado en canales separados | La alerta por exposición se fundamenta en lecturas locales simuladas |
| Vista Tierra e historial | Episodios recibidos, mediciones originales, explicación, tiempos y cola de entrega | Tras un corte, se recupera el registro sin duplicados ni confundir datos antiguos con actuales |
| Control de demostración | Reproducción a velocidad real, pausa y selección de escenarios reproducibles | El motor analiza únicamente la información disponible al final de la ventana |

Se usa un perfil ficticio, una TUI para el astronauta y una web para Tierra, conectadas a sus respectivos nodos. El flujo de hipótesis, revisión e historial es común a los escenarios. La simulación de comunicación representa un enlace con demora e interrupciones; no se presenta como una implementación real de la DSN.

**Datos, simulación y modelo.** La fusión de la demo reúne señales compatibles dentro de un escenario explícito. Registros reales pueden servir de base, indicando qué se modificó. Unir arbitrariamente personas terrestres con radiación de otra misión no produce ejemplos clínicos observados.

El generador ya produjo las sesiones con las cuatro clases de patrón definidas en el contrato y las etiquetas por ventana para entrenamiento y evaluación. Si faltan entradas o el clasificador se abstiene, la interfaz prevista comunicará el motivo. [Conjunto de fusión](data/fusion_simulada/README.md)

Una implementación inicial puede usar un clasificador pequeño con variables de tendencia y contexto. Las reglas revisan calidad, persistencia y límites configurados; el clasificador reconoce patrones; plantillas explicativas presentan observaciones y alternativas. Solo se muestran atribuciones calculadas realmente. Un porcentaje de clasificación sintética no se presenta como probabilidad de enfermedad.

En el clasificador, separar perfiles ficticios y semillas antes de generar ventanas. Reservar variantes de ruido, intensidad y pérdida de datos para evaluación. En el pronóstico, reservar personas o registros completos de BIDMC y comparar con mantener la última FC o extrapolar una tendencia.

La única variable que se pronostica es la FC a 60 s. Si se incluye una proyección ambiental a seis horas, se calculará por separado con una tasa de exposición supuesta y se mostrará ese supuesto.

**Escenario solar de bajo alcance.**

1. Cargar el evento histórico SEP de DONKI ya guardado. Mantener la fecha original separada del reloj de reproducción. [Evento seleccionado](data/donki/evento.json)
2. Mostrar el evento como contexto recibido desde una fuente externa. La aplicación conoce cuándo se recibió y cuánto tiempo ha transcurrido; no depende de una consulta en vivo para seguir funcionando.
3. Reproducir una serie independiente de dosímetro simulado, diferenciando tasa de dosis de dosis acumulada y conservando unidades consistentes. No derivar dosis personal directamente del evento DONKI.
4. Procesar las lecturas mediante el motor común de reglas y guardar un episodio con la evidencia que activó el aviso. Un evento solar remoto por sí solo no activa una conclusión médica.
5. Permitir «simular traslado al refugio»: cambiar la tasa según un supuesto explícito del escenario. La dosis acumulada no disminuye; puede aumentar más lentamente.
6. Si se muestra una proyección, indicar que depende de la tasa y duración supuestas. No se modelan propagación de partículas, blindaje real ni daño biológico para esta demo.

DONKI documenta eventos y análisis de clima espacial, incluidos SEP, y ofrece acceso programático. Su información se proporciona para investigación y prototipos. Fuente: [NASA CCMC — DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/).

**Escenarios a preparar.**

| Escenario | Comportamiento esperado del prototipo |
| --- | --- |
| Actividad con evolución fisiológica esperada | Reconocer el contexto y mostrar tendencias sin disparar una alerta solo por el nombre del escenario |
| Desviación fisiológica sostenida con cambio ambiental simulado | Presentar una hipótesis orientativa, sus observaciones, alternativas y revisión ilustrativa |
| Evento solar histórico con dosimetría simulada | Diferenciar contexto remoto y medición local; explicar la alerta ambiental y registrar la acción simulada |
| Variante transversal: señal ausente o contradictoria | Indicar qué falta y limitar las conclusiones de ese canal sin borrar alertas respaldadas por otros |

Las alteraciones de CO₂ y dosimetría se presentan en episodios separados. No se atribuyen cambios instantáneos de pulso a radiación ni se escenifican varias emergencias simultáneas para aumentar el dramatismo.

**Pruebas que sostienen la candidatura tecnológica.**

| Prueba | Evidencia que conservar | Límite de interpretación |
| --- | --- | --- |
| Desconexión | Inferencia y registro continúan con todos los recursos necesarios en local | Demuestra autonomía del prototipo en la prueba realizada |
| Reconexión | Comparación de episodios emitidos y recibidos, orden, identificadores y ausencia de duplicados | Demuestra la lógica de cola del simulador de enlace |
| Variantes reservadas | Matriz de resultados, falsas alertas por hora simulada y demora de detección | Describe rendimiento sobre escenarios sintéticos |
| Sensor defectuoso | Mensajes de datos insuficientes y conservación de otras alertas válidas | Describe manejo de fallos previstos |
| Pronóstico, si se entrena | Error en unidades de la señal frente a una referencia simple | No prueba anticipación de enfermedad |
| Comprensión | Prueba breve con alguien externo: identificar cambio, fuente, antigüedad y siguiente paso | Evalúa claridad de uso, no seguridad clínica |

No se prometen porcentajes de precisión ni tiempos de inferencia antes de medir. La ficha de resultados incluye entorno de ejecución, escenario, referencia usada y limitaciones.

**Narrativa de demo propuesta.** El ensayo dura unos tres minutos, ajustables al tiempo que confirme Cajamarca. Una misma astronauta ficticia conecta dos escenas breves. A velocidad real, se puede cargar una ventana de historia previa identificada para que el modelo tenga contexto al comenzar. La pantalla conserva la fecha del evento histórico.

| Tiempo aproximado | Acción | Qué se comunica |
| --- | --- | --- |
| 0:00–0:20 | Presentar a la astronauta y mostrar la información que tiene Tierra | Necesidad concreta y antigüedad de la información |
| 0:20–1:10 | Reproducir el episodio fisiológico y abrir la hipótesis orientativa | El motor usa señales, actividad y evidencia para interpretar el escenario |
| 1:10–1:30 | Interrumpir el enlace y registrar una revisión a bordo | La autonomía resuelve una restricción observable |
| 1:30–2:20 | Cambiar explícitamente al escenario solar, abrir el evento NASA y reproducir el dosímetro | El dato abierto aporta contexto; la exposición local está identificada como simulada |
| 2:20–2:40 | Simular el refugio y mostrar la proyección de exposición | Decisión del escenario y efecto bajo supuestos visibles |
| 2:40–3:00 | Reconectar y mostrar el episodio recibido en Tierra y una métrica medida | Registro trazable y evidencia del funcionamiento |

Para Storytelling, el vínculo con los datos abiertos debe verse: evento elegido, observación disponible, cómo entra en la historia y qué puede o no inferirse de él. La narrativa evita resultados médicos inventados, como afirmar que se evitó una muerte. El desenlace demostrable es que la tripulación interpretó la información, registró su revisión y conservó continuidad durante el corte.

**Best Use of Data.** El 13 de noviembre se revisará si un recurso oficial contribuye a una comparación, estimación o interpretación concreta. Se documentarán su origen, condiciones de acceso, variables, transformaciones, función y límites.

Los ejemplos de pronóstico están preparados con BIDMC y separados por participante. PPG-DaLiA, MMASH y WESAD tienen tablas locales para posibles extensiones de actividad, sueño y estrés. [Resultados de preparación](data/bidmc/README.md) · [Fuentes y uso por tarea](DATOS_ALTERNATIVOS.md)

NASA-STD-3001 puede fundamentar reglas específicas si se identifica el requisito, revisión, unidades, exposición y contexto aplicables. La referencia no valida las hipótesis del modelo ni sustituye su evaluación. [NASA — Human Spaceflight Standards](https://www.nasa.gov/ochmo/human-spaceflight-and-aviation-standards/).

**Impacto y conexión con Cajamarca.** Como hipótesis de transferencia futura, el procesamiento local y el envío diferido podrían ser útiles en situaciones terrestres de conectividad limitada. Para aspirar a Local Impact habría que conversar con personal o instituciones locales y describir una necesidad comprobada, condiciones de uso y evaluación. Esta hipótesis no implica que ya exista un piloto, validación o beneficio sanitario. El MVP conserva el contexto espacial; no añade un segundo producto terrestre.

**Organización y recortes.** Repartir funciones combinables: interfaz/narrativa, datos/modelo, simulador/integración y evaluación/fuentes. La revisión de un mentor sanitario se centra en los términos y la secuencia ilustrativa; no se presenta como validación clínica. Antes del evento se estudian fuentes y herramientas y se confirma con la organización el alcance permitido de preparación.

Durante la construcción, distribuir aproximadamente 15% para caso y datos, 35% para el recorrido completo, 20% para modelo y evaluación, 15% para integración y pruebas y 15% para ensayo y entrega. A mitad del tiempo debe funcionar un episodio completo en las dos vistas. Si el tiempo se reduce, priorizar hipótesis orientativa explicada, episodio solar mínimo, continuidad local y sincronización; reducir integraciones en vivo, vistas adicionales y complejidad del modelo.

**Entregables revisables.** Aplicación ejecutable, demo breve, instrucciones reproducibles, esquema del flujo de datos, fuentes/licencias, ficha de evaluación, supuestos del simulador y explicación de qué parte es dato histórico, sensor simulado o estimación. La selección de premios orienta estas evidencias y no exige modificar el producto para cubrir todas las categorías.
