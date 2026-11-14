"""Glosario orientativo y educativo de señales y niveles para ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

SIGNAL_GLOSSARY: dict[str, dict[str, str]] = {
    "hr": {
        "what_is": "Frecuencia cardíaca expresada en latidos por minuto (bpm); en registros BIDMC proviene del canal HR derivado de ECG.",
        "why_it_matters": "Permite observar de forma orientativa el esfuerzo físico, la recuperación posterior a una actividad y variaciones sostenidas frente a la línea base personal.",
        "what_to_do": "Interpretar siempre junto con la actividad declarada (reposo, ejercicio o recuperación), comprobar contacto del sensor y observar la tendencia.",
        "limitations": "Varía según persona, postura, estrés y movimiento; un valor fuera del umbral de demostración es una hipótesis orientativa (escenario simulado) y no un diagnóstico.",
    },
    "rr": {
        "what_is": "Frecuencia respiratoria medida en respiraciones por minuto (resp/min).",
        "why_it_matters": "Aporta contexto complementario al pulso para distinguir la respuesta esperada al ejercicio de cambios asociados al entorno de cabina.",
        "what_to_do": "Comparar la lectura con el CO₂ de cabina y la fase de actividad actual; revisar el sensor si aparecen saltos bruscos o huecos de señal.",
        "limitations": "Es sensible a artefactos de movimiento o habla; en reproducciones históricas BIDMC carece de contexto espacial y de CO₂.",
    },
    "co2": {
        "what_is": "Presión parcial de dióxido de carbono (ppCO₂) en la cabina o módulo ocupado, medida en mmHg.",
        "why_it_matters": "En hábitats cerrados sin convección natural el CO₂ puede acumularse alrededor de la tripulación; el promedio de 1 h de 3.0 mmHg (NASA OCHMO-TB-004) sirve como referencia operativa del proyecto, con síntomas de cefalea reportados desde 2.3 mmHg.",
        "what_to_do": "Comprobar ventilación y depuradores de cabina, contrastar con la frecuencia respiratoria, reducir carga física en la simulación y registrar una observación.",
        "limitations": "Si una fuente entrega ppm se requiere la presión total conocida para convertir a mmHg; una lectura instantánea no equivale al promedio de 1 h ni constituye diagnóstico médico.",
    },
    "dose_rate": {
        "what_is": "Tasa instantánea de dosis equivalente ambiental leída por el dosímetro simulado, en microsieverts por hora (μSv/h).",
        "why_it_matters": "Ayuda a vigilar exposiciones simuladas durante escenarios de tormenta solar e integrar la dosis acumulada (μSv) sobre intervalos válidos.",
        "what_to_do": "Evaluar por separado de las señales fisiológicas; en escenario solar simulado, activar el refugio de demostración y comprobar la cobertura de integración.",
        "limitations": "Es una fuente simulada independiente del evento histórico DONKI; no modela blindaje físico real, propagación de partículas ni efectos biológicos.",
    },
    "spo2": {
        "what_is": "Saturación periférica de oxígeno estimada mediante oximetría de pulso, en porcentaje (%).",
        "why_it_matters": "Ofrece una referencia orientativa sobre el aporte de oxígeno en registros compatibles y pantallas informativas del sistema.",
        "what_to_do": "Revisar ajuste del oxímetro, temperatura periférica y estado simulado de suministro de oxígeno cuando la fuente proporcione este canal.",
        "limitations": "Sensible a movimiento, perfusión baja o luz ambiente; en esta versión es informativa y no participa en los modelos de pronóstico ni clasificación.",
    },
    "bp_sys": {
        "what_is": "Presión arterial sistólica estimada en milímetros de mercurio (mmHg), correspondiente al máximo de presión del ciclo cardíaco.",
        "why_it_matters": "Contextualiza cambios cardiovasculares y de desplazamiento de fluidos en ejercicios educativos de adaptación espacial.",
        "what_to_do": "Registrar la medición en reposo estable y compararla con la presión diastólica y el estado de hidratación simulado.",
        "limitations": "Depende de la postura y del sensor utilizado; no forma parte del contrato mínimo de telemetría ni del motor de reglas actual.",
    },
    "bp_dia": {
        "what_is": "Presión arterial diastólica estimada en milímetros de mercurio (mmHg), correspondiente a la presión basal entre latidos.",
        "why_it_matters": "Complementa a la lectura sistólica para seguir el comportamiento hemodinámico orientativo en escenarios de demostración.",
        "what_to_do": "Evaluar junto con la presión sistólica tras pausar actividad intensa y anotar cambios persistentes para revisión posterior.",
        "limitations": "Una lectura aislada puede fluctuar por movimiento o colocación del sensor; tiene carácter exclusivamente informativo en este prototipo.",
    },
    "temp_c": {
        "what_is": "Temperatura corporal o cutánea estimada por sensor portátil, expresada en grados Celsius (°C).",
        "why_it_matters": "Aporta contexto orientativo sobre carga térmica, regulación del traje o módulo y esfuerzo físico acumulado.",
        "what_to_do": "Comprobar el contacto térmico del sensor y el estado simulado de refrigeración del traje antes de interpretar desviaciones.",
        "limitations": "La temperatura cutánea no equivale a la temperatura central y está influida por el microclima del traje o desplazamientos del sensor.",
    },
    "hydration_pct": {
        "what_is": "Indicador orientativo de estado de hidratación expresado en porcentaje (%) dentro de escenarios simulados.",
        "why_it_matters": "Recuerda vigilar el balance de líquidos durante jornadas prolongadas o sesiones con carga térmica y actividad física.",
        "what_to_do": "Contrastar con el registro simulado de ingesta de agua y observar junto con pulso y presión estimados.",
        "limitations": "Es una referencia ilustrativa de simulación y no una medición bioquímica real; no alimenta reglas automáticas ni modelos ML.",
    },
}

LEVEL_GLOSSARY: dict[str, dict[str, str]] = {
    "normal": {
        "label": "ESTABLE",
        "color": "#66e0bd",
        "meaning": "Hipótesis orientativa (escenario simulado): las señales disponibles permanecen dentro de los márgenes de demostración para la actividad declarada.",
        "what_to_do": "Continuar el seguimiento periódico y mantener actualizado el contexto de actividad en la consola.",
        "limitations": "Refleja únicamente los canales activos en la ventana reciente; no certifica el estado general de salud.",
    },
    "watch": {
        "label": "REVISAR",
        "color": "#ffca73",
        "meaning": "Hipótesis orientativa (escenario simulado): una o más señales muestran una variación moderada respecto a los umbrales de demostración o referencia personal.",
        "what_to_do": "Confirmar la actividad actual, verificar el ajuste del sensor, observar la tendencia en los próximos minutos y anotar contexto si persiste.",
        "limitations": "Los umbrales son ilustrativos y pueden activarse por cambios de postura, transición tras ejercicio o ruido de medición.",
    },
    "alert": {
        "label": "ATENCIÓN",
        "color": "#ff8d84",
        "meaning": "Hipótesis orientativa (escenario simulado): las lecturas superan los límites configurados de demostración para cabina, dosimetría o respuesta fisiológica.",
        "what_to_do": "Revisar la evidencia mostrada, comprobar sensores, ventilación o refugio simulado según corresponda, reconocer el aviso y registrar la observación.",
        "limitations": "Reconocer el aviso deja constancia de lectura pero no resuelve la condición; no equivale a un diagnóstico médico ni confirma un incidente real.",
    },
    "unknown": {
        "label": "SIN EVALUACIÓN",
        "color": "#a4b2ca",
        "meaning": "Faltan lecturas recientes, hay señales obligatorias ausentes, se desconoce la actividad o el registro histórico carece de contexto espacial.",
        "what_to_do": "Revisar conexión con la pasarela, calidad de sensores y contexto de actividad antes de interpretar los últimos valores visibles.",
        "limitations": "Los huecos nunca se rellenan con cero; ante cobertura insuficiente o datos antiguos, el sistema se abstiene de emitir evaluación.",
    },
}


def get_glossary() -> dict[str, Any]:
    """Retorna el glosario completo de señales y niveles orientativos."""
    return {
        "signals": {key: dict(entry) for key, entry in SIGNAL_GLOSSARY.items()},
        "levels": {key: dict(entry) for key, entry in LEVEL_GLOSSARY.items()},
    }
