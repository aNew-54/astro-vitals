"""Glosario orientativo en lenguaje sencillo para el tripulante en ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

SIGNAL_GLOSSARY: dict[str, dict[str, str]] = {
    "hr": {
        "what_is": "Frecuencia cardíaca: cuántas veces late tu corazón por minuto (bpm) según el sensor de tu traje o banda pectoral.",
        "why_it_matters": "Te ayuda a distinguir si tu cuerpo está respondiendo a un esfuerzo físico normal o si tu pulso sigue acelerado mientras descansas.",
        "what_to_do": "Compáralo con lo que estás haciendo ahora (descanso, ejercicio o recuperación) y revisa que la banda del traje haga buen contacto.",
        "limitations": "El pulso cambia de forma natural con el movimiento, la postura o el estrés; sirve como guía orientativa y nunca sustituye una revisión médica.",
    },
    "rr": {
        "what_is": "Ritmo respiratorio: cuántas respiraciones completas haces por minuto (resp/min).",
        "why_it_matters": "Junto con el pulso, te permite ver si estás respirando más rápido por ejercicio o por aire viciado en tu módulo o casco.",
        "what_to_do": "Comprueba la calidad del aire en cabina y confirma tu nivel de esfuerzo actual; si el número salta sin sentido, revisa la cinta torácica.",
        "limitations": "Hablar, toser o acomodarte el traje puede alterar temporalmente esta lectura.",
    },
    "co2": {
        "what_is": "Aire viciado en cabina o casco (dióxido de carbono, ppCO₂), medido en milímetros de mercurio (mmHg).",
        "why_it_matters": "En el espacio el aire no circula solo si no hay ventilación constante; el promedio de 1 h de 3.0 mmHg (NASA OCHMO-TB-004) es el límite operativo de referencia, y desde 2.3 mmHg ya puede aparecer dolor de cabeza o fatiga.",
        "what_to_do": "Revisa los ventiladores y filtros purificadores de aire, reduce el esfuerzo físico y avisa si notas pesadez o dolor de cabeza.",
        "limitations": "Una subida corta no siempre refleja el promedio de 1 h; siempre interpreta este valor junto con cómo te sientes y el estado del sistema de aire.",
    },
    "dose_rate": {
        "what_is": "Radiación espacial instantánea que atraviesa tu zona actual o traje, medida en microsieverts por hora (μSv/h).",
        "why_it_matters": "Te avisa a tiempo si aumenta la radiación externa durante una tormenta solar para protegerte dentro de una zona blindada.",
        "what_to_do": "Si sube de golpe, sigue el protocolo de refugio hacia el área más protegida de la nave o hábitat y vigila la dosis total acumulada.",
        "limitations": "Es una referencia orientativa de exposición en cabina y no mide efectos biológicos personales.",
    },
    "spo2": {
        "what_is": "Oxígeno en sangre (SpO₂): porcentaje (%) de oxígeno que está llegando a tu cuerpo según el sensor óptico del traje o guante.",
        "why_it_matters": "Confirma que estás recibiendo oxígeno suficiente dentro del casco o módulo.",
        "what_to_do": "Si baja respecto a tu valor habitual, revisa las manos frías o el ajuste del sensor y comprueba el suministro de oxígeno del traje.",
        "limitations": "El movimiento brusco o el frío en los dedos puede hacer que el sensor marque lecturas inestables.",
    },
    "bp_sys": {
        "what_is": "Presión arterial máxima (sistólica, mmHg) cuando el corazón impulsa la sangre en cada latido.",
        "why_it_matters": "Ayuda a observar cómo se adapta tu circulación a la ingravidez, el esfuerzo físico o la falta de líquidos.",
        "what_to_do": "Mídela cuando estés en calma, compárala con tu valor mínimo (diastólica) y recuerda mantener una buena hidratación.",
        "limitations": "Cambia según tu postura y el ajuste del brazalete; es solo una guía de apoyo en cabina.",
    },
    "bp_dia": {
        "what_is": "Presión arterial mínima (diastólica, mmHg) cuando el corazón descansa entre un latido y el siguiente.",
        "why_it_matters": "Complementa la presión máxima para tener una idea general de tu circulación durante la jornada.",
        "what_to_do": "Obsérvala junto a la presión máxima después de descansar unos minutos si acabas de hacer ejercicio.",
        "limitations": "Una lectura aislada puede variar por movimiento del brazo o colocación del sensor.",
    },
    "temp_c": {
        "what_is": "Temperatura corporal medida por el parche térmico del traje o cabina, en grados Celsius (°C).",
        "why_it_matters": "Te permite notar a tiempo si estás reteniendo calor dentro del traje espacial durante una tarea exigente o si hace demasiado frío.",
        "what_to_do": "Revisa el sistema de enfriamiento por líquido del traje o la ventilación de cabina y asegúrate de que el sensor esté bien adherido.",
        "limitations": "La temperatura sobre la piel refleja también el microclima del traje y no siempre coincide con la temperatura interna exacta.",
    },
    "hydration_pct": {
        "what_is": "Nivel estimado de hidratación corporal (%) durante la misión.",
        "why_it_matters": "En el espacio es fácil olvidarse de beber agua y deshidratarse durante caminatas o ejercicio intenso.",
        "what_to_do": "Si desciende por debajo de tu rango habitual, tómate una pausa para beber agua y registra tu rutina de hidratación.",
        "limitations": "Es una estimación orientativa para ayudarte a recordar beber agua, no un análisis de laboratorio.",
    },
}

LEVEL_GLOSSARY: dict[str, dict[str, str]] = {
    "normal": {
        "label": "ESTABLE",
        "color": "#66e0bd",
        "meaning": "Hipótesis orientativa (escenario simulado): todos tus sensores disponibles están dentro de los márgenes habituales para lo que estás haciendo.",
        "what_to_do": "Mantén tus rutinas de agua, ejercicio y descansos, y actualiza tu actividad si cambias de tarea.",
        "limitations": "Solo refleja los sensores conectados en este momento; sigue atento a cómo te sientes físicamente.",
    },
    "watch": {
        "label": "REVISAR",
        "color": "#ffca73",
        "meaning": "Hipótesis orientativa (escenario simulado): uno o más signos muestran un cambio moderado frente a tu nivel habitual.",
        "what_to_do": "Confirma si estás haciendo esfuerzo físico, verifica que los sensores estén bien puestos y vuelve a revisar en unos minutos.",
        "limitations": "Puede activarse brevemente al cambiar de postura o justo al terminar una actividad intensa.",
    },
    "alert": {
        "label": "ATENCIÓN",
        "color": "#ff8d84",
        "meaning": "Hipótesis orientativa (escenario simulado): el aire de cabina, la radiación o tus signos vitales superan los límites de seguridad configurados.",
        "what_to_do": "Revisa la causa señalada en pantalla, comprueba ventilación o muévete a zona de refugio si corresponde, y confirma que viste el aviso.",
        "limitations": "Confirmar el aviso deja constancia de lectura pero no soluciona el problema; revisa siempre cabina y sensores.",
    },
    "unknown": {
        "label": "SIN EVALUACIÓN",
        "color": "#a4b2ca",
        "meaning": "Faltan lecturas recientes de algún sensor esencial o todavía no has indicado qué actividad realizas.",
        "what_to_do": "Comprueba la conexión de los sensores del traje e indica en pantalla si estás en descanso, ejercicio o recuperación.",
        "limitations": "Cuando un sensor no envía datos, la pantalla muestra SIN SEÑAL (—) y nunca inventa números ni rellena con ceros.",
    },
}


def get_glossary() -> dict[str, Any]:
    """Retorna el glosario completo de señales y niveles orientativos."""
    return {
        "signals": {key: dict(entry) for key, entry in SIGNAL_GLOSSARY.items()},
        "levels": {key: dict(entry) for key, entry in LEVEL_GLOSSARY.items()},
    }
