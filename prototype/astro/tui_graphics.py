"""Motor gráfico en terminal (Braille Unicode 2x4, barras HUD, osciloscopio ECG y escáner anatómico)."""

from __future__ import annotations

import math
import re
from typing import Any

from rich.text import Text

from astro.glossary import LEVEL_GLOSSARY, SIGNAL_GLOSSARY

# Subpíxeles Braille 2x4: (fila 0..3)(col 0..1)
_BRAILLE_MAP: tuple[tuple[int, int], ...] = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

# (vmin, vmax, nom_lo, nom_hi, warn_lo, warn_hi, color, icon)
SIGNAL_VISUAL_META: dict[str, tuple[float, float, float, float, float, float, str, str]] = {
    "hr": (45.0, 165.0, 55.0, 110.0, 48.0, 135.0, "#38bdf8", "♥"),
    "rr": (6.0, 34.0, 10.0, 22.0, 8.0, 28.0, "#34d399", "≋"),
    "spo2": (88.0, 100.0, 95.0, 100.0, 92.0, 100.0, "#60a5fa", "◈"),
    "temp_c": (35.0, 39.5, 36.1, 37.5, 35.5, 38.2, "#fb923c", "🌡"),
    "bp_sys": (80.0, 170.0, 95.0, 130.0, 88.0, 145.0, "#a78bfa", "⇅"),
    "bp_dia": (45.0, 115.0, 60.0, 85.0, 52.0, 95.0, "#a78bfa", "⇅"),
    "co2": (0.0, 8.0, 0.0, 3.0, 0.0, 4.5, "#facc15", "☁"),
    "hydration_pct": (40.0, 100.0, 75.0, 100.0, 65.0, 100.0, "#2dd4bf", "💧"),
    "dose_rate": (0.0, 500.0, 0.0, 35.0, 0.0, 120.0, "#f472b6", "☢"),
}

_SEVERITY_STYLE: dict[str, tuple[str, str, str]] = {
    "nominal": ("● NOMINAL", "#4ade80", "#66e0bd"),
    "watch": ("▲ REVISAR", "#fbbf24", "#ffca73"),
    "alert": ("■ ALERTA", "#fb7185", "#ff8d84"),
    "missing": ("◌ SIN SEÑAL (—)", "#fbbf24", "#94a3b8"),
}

_ACTIVITY_LABELS: dict[str, str] = {
    "rest": "En reposo",
    "exercise": "En ejercicio",
    "recovery": "En recuperación",
    "unknown": "Sin declarar",
}

_SOURCE_LABELS: dict[str, str] = {
    "simulated": "Sensores del traje",
    "bidmc": "Registro biomédico",
    "declared": "Declarado a bordo",
}

_LEVEL_LABELS: dict[str, str] = {
    "normal": "ESTABLE",
    "watch": "REVISAR",
    "alert": "ATENCIÓN",
    "unknown": "EN ESPERA",
}

_PATTERN_INFO: dict[str, tuple[str, str, str]] = {
    "baseline_expected": (
        "● EN REPOSO NORMAL",
        "Tus signos coinciden con tu ritmo habitual de descanso.",
        "#4ade80",
    ),
    "activity_expected": (
        "▲ ESFUERZO FÍSICO ACTIVO",
        "Tu pulso y respiración suben de forma normal por tu actividad.",
        "#38bdf8",
    ),
    "persistent_recovery_deviation": (
        "▲ RECUPERACIÓN LENTA",
        "Tu pulso tarda en bajar tras el esfuerzo. Hidrátate y descansa.",
        "#fbbf24",
    ),
    "combined_cabin_physiology_pattern": (
        "■ EFECTO DE AIRE CARGADO (CO₂)",
        "Respiras más rápido mientras sube el CO₂. Revisa ventilación.",
        "#fb7185",
    ),
}

_REASON_LABELS: dict[str, str] = {
    "sin_datos": "esperando lecturas del traje",
    "datos_antiguos": "esperando señal reciente",
    "falta_hr": "sensor de pulso sin señal",
    "falta_rr": "sensor de respiración sin señal",
    "falta_co2": "sensor de CO₂ sin señal",
    "calibrando": "ajustándose con tus lecturas de descanso (tarda ~2 min)",
    "cobertura_insuficiente": "reuniendo 2 minutos continuos de señal",
    "cobertura_insuficiente_120s": "reuniendo 2 minutos continuos de CO₂",
    "no_evaluable": "esperando ventana válida de lectura",
    "modelo_no_disponible": "predicción en espera",
    "actividad_desconocida": "indica si estás en reposo o ejercicio para estimar tu patrón",
    "sin_linea_base": "calibrando tu ritmo personal de descanso",
    "confianza_insuficiente": "patrón en transición (observando)",
    "tendencia_no_ascendente": "aire estable, sin tendencia a subir",
    "baja_correlacion_lineal": "variación irregular, observando",
    "sin_lectura_co2": "sensor de CO₂ sin señal",
    "sin_lectura_dosimetria": "sensor de radiación sin señal",
    "insufficient_data": "aire estable (se calibra si varía el CO₂)",
}

_DISCARDED_EVIDENCE_FRAGMENTS: tuple[str, ...] = (
    "no equivale a una evaluación completa de salud",
    "el contexto de actividad explica la interpretación",
    "coinciden dos cambios del escenario; no demuestra causalidad",
    "la tasa no permite diagnosticar una lesión",
    "reproducción histórica; no se asigna una hipótesis espacial",
    "no es una referencia personal",
)

_TEXT_REWRITES: tuple[tuple[str, str], ...] = (
    ("señales dentro de los rangos de demostración para el contexto actual", "Tus signos vitales están dentro del rango normal para tu actividad actual"),
    ("sin cambios señalados por las reglas de demo", "Signos vitales estables en cabina"),
    ("patrón compatible con actividad simulada", "Signos acordes a tu actividad física"),
    ("pulso elevado respecto al umbral de demo sin ejercicio declarado", "Tu pulso está elevado sin haber registrado ejercicio"),
    ("tasa de radiación simulada por encima del umbral; revisar exposición y refugio", "Nivel de radiación elevado en el exterior; pasa a zona de refugio"),
    ("Radiación simulada · revisar exposición", "Radiación elevada · revisa protección"),
    ("Dosímetro simulado:", "Radiación medida:"),
    ("Probar el refugio del simulador y observar la tasa y el acumulado.", "Activa la protección de refugio y vigila la radiación acumulada."),
    ("Iniciar el simulador o la reproducción BIDMC.", "Verifica la conexión de los sensores del traje y cabina."),
    ("el límite de demo es", "el tiempo máximo de espera es"),
    ("las reglas de demo", "el monitoreo de cabina"),
    ("reglas de demostración v0.1 · sin modelo entrenado", "Reglas operativas a bordo"),
    ("reglas de demostración v0.1", "Reglas operativas a bordo"),
    ("regla de demo", "monitoreo de cabina"),
    ("umbral del entorno", "límite operativo en"),
    ("(valor null; no se sustituye por cero)", "(sensor sin señal)"),
    ("sin lectura (null)", "SIN SEÑAL (—)"),
    ("(share_behavioral=False)", "(solo visible para ti a bordo)"),
    ("share_behavioral=False", "privacidad a bordo activa"),
    ("BIDMC: registro clínico terrestre, sin CO₂, dosímetro ni actividad conocida.", "Registro de respaldo sin sensores de aire ni radiación de cabina."),
    ("reproducción de registro clínico terrestre BIDMC con contexto ambiental y de actividad ausente.", "Lectura de pulso y respiración sin sensores ambientales conectados."),
)


def humanize_activity(activity: Any) -> str:
    raw = str(activity or "unknown").strip().lower()
    return _ACTIVITY_LABELS.get(raw, "Sin declarar")


def humanize_source(source: Any) -> str:
    raw = str(source or "").strip().lower()
    return _SOURCE_LABELS.get(raw, "Cabina" if raw else "Sin señal")


def humanize_level(level: Any) -> str:
    raw = str(level or "unknown").strip().lower()
    return _LEVEL_LABELS.get(raw, "EN ESPERA")


def humanize_pattern(pattern: Any) -> tuple[str, str, str]:
    raw = str(pattern or "").strip()
    if raw in _PATTERN_INFO:
        return _PATTERN_INFO[raw]
    label = raw.replace("_", " ").upper() or "EN OBSERVACIÓN"
    return (f"● {label}", "Patrón fisiológico detectado en cabina.", "#66e0bd")


def humanize_reason(reason: Any) -> str:
    raw = str(reason or "").strip()
    if not raw:
        return "en observación"
    if raw in _REASON_LABELS:
        return _REASON_LABELS[raw]
    cleaned = raw.replace("_", " ")
    return clean_astronaut_text(cleaned)


def clean_astronaut_text(text: Any) -> str:
    """Limpia prefijos de prototipo, códigos con guion bajo y jerga técnica."""
    s = str(text or "").strip()
    if not s:
        return ""
    s = re.sub(r"Hipótesis orientativa\s*\(escenario simulado\)\s*:\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^Hipótesis\s*:\s*", "", s, flags=re.IGNORECASE)
    for src, dst in _TEXT_REWRITES:
        s = re.sub(re.escape(src), dst, s, flags=re.IGNORECASE)
    for slug, friendly in _REASON_LABELS.items():
        if slug in s:
            s = s.replace(slug, friendly)
    for pat_key, (pat_label, _, _) in _PATTERN_INFO.items():
        if pat_key in s:
            s = s.replace(pat_key, pat_label.lstrip("●▲■ ").lower())
    s = s.replace("Módulo ML en abstención/espera:", "Estimación en espera:")
    s = re.sub(r"\s{2,}", " ", s).strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def filter_astronaut_evidence(evidence: list[Any], pattern_hyp: str | None = None) -> list[str]:
    """Conserva solo los datos clave para el astronauta sin avisos repetitivos."""
    pat_clean = clean_astronaut_text(pattern_hyp).lower() if pattern_hyp else ""
    out: list[str] = []
    for raw in evidence:
        text = str(raw or "").strip()
        if not text:
            continue
        low = text.lower()
        if any(frag in low for frag in _DISCARDED_EVIDENCE_FRAGMENTS):
            continue
        cleaned = clean_astronaut_text(text)
        if not cleaned:
            continue
        if pat_clean and cleaned.lower() == pat_clean:
            continue
        if cleaned not in out:
            out.append(cleaned)
    return out


def _finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def channel_severity(value: Any, key: str) -> str:
    """Clasifica visualmente una lectura sin inventar valores ante ausencia."""
    num = _finite_float(value)
    if num is None:
        return "missing"
    meta = SIGNAL_VISUAL_META.get(key)
    if meta is None:
        return "nominal"
    _, _, nom_lo, nom_hi, warn_lo, warn_hi, _, _ = meta
    if nom_lo <= num <= nom_hi:
        return "nominal"
    if warn_lo <= num <= warn_hi:
        return "watch"
    return "alert"


def severity_color(sev: str) -> str:
    return _SEVERITY_STYLE.get(sev, _SEVERITY_STYLE["missing"])[1]


def gauge_bar(value: Any, key: str, width: int = 16) -> Text:
    """Barra segmentada ▰▰◆▱▱ con cursor en rango o aviso explícito de SIN SEÑAL."""
    num = _finite_float(value)
    if num is None:
        dots = "◌" * max(4, min(width, 6))
        return Text(f"{dots} SIN SEÑAL", style="bold #fbbf24")

    meta = SIGNAL_VISUAL_META.get(key)
    if meta is None:
        vmin, vmax = 0.0, 100.0
        color = "#38bdf8"
    else:
        vmin, vmax, _, _, _, _, _, _ = meta
        color = severity_color(channel_severity(num, key))

    span = max(1e-6, vmax - vmin)
    ratio = max(0.0, min(1.0, (num - vmin) / span))
    cursor = min(width - 1, max(0, int(round(ratio * (width - 1)))))

    text = Text()
    if cursor > 0:
        text.append("▰" * cursor, style=color)
    text.append("◆", style=f"bold {color}")
    if width - cursor - 1 > 0:
        text.append("▱" * (width - cursor - 1), style="#293b52")
    return text


def progress_ratio_bar(
    ratio: float,
    width: int = 16,
    fill_color: str = "#38bdf8",
    empty_color: str = "#24364d",
) -> Text:
    """Barra sólida de proporción [0..1] para indicadores no ausentes."""
    clamped = max(0.0, min(1.0, ratio))
    filled = int(round(clamped * width))
    out = Text()
    if filled > 0:
        out.append("█" * filled, style=fill_color)
    if width - filled > 0:
        out.append("░" * (width - filled), style=empty_color)
    return out


def _draw_line(grid: list[list[int]], x0: int, y0: int, x1: int, y1: int) -> None:
    """Traza un segmento discreto sobre la rejilla booleana (py x px)."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cx, cy = x0, y0
    while True:
        if 0 <= cy < h and 0 <= cx < w:
            grid[cy][cx] = 1
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            cx += sx
        if e2 <= dx:
            err += dx
            cy += sy


def _grid_to_braille_rows(grid: list[list[int]], width: int, height: int) -> list[str]:
    rows: list[str] = []
    for row_idx in range(height):
        chars: list[str] = []
        base_y = row_idx * 4
        for col_idx in range(width):
            base_x = col_idx * 2
            code = 0x2800
            for dy in range(4):
                for dx in range(2):
                    if grid[base_y + dy][base_x + dx]:
                        code |= _BRAILLE_MAP[dy][dx]
            chars.append(chr(code))
        rows.append("".join(chars))
    return rows


def braille_chart(
    series: list[float],
    width: int = 44,
    height: int = 5,
    color: str = "#38bdf8",
    threshold: float | None = None,
    baseline: float | None = None,
    unit: str = "",
) -> Text:
    """Renderiza una serie continua en alta resolución Braille 2x4 con eje Y y guías."""
    clean = [v for v in (_finite_float(x) for x in series) if v is not None]
    out = Text()

    if not clean:
        border = "─" * max(16, width)
        out.append(f"       ╭{border}╮\n", style="#2c4563")
        mid = height // 2
        for r in range(height):
            if r == mid:
                msg = "◌ SIN SEÑAL (—) · Sensor desconectado o sin lectura"
                msg = msg[:width].center(width)
                out.append("   —   │", style="#64748b")
                out.append(msg, style="bold #fbbf24")
                out.append("│\n", style="#2c4563")
            else:
                out.append(f"       │{' ' * width}│\n", style="#2c4563")
        out.append(f"       ╰{border}╯", style="#2c4563")
        return out

    vals = list(clean)
    lo = min(vals)
    hi = max(vals)
    thr_val = _finite_float(threshold)
    base_val = _finite_float(baseline)
    if thr_val is not None and abs(thr_val - lo) <= max(15.0, (hi - lo) * 2.5 + 1.0):
        lo = min(lo, thr_val)
        hi = max(hi, thr_val)
    if base_val is not None and abs(base_val - lo) <= max(15.0, (hi - lo) * 2.5 + 1.0):
        lo = min(lo, base_val)
        hi = max(hi, base_val)

    span = hi - lo
    if span < 1e-4:
        pad = max(0.5, abs(hi) * 0.05)
        lo -= pad
        hi += pad
        span = hi - lo

    px_w = width * 2
    px_h = height * 4
    data_grid = [[0] * px_w for _ in range(px_h)]
    ref_grid = [[0] * px_w for _ in range(px_h)]

    def _to_py(val: float) -> int:
        norm = max(0.0, min(1.0, (val - lo) / span))
        return int(round((1.0 - norm) * (px_h - 1)))

    if thr_val is not None and lo <= thr_val <= hi:
        ty = _to_py(thr_val)
        for px in range(0, px_w, 3):
            ref_grid[ty][px] = 1
    if base_val is not None and lo <= base_val <= hi:
        by = _to_py(base_val)
        for px in range(0, px_w, 5):
            ref_grid[by][px] = 1

    if len(clean) == 1:
        py = _to_py(clean[0])
        _draw_line(data_grid, 0, py, px_w - 1, py)
    else:
        n = len(clean)
        pts = [
            (int(round(i * (px_w - 1) / (n - 1))), _to_py(val))
            for i, val in enumerate(clean)
        ]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            _draw_line(data_grid, x0, y0, x1, y1)

    data_rows = _grid_to_braille_rows(data_grid, width, height)
    ref_rows = _grid_to_braille_rows(ref_grid, width, height)

    mid_val = (lo + hi) / 2.0
    for r in range(height):
        if r == 0:
            axis_lbl = f"{hi:6.1f} ┤"
        elif r == height // 2:
            axis_lbl = f"{mid_val:6.1f} ┤"
        elif r == height - 1:
            axis_lbl = f"{lo:6.1f} ┤"
        else:
            axis_lbl = "       │"
        out.append(axis_lbl, style="#6f87a6")

        d_row = data_rows[r]
        r_row = ref_rows[r]
        for d_ch, r_ch in zip(d_row, r_row):
            if d_ch != "\u2800":
                out.append(d_ch, style=f"bold {color}")
            elif r_ch != "\u2800":
                out.append(r_ch, style="#94a3b8")
            else:
                out.append("·" if r == height - 1 else " ", style="#1b2d44")
        if r < height - 1:
            out.append("\n")

    unit_txt = f" {unit}" if unit else ""
    out.append(f"\n       ╰{'─' * width} ", style="#2c4563")
    out.append(f"últ:{clean[-1]:.1f}{unit_txt} · min:{min(clean):.1f} · max:{max(clean):.1f}", style="#93b4d4")
    return out


def _ecg_wave_value(phase: float) -> float:
    """Forma de onda P-QRS-T normalizada en [-0.35, 1.0] para el ciclo cardíaco [0, 1)."""
    p = phase % 1.0
    # Onda P
    if 0.12 <= p < 0.22:
        return 0.18 * math.sin(((p - 0.12) / 0.10) * math.pi)
    # Complejo Q
    if 0.27 <= p < 0.30:
        return -0.18 * math.sin(((p - 0.27) / 0.03) * math.pi)
    # Pico R
    if 0.30 <= p < 0.35:
        return 1.0 * math.sin(((p - 0.30) / 0.05) * math.pi)
    # S nadir
    if 0.35 <= p < 0.39:
        return -0.28 * math.sin(((p - 0.35) / 0.04) * math.pi)
    # Onda T
    if 0.50 <= p < 0.68:
        return 0.30 * math.sin(((p - 0.50) / 0.18) * math.pi)
    return 0.0


def render_ecg_oscilloscope(
    hr: Any,
    rr: Any,
    spo2: Any,
    activity: str,
    tick: int,
    width: int = 48,
) -> Text:
    """Osciloscopio ECG en Braille 2x4; nunca dibuja onda falsa si HR es None."""
    hr_num = _finite_float(hr)
    rr_num = _finite_float(rr)
    spo2_num = _finite_float(spo2)
    act_label = humanize_activity(activity).upper()

    out = Text()
    if hr_num is None:
        out.append("◌ BIO-LEAD II · ", style="bold #fbbf24")
        out.append("SIN SEÑAL (—)", style="bold #fbbf24")
        out.append(f" · BANDA 0.5–40 Hz · {act_label}\n", style="#7c96b3")
        line = "┈" * max(16, width)
        out.append(f"  +1mV ┤ {line}\n", style="#334155")
        out.append("   0mV ┤ ", style="#334155")
        out.append("Sensor de pulso desconectado · esperando contacto con el traje".center(width), style="#fbbf24")
        out.append("\n")
        out.append(f"  -1mV ┤ {line}\n", style="#334155")
        out.append(f"       └{'─' * (width + 1)}", style="#243b55")
        return out

    beat_icon = "♥" if tick % 2 == 0 else "♡"
    hr_color = severity_color(channel_severity(hr_num, "hr"))
    rr_txt = f"{rr_num:.0f} rpm" if rr_num is not None else "—"
    spo2_txt = f"{spo2_num:.1f}%" if spo2_num is not None else "—"

    out.append(f"{beat_icon} BIO-LEAD II ", style=f"bold {hr_color}")
    out.append(f"· FC {hr_num:.0f} bpm · FR {rr_txt} · SpO₂ {spo2_txt} · {act_label}\n", style="#b7cbe0")

    height = 4
    px_w = width * 2
    px_h = height * 4
    grid = [[0] * px_w for _ in range(px_h)]

    cycles = max(1.6, min(4.2, hr_num / 28.0))
    shift = (tick * 0.23) % 1.0
    prev_xy: tuple[int, int] | None = None
    for px in range(px_w):
        phase = (px / max(1, px_w - 1)) * cycles + shift
        amp = _ecg_wave_value(phase)
        norm = (amp + 0.35) / 1.40
        py = int(round((1.0 - max(0.0, min(1.0, norm))) * (px_h - 1)))
        if prev_xy is not None:
            _draw_line(grid, prev_xy[0], prev_xy[1], px, py)
        else:
            grid[py][px] = 1
        prev_xy = (px, py)

    rows = _grid_to_braille_rows(grid, width, height)
    labels = (" +1mV ┤ ", "  iso ┼ ", "      │ ", " -1mV ┤ ")
    for r, (lbl, row_chars) in enumerate(zip(labels, rows)):
        out.append(lbl, style="#5f7a99")
        # Colorear los píxeles más recientes al final del barrido con brillo cian/esmeralda
        split = max(0, len(row_chars) - 8)
        out.append(row_chars[:split], style=hr_color)
        out.append(row_chars[split:], style="bold #a7f3d0")
        out.append("\n")
    out.append(f"       └{'─' * width} ", style="#2c4563")
    out.append("0.5–40 Hz · barrido en vivo", style="#6f87a6")
    return out


def render_ml_forecast_braille(
    history: list[dict[str, Any]],
    forecast: dict[str, Any],
    width: int = 44,
) -> Text:
    """Curva Braille de FC reciente + punto proyectado +60 s y banda de incertidumbre."""
    out = Text()
    series = [
        val
        for val in (_finite_float(item.get("hr")) for item in history[-45:])
        if val is not None
    ]
    fc_val = _finite_float(forecast.get("forecast_hr"))
    rad_val = _finite_float(forecast.get("interval_radius_bpm"))
    pers_val = _finite_float(forecast.get("persistence_hr"))

    if not series:
        out.append("EVOLUCIÓN DEL PULSO: esperando lecturas continuas.\n", style="#fbbf24")
        out.append(braille_chart([], width=width, height=3, unit="bpm"))
        return out

    extended = list(series)
    if fc_val is not None:
        # Interpola puente suave hacia el horizonte +60 s
        last_hr = series[-1]
        steps = 8
        for idx in range(1, steps + 1):
            extended.append(last_hr + (fc_val - last_hr) * (idx / steps))

    out.append("EVOLUCIÓN DEL PULSO", style="bold #7dd3fc")
    if fc_val is not None:
        if rad_val is not None:
            lo = max(35.0, fc_val - rad_val)
            hi = fc_val + rad_val
            out.append(
                f"  ──▶  EN 1 MIN: {fc_val:.0f} bpm (rango {lo:.0f}–{hi:.0f})",
                style="bold #c084fc",
            )
        else:
            out.append(f"  ──▶  EN 1 MIN: {fc_val:.0f} bpm", style="bold #c084fc")
    elif pers_val is not None:
        out.append(f"  ──▶  ESTABLE CERCA DE {pers_val:.0f} bpm", style="#fbbf24")
    else:
        out.append(f"  ──▶  {humanize_reason(forecast.get('reason'))}", style="#94a3b8")
    out.append("\n")

    out.append(
        braille_chart(
            extended,
            width=width,
            height=4,
            color="#c084fc" if fc_val is not None else "#38bdf8",
            threshold=fc_val,
            baseline=pers_val,
            unit="bpm",
        )
    )
    return out


def _zone_status_line(
    zone_id: str,
    title: str,
    summary: str,
    sev: str,
) -> Text:
    tag, color, _ = _SEVERITY_STYLE.get(sev, _SEVERITY_STYLE["missing"])
    line = Text()
    line.append(f"{zone_id} ", style="bold #7dd3fc")
    line.append(f"{title:<14} ", style="bold #dbe6f4")
    line.append(f"{tag:<16}", style=f"bold {color}")
    line.append(f" {summary}", style="#cbd5e1" if sev != "missing" else "#fbbf24")
    return line


def _worst_sev(*sevs: str) -> str:
    order = {"alert": 3, "watch": 2, "nominal": 1, "missing": 0}
    if all(s == "missing" for s in sevs):
        return "missing"
    return max(sevs, key=lambda s: order.get(s, 0))


def render_body_scanner(
    latest: dict[str, Any],
    assessment: dict[str, Any],
    dose_total: Any,
    shelter_active: bool,
) -> Text:
    """Escáner anatómico de traje de 7 zonas sin inventar lecturas faltantes."""
    hr = _finite_float(latest.get("hr"))
    rr = _finite_float(latest.get("rr"))
    spo2 = _finite_float(latest.get("spo2"))
    temp_c = _finite_float(latest.get("temp_c"))
    bp_sys = _finite_float(latest.get("bp_sys"))
    bp_dia = _finite_float(latest.get("bp_dia"))
    co2 = _finite_float(latest.get("co2"))
    hyd = _finite_float(latest.get("hydration_pct"))
    dose = _finite_float(latest.get("dose_rate"))
    dose_acc = _finite_float(dose_total)
    raw_act = str(latest.get("activity") or "unknown").lower()
    act = humanize_activity(raw_act).upper()

    s_head = channel_severity(co2, "co2")
    s_lungs = _worst_sev(channel_severity(rr, "rr"), channel_severity(spo2, "spo2"))
    s_heart = _worst_sev(channel_severity(hr, "hr"), channel_severity(bp_sys, "bp_sys"))
    s_core = channel_severity(temp_c, "temp_c")
    s_hyd = channel_severity(hyd, "hydration_pct")
    s_rad = channel_severity(dose, "dose_rate")
    s_eva = "nominal" if raw_act != "unknown" else "watch"

    c_head = severity_color(s_head)
    c_lungs = severity_color(s_lungs)
    c_heart = severity_color(s_heart)
    c_core = severity_color(s_core)
    c_hyd = severity_color(s_hyd)
    c_rad = "#38bdf8" if shelter_active else severity_color(s_rad)

    zones: list[Text] = [
        _zone_status_line(
            "01",
            "CABEZA / SNC",
            f"ppCO₂ {co2:.2f} mmHg" if co2 is not None else "SIN SEÑAL (—)",
            s_head,
        ),
        _zone_status_line(
            "02",
            "PULMONES",
            (
                f"FR {rr:.0f} rpm · SpO₂ {spo2:.1f}%"
                if rr is not None and spo2 is not None
                else (
                    f"FR {rr:.0f} rpm · SpO₂ —"
                    if rr is not None
                    else (f"FR — · SpO₂ {spo2:.1f}%" if spo2 is not None else "SIN SEÑAL (—)")
                )
            ),
            s_lungs,
        ),
        _zone_status_line(
            "03",
            "CORAZÓN",
            (
                f"FC {hr:.0f} bpm · PA {bp_sys:.0f}/{bp_dia:.0f}"
                if hr is not None and bp_sys is not None and bp_dia is not None
                else (f"FC {hr:.0f} bpm · PA —" if hr is not None else "SIN SEÑAL (—)")
            ),
            s_heart,
        ),
        _zone_status_line(
            "04",
            "CORE TÉRMICO",
            f"Temp {temp_c:.1f} °C" if temp_c is not None else "SIN SEÑAL (—)",
            s_core,
        ),
        _zone_status_line(
            "05",
            "HIDRATACIÓN",
            f"Índice {hyd:.0f}%" if hyd is not None else "SIN SEÑAL (—)",
            s_hyd,
        ),
        _zone_status_line(
            "06",
            "DOSIMETRÍA",
            (
                f"{dose:.2f} μSv/h" + (" [REFUGIO ON]" if shelter_active else "")
                if dose is not None
                else "SIN SEÑAL (—)"
            ),
            s_rad,
        ),
        _zone_status_line(
            "07",
            "ACTIVIDAD EVA",
            f"{act} · Acum: {dose_acc:.2f} μSv" if dose_acc is not None else f"{act} · Acum: —",
            s_eva,
        ),
    ]

    # Silueta humanoide izquierda (15 cols) + zonas a la derecha
    figure: list[list[tuple[str, str]]] = [
        [("    ╭─", "#335275"), ("◉◉", c_head), ("─╮    ", "#335275")],
        [("    ╰──", "#335275"), ("┬", c_head), ("──╯    ", "#335275")],
        [("  ╭─", "#335275"), ("≋", c_lungs), ("─┴", "#335275"), ("♥", c_heart), ("┴─", "#335275"), ("≋", c_lungs), ("─╮", "#335275")],
        [("  │ ", "#335275"), ("░▒", c_lungs), (" ", "#0c1726"), ("◆", c_core), (" ", "#0c1726"), ("▒░", c_lungs), (" │", "#335275")],
        [("  │  ╰─", "#335275"), ("💧", c_hyd), ("─╯  │", "#335275")],
        [("  ╰╮ ", "#335275"), ("☢" if dose is not None else "◌", c_rad), (" ", "#0c1726"), ("██", c_core), ("  ╭╯", "#335275")],
        [("     │ │ │ │    ", "#335275")],
    ]

    lvl = humanize_level(assessment.get("level"))
    out = Text()
    out.append(f"BIO-SUIT 7 ZONAS · ESTADO GLOBAL: {lvl}", style="bold #93c5fd")
    out.append("  [REFUGIO ACTIVO]\n" if shelter_active else "\n", style="bold #38bdf8")

    for fig_segments, zone_text in zip(figure, zones):
        for seg, seg_color in fig_segments:
            out.append(seg, style=f"bold {seg_color}")
        out.append(" │ ", style="#233b54")
        out.append(zone_text)
        out.append("\n")

    return out


def render_reaction_cockpit(
    phase: str,
    trial: int,
    total_trials: int,
    times: list[float],
    false_starts: int,
    lapses: int,
    baseline_ms: float | None,
) -> Text:
    """Semáforo óptico de cabina y marcador en vivo para el test de reflejos."""
    import statistics as _stats

    out = Text()
    med_ms = _stats.median(times) if times else None
    w_box = 72
    out.append("╭─ CABINA DE REFLEJOS ÓPTICOS " + "─" * (w_box - 30) + "╮\n", style="bold #38bdf8")

    # Semáforo de 3 fases en doble caja
    p1_on = phase in {"idle", "between"}
    p2_on = phase == "waiting"
    p3_go = phase == "go"
    p3_false = phase == "false_start"
    p3_done = phase == "done"

    l1_txt = " ● LISTO PARA INICIAR ".center(22) if phase == "idle" else " ◌ EN PAUSA           ".center(22)
    l2_txt = " ▲ ATENTO AL VERDE... ".center(22) if p2_on else " ◌ ESPERANDO SEÑAL    ".center(22)
    if p3_go:
        l3_txt = " ██ ¡PULSA AHORA! ██  ".center(22)
        l3_sty = "bold #06101a on #4ade80"
        l3_brd = "#4ade80"
    elif p3_false:
        l3_txt = " ✖ SALIDA EN FALSO    ".center(22)
        l3_sty = "bold #06101a on #fb7185"
        l3_brd = "#fb7185"
    elif p3_done:
        l3_txt = " ★ PRUEBA COMPLETADA ★".center(22)
        l3_sty = "bold #06101a on #38bdf8"
        l3_brd = "#38bdf8"
    else:
        l3_txt = " ◌ SEÑAL VERDE        ".center(22)
        l3_sty = "#475569"
        l3_brd = "#243b55"

    l1_sty = "bold #38bdf8" if p1_on else "#475569"
    l1_brd = "#38bdf8" if p1_on else "#243b55"
    l2_sty = "bold #06101a on #fbbf24" if p2_on else "#475569"
    l2_brd = "#fbbf24" if p2_on else "#243b55"

    top = "╔" + "═" * 22 + "╗"
    bot = "╚" + "═" * 22 + "╝"

    out.append("│ ", style="#27435e")
    out.append(top, style=l1_brd)
    out.append(" ")
    out.append(top, style=l2_brd)
    out.append(" ")
    out.append(top + "\n", style=l3_brd)

    out.append("│ ", style="#27435e")
    out.append("║", style=l1_brd)
    out.append(l1_txt, style=l1_sty)
    out.append("║ ", style=l1_brd)
    out.append("║", style=l2_brd)
    out.append(l2_txt, style=l2_sty)
    out.append("║ ", style=l2_brd)
    out.append("║", style=l3_brd)
    out.append(l3_txt, style=l3_sty)
    out.append("║\n", style=l3_brd)

    out.append("│ ", style="#27435e")
    out.append(bot, style=l1_brd)
    out.append(" ")
    out.append(bot, style=l2_brd)
    out.append(" ")
    out.append(bot + "\n", style=l3_brd)

    # Marcador en vivo: intento, mediana actual vs tu referencia personal
    med_str = f"{med_ms:.0f} ms" if med_ms is not None else "—"
    base_str = f"{baseline_ms:.0f} ms" if baseline_ms is not None else "calibrando (3 días)"
    if med_ms is not None and baseline_ms is not None:
        delta = med_ms - baseline_ms
        sign = "+" if delta >= 0 else ""
        delta_txt = f" ({sign}{delta:.0f} ms frente a tu marca)"
        delta_clr = "#fbbf24" if delta > 80.0 else "#4ade80"
    else:
        delta_txt = ""
        delta_clr = "#cbd5e1"

    out.append("│ ", style="#27435e")
    out.append(f"Intento {trial}/{total_trials} ", style="bold #bae6fd")
    out.append("│ ⚡ Tu tiempo: ", style="#94a3b8")
    out.append(med_str, style="bold #38bdf8" if med_ms else "#64748b")
    out.append(" │ 🎯 Tu referencia: ", style="#94a3b8")
    out.append(base_str, style="bold #4ade80" if baseline_ms else "#94a3b8")
    if delta_txt:
        out.append(delta_txt, style=f"bold {delta_clr}")
    out.append("\n")

    out.append("│ ", style="#27435e")
    fs_clr = "#fb7185" if false_starts > 0 else "#64748b"
    lp_clr = "#fbbf24" if lapses > 0 else "#64748b"
    out.append(f"Salidas anticipadas: {false_starts}   ", style=fs_clr)
    out.append("·   ", style="#334155")
    out.append(f"Respuestas lentas (>500 ms): {lapses}\n", style=lp_clr)
    out.append("╰" + "─" * w_box + "╯", style="#27435e")
    return out


def render_reaction_histogram(
    times: list[float],
    baseline_ms: float | None,
    sleep_hours: float,
    mood: int,
    current_trial: int = 0,
    phase: str = "idle",
) -> Text:
    """Dianas por intento, barras de velocidad y medidores gráficos de sueño y ánimo."""
    out = Text()
    out.append("DIANA DE 6 INTENTOS Y VELOCIDAD DE RESPUESTA\n", style="bold #7dd3fc")

    # Fila de 6 cápsulas visuales [01..06]
    out.append("  ")
    for idx in range(6):
        if idx < len(times):
            val = float(times[idx])
            if val > 500.0:
                c_clr = "#fb7185"
                badge = f"[{idx + 1} ■ {val:.0f}]"
            elif baseline_ms is not None and val > baseline_ms + 80.0:
                c_clr = "#fbbf24"
                badge = f"[{idx + 1} ▲ {val:.0f}]"
            else:
                c_clr = "#4ade80"
                badge = f"[{idx + 1} ⚡{val:.0f}]"
            out.append(f"{badge:<11} ", style=f"bold {c_clr}")
        elif idx + 1 == current_trial and phase in {"waiting", "go", "false_start"}:
            out.append(f"[{idx + 1} ◎ YA!]   ", style="bold #06101a on #38bdf8")
        else:
            out.append(f"[{idx + 1} ┈ --]   ", style="#475569")
    out.append("\n\n")

    # Barras graduadas de tiempo por intento
    max_scale = max([550.0, *(times or [320.0])])
    for idx in range(6):
        if idx < len(times):
            val = float(times[idx])
            bar_len = max(1, min(30, int(round((val / max_scale) * 30))))
            if val > 500.0:
                color = "#fb7185"
                flag = " ■ Lento (>500 ms)"
            elif baseline_ms is not None and val > baseline_ms + 80.0:
                color = "#fbbf24"
                flag = " ▲ Más lento que tu base"
            elif val < 300.0:
                color = "#4ade80"
                flag = " ⚡ Muy ágil"
            else:
                color = "#38bdf8"
                flag = " ● Estable"
            out.append(f"  Intento {idx + 1}: ", style="#cbd5e1")
            out.append("█" * bar_len, style=color)
            out.append("░" * (30 - bar_len), style="#1e293b")
            out.append(f" {val:5.0f} ms", style=f"bold {color}")
            out.append(f"{flag}\n", style="#cbd5e1")
        else:
            out.append(f"  Intento {idx + 1}: ", style="#64748b")
            out.append("┈" * 30, style="#1e293b")
            out.append("    —  (pendiente)\n", style="#64748b")

    # Panel gráfico de descanso y ánimo
    out.append("\n")
    sleep_blocks = max(0, min(10, int(round((sleep_hours / 10.0) * 10))))
    slp_clr = "#4ade80" if sleep_hours >= 7.0 else ("#fbbf24" if sleep_hours >= 5.5 else "#fb7185")
    slp_tag = "Descanso óptimo" if sleep_hours >= 7.0 else ("Algo justo" if sleep_hours >= 5.5 else "Poco sueño")

    mood_labels = {1: "Muy bajo", 2: "Bajo", 3: "Normal", 4: "Bien", 5: "Óptimo"}
    mood_clr = "#4ade80" if mood >= 4 else ("#38bdf8" if mood == 3 else "#fbbf24")
    stars = " ".join("★" if i < mood else "☆" for i in range(5))

    out.append("  🔋 Sueño hoy: ", style="bold #93c5fd")
    out.append("▰" * sleep_blocks, style=slp_clr)
    out.append("▱" * (10 - sleep_blocks), style="#243b55")
    out.append(f" {sleep_hours:.1f} h ", style=f"bold {slp_clr}")
    out.append(f"({slp_tag})   │   ", style="#94a3b8")
    out.append("✨ Ánimo: ", style="bold #facc15")
    out.append(stars, style=f"bold {mood_clr}")
    out.append(f" ({mood}/5 · {mood_labels.get(mood, 'Normal')})", style="#dbe6f4")
    return out


def render_checkin_result_card(data: dict[str, Any]) -> Text:
    """Tarjeta visual de resultado al registrar un check-in conductual."""
    med_v = _finite_float(data.get("median_ms"))
    base_v = _finite_float(data.get("baseline_ms"))
    drift = bool(data.get("drift_detected"))
    pts = int(data.get("points_awarded") or 15)
    interp = clean_astronaut_text(data.get("interpretation") or "Chequeo registrado correctamente.")

    status_lbl = "▲ CAMBIO FRENTE A TU BASE" if drift else "● REFLEJOS ESTABLES"
    status_clr = "#fbbf24" if drift else "#4ade80"
    med_txt = f"{med_v:>5.0f} ms" if med_v is not None else "  —  ms"
    base_txt = f"{base_v:>5.0f} ms" if base_v is not None else "CALIB.  "

    out = Text()
    out.append("╭─ RESULTADO DE TU CHEQUEO HOY ──────────────────────────────────────╮\n", style="bold #38bdf8")
    out.append("│ ", style="#27435e")
    out.append(f" {status_lbl} ", style=f"bold #06101a on {status_clr}")
    out.append(f"   🏆 +{pts} pts por constancia\n", style="bold #facc15")

    top = "╔══════════════════╗"
    bot = "╚══════════════════╝"
    out.append("│ ", style="#27435e")
    out.append(top, style=status_clr)
    out.append("    ")
    out.append(top + "\n", style="#4ade80")
    out.append("│ ", style="#27435e")
    out.append("║", style=status_clr)
    out.append(f" ⚡ HOY: {med_txt}".ljust(18), style=f"bold {status_clr}")
    out.append("║ ◀▶ ", style=status_clr)
    out.append("║", style="#4ade80")
    out.append(f" 🎯 BASE: {base_txt}".ljust(18), style="bold #4ade80")
    out.append("║\n", style="#4ade80")
    out.append("│ ", style="#27435e")
    out.append(bot, style=status_clr)
    out.append("    ")
    out.append(bot + "\n", style="#4ade80")
    out.append(f"│ {interp}\n", style="#e2e8f0")
    out.append("╰─────────────────────────────────────────────────────────────────────╯", style="#27435e")
    return out


def render_trends_summary_hud(
    window_label: str,
    data: dict[str, Any],
    baseline: dict[str, Any],
) -> Text:
    """Resumen visual superior de tendencias con cobertura y 4 canales clave."""
    cov = float(data.get("coverage_pct") or 0.0)
    samples = int(data.get("sample_count") or 0)
    signals = data.get("signals") or {}

    out = Text()
    out.append("╭─ RESUMEN DE TENDENCIAS EN CABINA ──────────────────────────────────────────╮\n", style="bold #38bdf8")
    out.append(f"│ Ventana: ", style="#94a3b8")
    out.append(f"{window_label:<8}", style="bold #bae6fd")
    out.append(f" · Muestras: {samples:<4} · Cobertura: ", style="#94a3b8")
    out.append(progress_ratio_bar(cov / 100.0, width=14, fill_color="#38bdf8"))
    out.append(f" {cov:.0f}%\n", style="bold #38bdf8")

    specs = (
        ("hr", "♥ PULSO      ", "bpm", 0),
        ("rr", "≋ RESPIRACIÓN", "rpm", 0),
        ("co2", "☁ AIRE CO₂   ", "mmHg", 2),
        ("dose_rate", "☢ RADIACIÓN  ", "μSv/h", 2),
    )
    for key, label, unit, dec in specs:
        sig = signals.get(key) or {}
        lat = _finite_float(sig.get("latest"))
        mean = _finite_float(sig.get("mean"))
        mn = _finite_float(sig.get("min"))
        mx = _finite_float(sig.get("max"))
        out.append(f"│ {label} ", style="bold #cbd5e1")
        out.append(gauge_bar(lat, key, width=12))
        if lat is not None:
            sev_clr = severity_color(channel_severity(lat, key))
            out.append(f"  Actual {lat:.{dec}f} {unit:<5}", style=f"bold {sev_clr}")
            if mean is not None and mn is not None and mx is not None:
                out.append(f"  ·  Prom {mean:.{dec}f}  ·  Rango {mn:.{dec}f}–{mx:.{dec}f}", style="#94a3b8")
        else:
            out.append("  ◌ SIN SEÑAL (—)", style="bold #fbbf24")
        if baseline.get("status") == "ready" and key in {"hr", "rr"} and _finite_float(baseline.get(key)) is not None:
            out.append(f"  ·  Base {float(baseline[key]):.0f}", style="#4ade80")
        out.append("\n")

    out.append("╰────────────────────────────────────────────────────────────────────────────╯", style="#27435e")
    return out


def render_coach_dashboard_hud(
    coach: dict[str, Any],
    badge_gallery: tuple[tuple[str, str], ...],
) -> Text:
    """Cabecera gráfica de hábitos, puntos, racha e insignias desbloqueadas."""
    pts = int(coach.get("points") or 0)
    streak = int(coach.get("streak") or 0)
    unlocked = set(coach.get("badges") or [])
    level_num = (pts // 100) + 1
    lvl_ratio = ((pts % 100) / 100.0) if pts > 0 else 0.0

    out = Text()
    out.append("╭─ TU PROGRESO DE HÁBITOS EN MISIÓN ──────────────────────────────────────╮\n", style="bold #38bdf8")

    top = "╔══════════════════╗"
    bot = "╚══════════════════╝"
    out.append("│ ", style="#27435e")
    out.append(top, style="#facc15")
    out.append("  ")
    out.append(top, style="#fb923c")
    out.append("  ")
    out.append(top + "\n", style="#4ade80")

    out.append("│ ", style="#27435e")
    out.append("║", style="#facc15")
    out.append(f" 🏆 {pts:>4} PUNTOS ".center(18), style="bold #facc15")
    out.append("║  ", style="#facc15")
    out.append("║", style="#fb923c")
    out.append(f" 🔥 RACHA x{streak:<3} ".center(18), style="bold #fb923c")
    out.append("║  ", style="#fb923c")
    out.append("║", style="#4ade80")
    out.append(f" ★ NIVEL {level_num:<3} ".center(18), style="bold #4ade80")
    out.append("║\n", style="#4ade80")

    out.append("│ ", style="#27435e")
    out.append(bot, style="#facc15")
    out.append("  ")
    out.append(bot, style="#fb923c")
    out.append("  ")
    out.append(bot + "\n", style="#4ade80")

    out.append("│ Siguiente nivel: ", style="#94a3b8")
    out.append(progress_ratio_bar(lvl_ratio, width=22, fill_color="#4ade80"))
    out.append(f" {pts % 100}/100 pts   │   Medallas:\n", style="#cbd5e1")
    out.append("│   ", style="#27435e")
    for badge_id, badge_lbl in badge_gallery:
        has_it = badge_id in unlocked
        out.append(
            f" {badge_lbl} ",
            style=("bold #06101a on #facc15" if has_it else "#64748b on #122033"),
        )
        out.append(" ")
    out.append("\n│ ", style="#27435e")
    out.append("Ganas puntos por completar chequeos de cuidado; tus lecturas corporales nunca restan puntos.\n", style="#93c5fd")
    out.append("╰─────────────────────────────────────────────────────────────────────────╯", style="#27435e")
    return out


_ROUTINE_ICONS: dict[str, str] = {
    "checkin": "⚡",
    "hydration": "💧",
    "exercise": "🏃",
    "co2_check": "☁",
    "shelter_checklist": "🛡",
}


def render_routine_card_hud(item: dict[str, Any], default_title: str) -> Text:
    """Tarjeta gráfica por rutina con estado, icono y barra de constancia."""
    rid = str(item.get("id") or "")
    icon = _ROUTINE_ICONS.get(rid, "◈")
    active = bool(item.get("active", True))
    due = bool(item.get("due"))
    count = int(item.get("completed_count") or 0)
    title = str(item.get("title") or default_title)
    desc = clean_astronaut_text(item.get("description") or "")

    if not active:
        badge = " ◌ SOLO TORMENTA "
        clr = "#64748b"
    elif due:
        badge = " ▲ TOCA AHORA "
        clr = "#fbbf24"
    else:
        badge = " ● AL DÍA "
        clr = "#4ade80"

    blocks = min(5, count)
    bar = "▰" * blocks + "▱" * (5 - blocks)

    out = Text()
    out.append(badge, style=f"bold #06101a on {clr}")
    out.append(f"  {icon} {title}   ", style="bold #e2e8f0")
    out.append(bar, style="#38bdf8" if count > 0 else "#334155")
    out.append(f" {count} veces\n", style="#7dd3fc")
    out.append(f"  {desc}", style="#94a3b8")
    return out


def render_privacy_hud_banner(share_behavioral: bool) -> Text:
    """Banner gráfico de privacidad para el informe de episodio."""
    out = Text()
    out.append("╭─ CONTROL DE PRIVACIDAD DE TU INFORME ───────────────────────────────────────╮\n", style="bold #38bdf8")
    out.append("│ 📡 Datos de traje y cabina (pulso, aire, radiación): ", style="#94a3b8")
    out.append("INCLUIDOS PARA MISIÓN\n", style="bold #bae6fd")
    out.append("│ 🔒 Tu bienestar personal (sueño, ánimo, reflejos):  ", style="#94a3b8")
    if share_behavioral:
        out.append(" 🔓 COMPARTIDO AL GUARDAR ", style="bold #06101a on #fbbf24")
    else:
        out.append(" 🔒 SOLO PARA TI EN CABINA ", style="bold #06101a on #4ade80")
    out.append("\n╰─────────────────────────────────────────────────────────────────────────────╯", style="#27435e")
    return out


_SIGNAL_TITLES: dict[str, tuple[str, str, int]] = {
    "hr": ("Frecuencia Cardíaca (FC)", "bpm", 0),
    "rr": ("Frecuencia Respiratoria (FR)", "resp/min", 0),
    "spo2": ("Saturación SpO₂", "%", 1),
    "temp_c": ("Temperatura Corporal / Cutánea", "°C", 1),
    "bp_sys": ("Presión Arterial Sistólica / Diastólica", "mmHg", 0),
    "bp_dia": ("Presión Arterial Diastólica", "mmHg", 0),
    "co2": ("Presión Parcial de CO₂ (ppCO₂)", "mmHg", 2),
    "hydration_pct": ("Índice de Hidratación", "%", 0),
    "dose_rate": ("Tasa de Dosis de Radiación", "μSv/h", 2),
}


def render_astronaut_ai_panel(
    latest: dict[str, Any],
    forecast: dict[str, Any],
    pattern: dict[str, Any],
    baseline: dict[str, Any],
    co2_sens: dict[str, Any],
) -> Text:
    """Tarjetas HUD claras con jerarquía visual para pronóstico, patrón y referencia."""
    out = Text()
    w_box = 64

    # 1. Bloque destacado de pronóstico +1 minuto
    fc_val = _finite_float(forecast.get("forecast_hr"))
    now_hr = _finite_float(latest.get("hr"))
    rad_val = _finite_float(forecast.get("interval_radius_bpm"))

    out.append("╭─ PRONÓSTICO DE PULSO EN 1 MINUTO " + "─" * (w_box - 35) + "╮\n", style="bold #c084fc")
    if fc_val is not None:
        ref_hr = now_hr if now_hr is not None else _finite_float(forecast.get("persistence_hr"))
        now_txt = f"{ref_hr:>3.0f} bpm" if ref_hr is not None else " —  bpm"
        fc_txt = f"{fc_val:>3.0f} bpm"
        fc_clr = severity_color(channel_severity(fc_val, "hr"))
        now_clr = severity_color(channel_severity(ref_hr, "hr")) if ref_hr is not None else "#94a3b8"

        if ref_hr is not None:
            diff = fc_val - ref_hr
            if diff >= 2.0:
                arrow = f"══ ▲ +{diff:.0f} bpm ══▶".center(18)
                arrow_clr = "bold #fbbf24"
            elif diff <= -2.0:
                arrow = f"══ ▼ {diff:.0f} bpm ══▶".center(18)
                arrow_clr = "bold #38bdf8"
            else:
                arrow = "══ ▶ ESTABLE ══▶".center(18)
                arrow_clr = "bold #4ade80"
        else:
            arrow = "══ ▶ EN 1 MIN ══▶".center(18)
            arrow_clr = "bold #c084fc"

        top_edge = "╔" + "═" * 18 + "╗"
        bot_edge = "╚" + "═" * 18 + "╝"
        left_cell = f" ♥ AHORA: {now_txt}".ljust(18)
        right_cell = f" ◆ EN 1M: {fc_txt}".ljust(18)

        out.append("│ ", style="#27435e")
        out.append(top_edge, style=now_clr)
        out.append(" " * 18)
        out.append(top_edge + "\n", style=fc_clr)

        out.append("│ ", style="#27435e")
        out.append("║", style=now_clr)
        out.append(left_cell, style=f"bold {now_clr}")
        out.append("║", style=now_clr)
        out.append(arrow, style=arrow_clr)
        out.append("║", style=fc_clr)
        out.append(right_cell, style=f"bold {fc_clr}")
        out.append("║\n", style=fc_clr)

        out.append("│ ", style="#27435e")
        out.append(bot_edge, style=now_clr)
        out.append(" " * 18)
        out.append(bot_edge + "\n", style=fc_clr)

        out.append("│   ", style="#27435e")
        if rad_val is not None:
            lo = max(35.0, fc_val - rad_val)
            hi = fc_val + rad_val
            out.append(f"Margen esperado: {lo:.0f} a {hi:.0f} bpm   ", style="#cbd5e1")
        else:
            out.append("Estimación para el próximo minuto   ", style="#cbd5e1")
        out.append(gauge_bar(fc_val, "hr", width=14))
        out.append("\n")
    else:
        reason_txt = humanize_reason(forecast.get("reason") or forecast.get("status"))
        out.append(f"│ ⏳ En espera: {reason_txt}\n", style="#94a3b8")
    out.append("╰" + "─" * w_box + "╯\n", style="#27435e")

    # 2. Bloque de patrón físico actual
    out.append("╭─ ESTADO FÍSICO DETECTADO " + "─" * (w_box - 27) + "╮\n", style="bold #66e0bd")
    if pattern.get("available"):
        pat_label, pat_desc, pat_clr = humanize_pattern(pattern.get("pattern"))
        pat_score = float(pattern.get("score") or 0.0)
        out.append("│ ", style="#27435e")
        out.append(f"{pat_label:<28} ", style=f"bold {pat_clr}")
        out.append(progress_ratio_bar(pat_score, width=12, fill_color=pat_clr))
        out.append(f" {pat_score * 100:.0f}%\n", style=f"bold {pat_clr}")
        out.append(f"│   {pat_desc}\n", style="#cbd5e1")
    else:
        pat_reason = humanize_reason(pattern.get("reason") or pattern.get("status"))
        out.append(f"│ ⏳ En observación: {pat_reason}\n", style="#fbbf24")
    out.append("╰" + "─" * w_box + "╯\n", style="#27435e")

    # 3. Tu referencia personal en descanso y aire
    out.append("╭─ TU REFERENCIA PERSONAL " + "─" * (w_box - 26) + "╮\n", style="bold #38bdf8")
    if baseline.get("status") == "ready":
        b_hr = _finite_float(baseline.get("hr"))
        b_rr = _finite_float(baseline.get("rr"))
        hr_s = f"{b_hr:.0f} bpm" if b_hr is not None else "—"
        rr_s = f"{b_rr:.0f} resp/min" if b_rr is not None else "—"
        out.append("│ ♥ Ritmo en descanso: ", style="#94a3b8")
        out.append(f"LISTO · Pulso {hr_s} · Resp. {rr_s}\n", style="bold #4ade80")
    else:
        out.append("│ ♥ Ritmo en descanso: ", style="#94a3b8")
        out.append("Calibrando automáticamente mientras descansas\n", style="#cbd5e1")

    if co2_sens.get("status") == "ready":
        slope = _finite_float(co2_sens.get("slope"))
        thr = _finite_float(co2_sens.get("personal_threshold_mmhg"))
        slope_s = f"+{slope:.1f} resp/min" if slope is not None else "—"
        thr_s = f"~{thr:.1f} mmHg" if thr is not None else "—"
        out.append("│ ☁ Respuesta al CO₂:  ", style="#94a3b8")
        out.append(f"{slope_s} por mmHg · límite personal {thr_s}\n", style="bold #facc15")
    else:
        out.append("│ ☁ Respuesta al CO₂:  ", style="#94a3b8")
        out.append("Aire de cabina estable (se ajusta si sube el CO₂)\n", style="#94a3b8")
    out.append("╰" + "─" * w_box + "╯", style="#27435e")
    return out


def render_sbar_cards(report_data: dict[str, Any]) -> Text:
    """Cuadrantes visuales estructurados [S][B][A][R] en lenguaje de tripulación."""
    sit = report_data.get("situacion") or {}
    ant = report_data.get("antecedentes") or {}
    eva = report_data.get("evaluacion") or {}
    rec = report_data.get("recomendacion") or {}
    share = bool(report_data.get("share_behavioral", False))

    lvl = str(sit.get("level") or "unknown").lower()
    lvl_label = humanize_level(lvl)
    lvl_color = {
        "normal": "#4ade80",
        "watch": "#fbbf24",
        "alert": "#fb7185",
        "unknown": "#94a3b8",
    }.get(lvl, "#94a3b8")

    env_raw = sit.get("environment")
    if isinstance(env_raw, dict):
        env_label = str(env_raw.get("name") or env_raw.get("id") or "No especificado")
    else:
        env_label = str(env_raw or "No especificado")

    out = Text()
    out.append("╭─ RESUMEN DE MISIÓN Y EPISODIO (SBAR) ", style="bold #38bdf8")
    out.append("─" * 40 + "╮\n", style="#27435e")

    if share:
        out.append("│ 🔓 PRIVACIDAD: COMPARTIENDO SUEÑO, ÁNIMO Y REFLEJOS EN EL INFORME", style="bold #fbbf24")
    else:
        out.append("│ 🔒 PRIVACIDAD: SOLO EN CABINA (sueño, ánimo y reflejos quedan privados a bordo)", style="bold #4ade80")
    out.append("\n", style="#27435e")

    title_clean = clean_astronaut_text(sit.get("title") or "—")
    raw_ts = str(sit.get("timestamp") or "")
    ts_clean = (raw_ts[11:19] + " UTC") if len(raw_ts) >= 19 else (raw_ts or "sin hora")
    lvl_icon = {"normal": "●", "watch": "▲", "alert": "■", "unknown": "◌"}.get(lvl, "◌")

    out.append("├─ [S] SITUACIÓN ACTUAL ──────────────────────────────────────────────────────┤\n", style="#27435e")
    out.append("│ ", style="#27435e")
    out.append(f" {lvl_icon} {lvl_label} ", style=f"bold #06101a on {lvl_color}")
    out.append(f"  {title_clean}\n", style=f"bold {lvl_color}")
    out.append(f"│ Módulo: {env_label}   ·   Hora de registro: {ts_clean}\n", style="#94a3b8")

    out.append("├─ [B] ANTECEDENTES ──────────────────────────────────────────────────────────┤\n", style="#27435e")
    dose = ant.get("dose_total_usv")
    dose_str = f"{float(dose):.2f} μSv" if _finite_float(dose) is not None else "SIN SEÑAL (—)"
    dose_cov = "Completa" if ant.get("dose_complete") else "Parcial"
    act_str = humanize_activity(ant.get("activity"))
    out.append(f"│ Actividad: {act_str} · Radiación acumulada: {dose_str} · Cobertura: {dose_cov}\n", style="#e2e8f0")
    beh = ant.get("behavioral_summary")
    if share and isinstance(beh, dict):
        med_v = beh.get("median_ms")
        med_s = f"{med_v} ms" if med_v is not None else "—"
        slp_s = f"{beh.get('sleep_hours', '—')} h" if beh.get("sleep_hours") is not None else "—"
        mood_s = f"{beh.get('mood', '—')}/5" if beh.get("mood") is not None else "—"
        out.append(
            f"│ Bienestar compartido: reflejos {med_s} · sueño {slp_s} · ánimo {mood_s}\n",
            style="#fbbf24",
        )
    else:
        out.append("│ Bienestar personal: RETENIDO SOLO PARA TI EN CABINA\n", style="#66e0bd")

    out.append("├─ [A] LECTURA DE SIGNOS ─────────────────────────────────────────────────────┤\n", style="#27435e")
    hyp_clean = clean_astronaut_text(eva.get("hypothesis") or "Esperando lecturas del traje.")
    out.append(f"│ {hyp_clean}\n", style=f"bold {lvl_color}")
    for item in filter_astronaut_evidence(eva.get("evidence") or [])[:3]:
        out.append(f"│   • {item}\n", style="#cbd5e1")
    for unk in (eva.get("unknowns") or [])[:2]:
        unk_clean = clean_astronaut_text(unk)
        if unk_clean and "sin brechas" not in unk_clean.lower():
            out.append(f"│   ◌ Aviso de sensor: {unk_clean}\n", style="#fbbf24")

    out.append("├─ [R] SIGUIENTE PASO RECOMENDADO ────────────────────────────────────────────┤\n", style="#27435e")
    out.append(f"│ 👉 {clean_astronaut_text(rec.get('next_step', 'Continuar observando tus señales.'))}\n", style="#93c5fd")
    out.append("╰" + "─" * 78 + "╯", style="#27435e")
    return out


def render_sbar_details(report_data: dict[str, Any]) -> Text:
    """Renderiza previsiones con barras, acciones y línea de tiempo vertical."""
    rec = report_data.get("recomendacion") or {}
    eva = report_data.get("evaluacion") or {}
    timeline = report_data.get("timeline") or []
    proj = eva.get("projections") or {}
    co2_p = proj.get("co2") if isinstance(proj.get("co2"), dict) else {}
    rad_p = proj.get("radiation") if isinstance(proj.get("radiation"), dict) else {}

    out = Text()
    if co2_p or rad_p:
        out.append("PROYECCIÓN DE AIRE Y RADIACIÓN (+1 HORA)\n", style="bold #c084fc")
        avg_1h = _finite_float(co2_p.get("moving_avg_1h_mmhg"))
        nasa_ref = _finite_float(co2_p.get("nasa_1h_ref_mmhg")) or 3.0
        if avg_1h is not None:
            ratio = min(1.0, avg_1h / max(0.1, nasa_ref))
            clr = "#fb7185" if ratio >= 1.0 else ("#fbbf24" if ratio >= 0.75 else "#4ade80")
            out.append(f"  ☁ CO₂ prom. 1h:  ", style="#cbd5e1")
            out.append(progress_ratio_bar(ratio, width=16, fill_color=clr))
            out.append(f"  {avg_1h:.2f} / {nasa_ref:g} mmHg\n", style=f"bold {clr}")
        no_sh = _finite_float(rad_p.get("projected_without_shelter"))
        with_sh = _finite_float(rad_p.get("projected_with_shelter"))
        if no_sh is not None and with_sh is not None:
            max_d = max(1.0, no_sh, with_sh)
            out.append("  ☢ Sin refugio:   ", style="#cbd5e1")
            out.append(progress_ratio_bar(no_sh / max_d, width=16, fill_color="#fb7185"))
            out.append(f"  {no_sh:.2f} μSv\n", style="bold #fb7185")
            out.append("  🛡 Con refugio:   ", style="#cbd5e1")
            out.append(progress_ratio_bar(with_sh / max_d, width=16, fill_color="#38bdf8"))
            out.append(f"  {with_sh:.2f} μSv\n", style="bold #38bdf8")
        out.append("\n")

    out.append("PASOS DE REVISIÓN SUGERIDOS\n", style="bold #38bdf8")
    steps = [clean_astronaut_text(s) for s in (rec.get("steps") or []) if clean_astronaut_text(s)]
    if steps:
        for step in steps:
            out.append(f"  ▸ {step}\n", style="#e2e8f0")
    else:
        out.append("  ▸ Mantener observación normal de traje y cabina.\n", style="#94a3b8")

    out.append("\nOTRAS POSIBLES CAUSAS A TENER EN CUENTA\n", style="bold #66e0bd")
    for alt in (eva.get("alternatives") or []):
        out.append(f"  • {clean_astronaut_text(alt)}\n", style="#cbd5e1")

    out.append("\nLÍNEA DE TIEMPO DEL EPISODIO\n", style="bold #38bdf8")
    if timeline:
        recent = list(timeline)[-8:]
        for idx, ev in enumerate(recent):
            raw_at = str(ev.get("at") or "")
            stamp = raw_at[11:19] + " UTC" if len(raw_at) >= 19 else (raw_at or "sin hora")
            txt = clean_astronaut_text(ev.get("text") or "")
            branch = "●──▶ " if idx == len(recent) - 1 else "●──┬ "
            out.append(f"  {branch}", style="#38bdf8")
            out.append(f"[{stamp}] ", style="bold #7dd3fc")
            out.append(f"{txt}\n", style="#cbd5e1")
    else:
        out.append("  ◌ Sin eventos registrados todavía.\n", style="#94a3b8")
    return out


def render_glossary_rich(data: dict[str, Any]) -> Text:
    """Formatea niveles, reglas visuales de rango y señales en bloques coloreados."""
    out = Text()
    out.append("╭─ NIVELES DE AVISO EN CABINA ────────────────────────────────────────────────╮\n", style="bold #38bdf8")
    level_colors = {"normal": "#4ade80", "watch": "#fbbf24", "alert": "#fb7185", "unknown": "#94a3b8"}
    level_icons = {"normal": "●", "watch": "▲", "alert": "■", "unknown": "◌"}
    for key, entry in (data.get("levels") or {}).items():
        clr = level_colors.get(key, "#93c5fd")
        lic = level_icons.get(key, "◈")
        lbl = str(entry.get("label", key)).upper()
        out.append("│ ", style="#27435e")
        out.append(f"╔═ {lic} {lbl} ═╗ ", style=f"bold {clr}")
        out.append(f"{entry.get('meaning', '')}\n", style="#e2e8f0")
        out.append(f"│   Qué hacer: {entry.get('what_to_do', '')}\n", style="#93c5fd")
        out.append(f"│   Ten en cuenta: {entry.get('limitations', '')}\n", style="#94a3b8")
    out.append("╰─────────────────────────────────────────────────────────────────────────────╯\n\n", style="#27435e")

    out.append("╭─ SENSORES DEL TRAJE Y CABINA ───────────────────────────────────────────────╮\n", style="bold #66e0bd")
    for key, entry in (data.get("signals") or {}).items():
        meta = SIGNAL_VISUAL_META.get(key)
        clr = meta[6] if meta else "#7dd3fc"
        icon = meta[7] if meta else "◈"
        friendly_title, unit, _ = _SIGNAL_TITLES.get(key, (key.replace("_", " ").title(), "", 0))
        out.append("│ ", style="#27435e")
        out.append(f"{icon} {friendly_title}", style=f"bold {clr}")
        if meta is not None:
            nom_lo, nom_hi = meta[2], meta[3]
            out.append(f"   Rango habitual: [ {nom_lo:g} ── ", style="#64748b")
            out.append("▰▰▰▰▰▰", style=clr)
            out.append(f" ── {nom_hi:g} {unit} ]", style="#64748b")
        out.append("\n")
        out.append(f"│   Qué mide:    {entry.get('what_is', '')}\n", style="#e2e8f0")
        out.append(f"│   Importancia: {entry.get('why_it_matters', '')}\n", style="#cbd5e1")
        out.append(f"│   Qué revisar: {entry.get('what_to_do', '')}\n", style="#93c5fd")
        out.append(f"│   Límites:     {entry.get('limitations', '')}\n", style="#94a3b8")
    out.append("╰─────────────────────────────────────────────────────────────────────────────╯", style="#27435e")
    return out


def build_signal_tooltip(
    key: str,
    current_value: Any = None,
    extra_val: Any = None,
    baseline: dict[str, Any] | None = None,
) -> str:
    """Construye texto explicativo sencillo y orientado al astronauta para tooltips y hover."""
    title, unit, dec = _SIGNAL_TITLES.get(key, (key.upper(), "", 1))
    meta = SIGNAL_VISUAL_META.get(key)
    entry = SIGNAL_GLOSSARY.get(key, {})

    num = _finite_float(current_value)
    if num is None:
        estado_line = (
            "Estado actual: ◌ SIN SEÑAL (—) · El sensor no está enviando datos en este momento."
        )
    else:
        sev = channel_severity(num, key)
        sev_label = _SEVERITY_STYLE.get(sev, _SEVERITY_STYLE["nominal"])[0]
        if key == "bp_sys":
            dia_num = _finite_float(extra_val)
            val_txt = f"{num:.0f}/{dia_num:.0f} {unit}" if dia_num is not None else f"{num:.0f}/— {unit}"
        else:
            val_txt = f"{num:.{dec}f} {unit}".strip()
        nom_txt = f" · rango habitual en misión: {meta[2]:g}–{meta[3]:g} {unit}" if meta else ""
        base_txt = ""
        if isinstance(baseline, dict) and baseline.get("status") == "ready" and key in {"hr", "rr"}:
            bval = _finite_float(baseline.get(key))
            if bval is not None:
                delta = num - bval
                sign = "+" if delta >= 0 else ""
                base_txt = f" · frente a tu descanso ({bval:.1f}): {sign}{delta:.1f}"
        estado_line = f"Estado actual: {val_txt} [{sev_label}]{nom_txt}{base_txt}"

    lines = [
        f"{title}",
        estado_line,
        f"• Qué mide: {entry.get('what_is', 'Indicador de tu traje o cabina.')}",
        f"• Por qué te importa: {entry.get('why_it_matters', '')}",
        f"• Qué revisar: {entry.get('what_to_do', '')}",
        f"• Ten en cuenta: {entry.get('limitations', '')}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))


WIDGET_HOVER_HELP: dict[str, tuple[str, str]] = {
    "brand": (
        "Reloj de Misión y Estado de Cabina",
        "Muestra la hora de misión y confirma que tu monitor funciona directamente a bordo sin depender de la señal con Tierra.",
    ),
    "status-bar": (
        "Resumen Rápido de Misión",
        (
            f"Te muestra de un vistazo si estás en estado {LEVEL_GLOSSARY['normal']['label']}, {LEVEL_GLOSSARY['watch']['label']}, "
            f"{LEVEL_GLOSSARY['alert']['label']} o {LEVEL_GLOSSARY['unknown']['label']}, en qué módulo te encuentras, si estás en refugio solar y tus puntos de hábitos."
        ),
    ),
    "oscilloscope-panel": (
        "Latido en Vivo y Evolución de Tu Pulso",
        "Muestra el ritmo de tu corazón instante a instante junto con la estimación de cómo se comportará tu pulso en el próximo minuto.",
    ),
    "oscilloscope-box": (
        "Monitor de Latido en Vivo",
        "Sigue el ritmo de tu pulso cuando la banda del traje está conectada. Si falta contacto, se queda en espera mostrando SIN SEÑAL (—).",
    ),
    "ml-braille-box": (
        "Tendencia Esperada de Pulso (+1 min)",
        "Compara tu pulso reciente con la evolución esperada en el siguiente minuto según tu actividad actual.",
    ),
    "scanner-panel": (
        "Estado del Traje por Zonas",
        "Mapa rápido de tu cuerpo y traje espacial: aire del casco, pulmones, corazón, temperatura, hidratación, radiación y actividad.",
    ),
    "body-scanner-box": (
        "Mapa Corporal de 7 Zonas",
        "Cada parte cambia de color si requiere atención o te avisa con SIN SEÑAL (—) cuando un sensor está desconectado.",
    ),
    "analysis-panel": (
        "Lectura Integral a Bordo",
        "Explica en palabras simples qué puede estar pasando con tus signos, qué sensores respaldan esa lectura y qué revisar primero.",
    ),
    "hypothesis": (
        "Interpretación Orientativa",
        "Ayuda de apoyo para la tripulación según tus lecturas y tarea actual. No es una evaluación médica.",
    ),
    "evidence": (
        "Señales Observadas",
        "Resumen de los cambios más claros detectados por los sensores de tu traje y cabina.",
    ),
    "next-step": (
        "Qué Revisar Primero",
        "Recomendación práctica de revisión: confirmar si estás esforzándote, revisar sensores o comprobar ventilación y refugio.",
    ),
    "ml-summary": (
        "Calibración Personal y Patrones",
        "Muestra tu pulso y respiración habituales cuando descansas, si tu respiración reacciona al aire cargado y qué patrón de actividad se observa.",
    ),
    "mission-panel": (
        "Aire de Cabina, Radiación Solar y Bitácora",
        "Vigila el aire acumulado (CO₂), cuánto falta para el límite de cabina, el resguardo ante tormenta solar y tus últimas acciones.",
    ),
    "projections-box": (
        "Previsión de Aire y Radiación (+1 h)",
        "Calcula cuánto aire viciado hay en promedio hacia el límite de cabina (3.0 mmHg) y cuánta radiación evitas al pasar a zona de refugio.",
    ),
    "donki-box": (
        "Alerta de Tormenta Solar (DONKI)",
        "Indica en qué etapa va una tormenta de radiación solar: vigilancia, llegada de partículas, pico máximo o calma.",
    ),
    "question-prompt": (
        "¿Qué Estás Haciendo Ahora?",
        "Avisar si estás descansando, haciendo ejercicio o recuperándote ayuda a que la consola entienda por qué subió tu pulso.",
    ),
    "btn-act-rest": ("En Reposo", "Indica que estás tranquilo o descansando para calibrar tu ritmo base."),
    "btn-act-exercise": ("En Ejercicio", "Indica que estás realizando esfuerzo físico o caminata espacial."),
    "btn-act-recovery": ("En Recuperación", "Indica que terminaste el ejercicio y estás bajando pulsaciones."),
    "btn-ack-alert": ("Confirmar Aviso", "Confirma que ya viste la alerta actual (+5 pts de hábito); el monitor seguirá vigilando hasta que baje."),
    "events-box": ("Bitácora Reciente", "Historial breve con los últimos avisos de cabina, cambios de actividad y chequeos realizados."),
    "trends-header": ("Resumen de Tu Última Hora", "Muestra cuántas lecturas se han recogido sin rellenar huecos si algún sensor se soltó."),
    "trends-table": ("Resumen Estadístico de Sensores", "Valores mínimo, máximo, promedio y actual de cada sensor frente a tu ritmo en descanso."),
    "braille-trend-hr": ("Evolución del Pulso", build_signal_tooltip("hr")),
    "braille-trend-rr": ("Evolución de Respiración", build_signal_tooltip("rr")),
    "braille-trend-co2": ("Evolución de CO₂ en Cabina", build_signal_tooltip("co2")),
    "braille-trend-dose_rate": ("Evolución de Radiación", build_signal_tooltip("dose_rate")),
    "rxn-status": ("Tu Prueba de Reflejos", "Mide qué tan ágil estás hoy en 6 intentos rápidos frente a tu propia marca habitual."),
    "rxn-Visual-chart": ("Gráfica de Tus 6 Intentos", "Muestra tus tiempos en milisegundos, horas de descanso y estado de ánimo de hoy."),
    "btn-rxn-pad": ("Pulsa Cuando Cambie a Verde", "Espera a que el botón se ponga verde («¡AHORA!») y presiona clic o la barra espaciadora."),
    "btn-rxn-start": ("Empezar Prueba de Reflejos", "Inicia 6 intentos cortos para medir tu atención y rapidez de respuesta."),
    "rxn-self-report": ("Sueño y Ánimo de Hoy", "Registra cuántas horas dormiste y cómo te sientes; por defecto queda privado solo para ti."),
    "btn-checkin-submit": ("Guardar Mi Chequeo de Bienestar", "Guarda tus reflejos, sueño y ánimo del día (+15 pts fijos por constancia, sin importar tu velocidad)."),
    "btn-checkin-quick": ("Registro Rápido de Bienestar", "Guarda un chequeo rápido de ánimo y descanso con una muestra de referencia."),
    "coach-header": ("Tus Hábitos de Misión", "Ganas puntos y rachas únicamente por cumplir tus chequeos de agua, aire y descanso; nunca te penalizan por tus signos."),
    "routine-row-checkin": ("Chequeo de Atención y Sueño", "Rutina breve para observar cómo descansas y respondes a lo largo de la misión."),
    "routine-row-hydration": ("Rutina de Hidratación", "Recordatorio para beber agua y evitar deshidratación en ingravidez o dentro del traje."),
    "routine-row-exercise": ("Rutina de Ejercicio", "Actividad física diaria para cuidar corazón, músculos y huesos en el espacio."),
    "routine-row-co2_check": ("Revisión de Ventilación y CO₂", "Comprobación rápida del flujo de aire y purificadores de cabina."),
    "routine-row-shelter_checklist": ("Lista de Protección Solar", "Pasos rápidos para confirmar que tu zona de refugio está lista durante una tormenta solar."),
    "privacy-banner": ("Tu Control de Privacidad", "Puedes elegir que tus horas de sueño, ánimo y reflejos queden solo contigo en cabina o incluirlos en el reporte."),
    "btn-privacy-toggle": ("Cambiar Privacidad del Reporte", "Activa o desactiva si compartes tu resumen de bienestar en el informe de misión."),
    "btn-report-refresh": ("Actualizar Informe", "Genera de nuevo el resumen de misión con los últimos signos y eventos."),
    "btn-report-export": ("Guardar Copia del Informe", "Guarda el informe completo de tu episodio en un archivo listo para entregar a control de misión."),
    "report-visual-cards": ("Resumen Visual del Episodio", "Organiza lo ocurrido en 4 bloques claros: Situación, Antecedentes, Lectura orientativa y Siguiente paso."),
    "report-markdown": ("Informe Detallado de Misión", "Documento completo listo para revisar o guardar cuando haya comunicaciones con Tierra."),
    "glossary-content": ("Guía de Ayuda de Sensores", "Explicación sencilla de qué significa cada medida del traje, la cabina y los colores de alerta."),
    # Controles del Simulador Externo (sim_tui.py)
    "scn-rest": ("Escenario 1 · Descanso en Cabina", "Simula signos tranquilos de un astronauta descansando para observar los valores de referencia."),
    "scn-exercise": ("Escenario 2 · Caminata / Ejercicio", "Simula esfuerzo físico del astronauta con pulso y respiración elevados de forma normal."),
    "scn-cabin": ("Escenario 3 · Aire Cargado en Cabina", "Simula acumulación de CO₂ en cabina que hace respirar más rápido al tripulante."),
    "scn-co2_ramp": ("Escenario 4 · Subida Progresiva de CO₂", "Aumenta el CO₂ poco a poco para ver cómo se calcula el tiempo restante antes del límite de cabina."),
    "scn-solar_event": ("Escenario 5 · Tormenta Solar DONKI", "Simula una tormenta solar con aumento de radiación; prueba activar el Refugio para ver cuánto protege."),
    "scn-signal_loss": ("Escenario 6 · Desconexión de Sensores", "Simula falla o mal contacto del traje espacial para comprobar que la pantalla avisa SIN SEÑAL (—)."),
    "scn-bidmc": ("Escenario 7 · Registro Histórico Real", "Reproduce pulso y respiración reales dejando sin señal los sensores espaciales de cabina y radiación."),
    "env-station": ("Entorno · Estación Orbital", "Simula condiciones dentro de una estación espacial en órbita."),
    "env-transit": ("Entorno · Nave en Tránsito", "Simula viaje en cápsula o nave rumbo a órbita lunar o Marte."),
    "env-rover": ("Entorno · Vehículo Explorador / Caminata", "Simula exploración en superficie donde el astronauta realiza mayor esfuerzo y vigila la radiación."),
    "env-base": ("Entorno · Base Lunar", "Simula hábitat instalado en superficie lunar con acceso rápido a refugio."),
    "phase-watch": ("Etapa Solar · Vigilancia", "Inicio de aviso por tormenta solar DONKI antes de que suba la radiación en cabina."),
    "phase-arrival": ("Etapa Solar · Llegada", "Comienzan a llegar las primeras partículas de la tormenta solar."),
    "phase-peak": ("Etapa Solar · Pico Máximo", "Momento de radiación más alta; ideal para comprobar el ahorro usando Refugio."),
    "phase-decay": ("Etapa Solar · Descenso", "La tormenta solar empieza a ceder y bajan los niveles de radiación."),
    "btn-sim-pause": ("Pausar Simulación Automática", "Detiene o reanuda el envío automático de datos cada segundo."),
    "btn-sim-shelter": ("Activar Zona de Refugio", "Simula resguardar al astronauta en zona blindada reduciendo la radiación entrante."),
    "sim-onboard-mirror": ("Lo Que Ve el Astronauta Ahora", "Vista espejo de los signos y alertas que está viendo en tiempo real la consola de cabina."),
    "btn-send-manual": ("Enviar Lectura del Traje", "Envía una sola lectura con los valores manuales del traje hacia la consola del astronauta."),
    "btn-stream-manual": ("Envío Continuo del Traje (1/seg)", "Manda tus valores manuales cada segundo como si llevaras puesto el traje en vivo."),
    "manual-packet-preview": ("Resumen de Lecturas del Traje", "Muestra exactamente los valores actuales de cada sensor del traje antes de enviarlos."),
}


def format_hover_inspector(title: str, detail: str) -> Text:
    """Formatea la barra inspectora inferior de 2 líneas al pasar el mouse."""
    clean_detail = " · ".join(part.strip() for part in detail.splitlines() if part.strip())
    if len(clean_detail) > 220:
        clean_detail = clean_detail[:217].rstrip() + "..."
    out = Text()
    out.append(f"◈ GUÍA HOVER · {title}\n", style="bold #38bdf8")
    out.append(clean_detail, style="#cbd5e1")
    return out


def format_tooltip_inspector(tip: str, fallback_title: str = "Ayuda en Pantalla") -> Text:
    """Extrae un título amigable de un tooltip multilínea sin exponer IDs internos."""
    lines = [line.strip() for line in str(tip).splitlines() if line.strip()]
    if not lines:
        return format_hover_inspector(fallback_title, "")
    if len(lines) == 1:
        return format_hover_inspector(fallback_title, lines[0])
    return format_hover_inspector(lines[0], " · ".join(lines[1:]))
