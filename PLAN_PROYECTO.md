Propuesta de proyecto — NASA Space Apps 2026
==========================================

Documento histórico de exploración del 26 de octubre. Las menciones al 28 de octubre reflejan el calendario conocido entonces. El equipo sitúa ahora la publicación de los recursos el 13 de noviembre. Para tomar decisiones de implementación, usar el [alcance vigente](MVP_ASTRO_VITALS.md) y el [contrato de datos](CONTRATO_DE_DATOS.md).

Documento de exploración preparado el 26 de octubre de 2026. Equipo de Cajamarca, Perú, con conocimientos generales de software, datos, diseño y electrónica, sin especialista en salud. Número de integrantes y horas efectivas pendientes. Nombre de trabajo: **Órbita — asistente de recuperación fisiológica**.

**Decisión propuesta.** Explorar una aplicación para un astronauta dentro del hábitat que responda: «¿Mi recuperación después de la actividad sigue mi patrón habitual?». Mostrar cambios sostenidos, su evidencia y un siguiente paso de revisión. El alcance definitivo depende del enunciado completo y de los datos disponibles.

El resumen oficial indexado pide reunir indicadores de salud y permitir al astronauta evaluar y actuar sobre su estado. Pude consultar ese resumen mediante búsqueda; la apertura directa del sitio devolvió un error 502. No se ha verificado todavía el enunciado completo ni sus requisitos detallados. [Desafío oficial](https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/).

La publicación anunciada para el 28 de octubre corresponde a enunciados completos y recursos; no garantiza telemetría clínica etiquetada. La fecha aparece en la [página oficial de Santiago, República Dominicana](https://www.spaceappschallenge.org/2026/local-events/santiago-dominican-republic/), utilizada como fuente del calendario, no como sede del equipo. El [evento global](https://www.spaceappschallenge.org/2026/) está previsto para el 14 y 15 de noviembre. El horario y las entregas locales de Cajamarca deben confirmarse con su organización.

**Problema y utilidad.** Un astronauta termina una sesión de ejercicio. Dispone de mediciones, pero necesita entender si su evolución coincide con la habitual para una actividad comparable, si una señal tiene problemas y qué información conviene registrar para revisión. La hipótesis del proyecto es que combinar contexto, referencia personal y explicación puede mejorar esa interpretación. Esto debe comprobarse con pruebas de uso; no se presenta como un beneficio clínico demostrado.

NASA documenta investigación con chalecos para pulso y respiración, bandas para temperatura y otros dispositivos. Por eso el concepto puede apoyarse en dispositivos del hábitat, sin asumir que todos los trajes tienen los mismos sensores. [Wearable Tech for Space Station Research](https://www.nasa.gov/humans-in-space/wearable-tech-for-space-station-research/).

El funcionamiento local aporta valor para futuras misiones: NASA describe demoras de comunicación de hasta 20 minutos en un sentido desde Marte. El escenario no presupone esa demora en la ISS ni en todas las misiones. [The Human Body in Space](https://www.nasa.gov/humans-in-space/the-human-body-in-space/).

**Experiencia central.** La aplicación reconoce o permite marcar el fin de una actividad. Compara las mediciones posteriores con sesiones personales comparables y presenta uno de estos estados: patrón esperado, desviación sostenida o datos insuficientes. Cada estado incluye contexto, evolución y calidad de las señales. «Patrón esperado» describe las señales analizadas; no certifica la salud global del usuario.

Ejemplo ilustrativo de mensaje: «La frecuencia cardíaca permanece por encima de tu referencia para esta fase de recuperación. La señal respiratoria también se aparta de su patrón. Revisa la medición y registra cómo te sientes». La interfaz debe poder explicar qué cambió, desde cuándo y respecto a qué referencia.

**Datos mínimos propuestos.**

| Entrada | Uso en el prototipo | Condición |
| --- | --- | --- |
| Frecuencia cardíaca | Tendencia y recuperación | Registrar unidades, tiempo y procedencia |
| Frecuencia respiratoria | Contexto fisiológico complementario | Solo si existe en la fuente utilizada |
| Actividad y fin de ejercicio | Comparar situaciones semejantes | Puede declararse manualmente en la demo |
| Calidad y antigüedad de cada señal | Detectar pérdida de datos y limitar conclusiones | Basarse en banderas disponibles o reglas técnicas documentadas |
| Autorreporte breve | Registrar esfuerzo percibido y malestar | No convertirlo automáticamente en diagnóstico |

SpO₂ o temperatura serían extensiones si el recurso las justifica. La temperatura cutánea no equivale a temperatura central. Una tabla de valores por segundo tampoco permite reconocer todos los artefactos del sensor.

**MVP para construir durante el evento.**

1. Una pantalla de estado con dos señales, actividad, tendencia y disponibilidad de datos.
2. Una explicación de cada episodio: valores observados, referencia, duración y señales que contribuyeron a la alerta.
3. Un formulario breve de autorreporte y una secuencia ilustrativa de revisión: verificar señal, repetir medición cuando corresponda y registrar el episodio para el responsable médico.
4. Un historial local exportable con mediciones, contexto y eventos.
5. Un panel separado para reproducir registros y activar escenarios sintéticos identificados como tales.

La secuencia de revisión requiere asesoría sanitaria antes de convertirse en un protocolo de uso real. Para el hackatón puede mantenerse explícitamente ilustrativa. Conviene solicitar a un mentor de salud una revisión del caso, los términos y las acciones; esa revisión puntual no constituye validación clínica.

La primera versión funciona con un perfil simulado y procesamiento local. Autenticación, cuentas múltiples, integración física de varios sensores y asistente conversacional pueden esperar. Una interfaz web adaptable a tablet o portátil reduce el trabajo de implementación.

**Componente analítico y modelo.** Separar tres responsabilidades:

1. Calidad de datos: reconocer señales ausentes, antiguas o técnicamente inválidas. Una señal fallida no debe ocultar una alerta respaldada por otra señal válida.
2. Referencia explicable: comparar curvas de recuperación o tendencias con una línea base personal condicionada por actividad. Si falta historia, mostrar «calibrando». No actualizar automáticamente la referencia con episodios señalados como anómalos.
3. Pronóstico exploratorio: si hay series suficientes, entrenar una regresión sencilla que estime la frecuencia cardíaca a 30–60 segundos a partir del historial reciente y el contexto disponible. Comparar contra mantener el último valor y extrapolar una tendencia simple.

Un objetivo de entrenamiento concreto sería «frecuencia cardíaca dentro de 60 segundos», con entradas calculadas exclusivamente a partir del pasado. El horizonte se ajusta a la duración y calidad de los datos. Si el modelo no mejora la referencia simple en datos reservados, conservar la referencia simple.

Un buen pronóstico numérico no demuestra anticipación de una emergencia. Un puntaje de anomalía tampoco es una probabilidad de enfermedad. Las alertas de demostración deben tener persistencia, criterios explícitos y parámetros identificados como experimentales. La personalización por sí sola no garantiza seguridad médica; un sistema clínico requeriría además criterios de seguridad revisados por especialistas.

**Estrategia de datos y decisión del 28 de octubre.**

| Recurso | Uso razonable | Límite relevante |
| --- | --- | --- |
| Recursos oficiales del desafío | Determinar el caso final y sustentar decisiones espaciales | Todavía no se conocen estructura, variables, etiquetas ni permisos |
| [PPG-DaLiA, UCI](https://archive.ics.uci.edu/dataset/495/ppg) | Explorar señales y movimiento durante actividades de 15 participantes; estudiar estimación de pulso | No contiene por ello diagnósticos ni etiquetas de recuperación anormal espacial; descarga aproximada de 2,7 GB |
| [BIDMC, PhysioNet](https://physionet.org/content/bidmc/1.0.0/) | Reproducir pulso, respiración y SpO₂; probar ingestión y pronóstico técnico | Son 53 registros de 8 minutos de pacientes hospitalarios, no astronautas haciendo ejercicio |
| Escenarios sintéticos propios | Verificar interfaz, pérdida de datos, alertas y flujo completo | Demuestran funcionamiento del software en simulación, no eficacia médica |

PPG-DaLiA incluye ECG como referencia de pulso, PPG y acelerometría; su licencia publicada es CC BY 4.0. BIDMC ofrece parámetros a 1 Hz y archivos CSV bajo Open Data Commons Attribution. Cada fuente requiere conservar su atribución y revisar compatibilidad con la entrega. No mezclar datos de poblaciones diferentes como si fueran equivalentes.

El 28, revisar: acceso real, licencia, variables, unidades, frecuencia, duración, identificador de persona/sesión, actividad, etiquetas y volumen. La decisión sería:

- Si hay actividad y recuperación suficientes: mantener el caso de recuperación personal.
- Si solo hay series fisiológicas: acotar a monitoreo de tendencias y calidad, y evaluar pronóstico técnico sin afirmar recuperación anormal.
- Si predominan documentos u otros tipos de datos: adaptar el caso al recurso y demostrar la plataforma mediante simulación transparente.

Los datos y documentos NASA deben influir en decisiones concretas del producto. Registrar qué recurso justifica cada señal, escenario o requisito, y qué parte proviene de datos terrestres o simulados.

**Demo propuesta, de tres minutos.**

| Momento | Escenario | Qué debe quedar claro |
| --- | --- | --- |
| 0:00–0:30 | Presentar astronauta y actividad | Pregunta de recuperación y referencia personal |
| 0:30–1:05 | Recuperación habitual | El sistema considera el contexto del ejercicio |
| 1:05–1:55 | Desviación persistente inyectada | Explica señales y duración; permite registrar contexto y abrir revisión |
| 1:55–2:25 | Pérdida de un sensor | Muestra datos insuficientes o análisis parcial, sin inventar mediciones |
| 2:25–3:00 | Continuar sin internet y exportar episodio | Procesamiento local y resumen disponible para revisión posterior |

Todos los escenarios muestran procedencia y tiempo de simulación. Se puede acelerar la reproducción indicando el factor de velocidad. Conviene usar un control de escenarios para la presentación y reservar otros escenarios para las pruebas, de modo que el comportamiento no dependa solo del guion ensayado.

**Criterios de éxito técnico.** Medir eventos sintéticos detectados frente a inyectados, falsas alertas por hora simulada y demora de detección. Verificar señales ausentes, mensajes claros y continuidad local. Si hay pronóstico, medir error absoluto medio en unidades de pulso frente a las referencias simples.

Reservar participantes o sesiones completas para evaluación; evitar que ventanas superpuestas crucen entrenamiento y prueba. Para personalización, calibrar con un segmento anterior y evaluar en un segmento posterior independiente. Separar también las semillas y variantes del simulador. Los resultados sobre simulación se reportan como tales.

Una prueba pequeña de uso puede medir cuánto tarda alguien en identificar qué cambió, qué datos faltan y cuál es el siguiente paso mostrado. Esto evalúa comprensión, no seguridad clínica. No fijar porcentajes de precisión prometidos antes de medir.

**Organización del trabajo.** Repartir cuatro funciones, combinables según el tamaño real del equipo: interfaz y experiencia; datos y análisis; integración y simulación; investigación, validación y presentación. Una persona debe cuidar la integración y otra las fuentes y límites de las afirmaciones, aunque también programen.

Antes del evento: explorar el reto, estudiar datos, aprender herramientas, identificar mentoría sanitaria y confirmar las reglas locales sobre preparación. La orientación de [Space Apps Tel Aviv 2026](https://space.tau.ac.il/SpaceApps2026), publicada por su organizador, distingue exploración previa de construcción del proyecto durante el hackatón. Este documento es una propuesta de preparación; conviene contrastar el alcance permitido con Cajamarca.

Durante el evento, distribuir el tiempo efectivo aproximadamente así: 15% cerrar caso y datos; 35% construir el flujo completo con reglas explicables; 20% añadir/evaluar el modelo si procede; 15% probar e integrar; 15% preparar demo, fuentes y entrega. Al cumplirse la mitad del tiempo ya debe funcionar un recorrido completo. Si no funciona, reducir extensiones y asegurar ese recorrido.

**Presentación propuesta.** «Órbita ayuda a astronautas a interpretar su recuperación tras una actividad. Combina señales, contexto y una referencia personal para explicar cambios sostenidos y conservar un registro revisable, incluso sin conexión. Nuestro prototipo demuestra ese flujo y mide su comportamiento técnico; el siguiente paso es evaluarlo con datos representativos y especialistas».

La contribución demostrable será un flujo de interpretación personal, explicable y local. La utilidad clínica, su adaptación a distintas condiciones de misión y cualquier uso terrestre requerirán evaluación posterior. Para un equipo sin formación sanitaria, esta delimitación permite aportar desde software y datos sin basar el proyecto en diagnósticos que aún no puede sustentar.
