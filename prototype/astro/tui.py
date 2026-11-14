"""Consola Operacional TUI de ASTRO-VITALS (v0.2): HUD gráfico estilo btop, 100% terminal."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import random
import statistics
import time
from typing import Any

import httpx
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)

from astro.tui_graphics import (
    SIGNAL_VISUAL_META,
    WIDGET_HOVER_HELP,
    braille_chart,
    build_signal_tooltip,
    channel_severity,
    clean_astronaut_text,
    filter_astronaut_evidence,
    format_hover_inspector,
    format_tooltip_inspector,
    gauge_bar,
    humanize_activity,
    humanize_level,
    humanize_reason,
    humanize_source,
    progress_ratio_bar,
    render_astronaut_ai_panel,
    render_body_scanner,
    render_checkin_result_card,
    render_coach_dashboard_hud,
    render_ecg_oscilloscope,
    render_glossary_rich,
    render_ml_forecast_braille,
    render_privacy_hud_banner,
    render_reaction_cockpit,
    render_reaction_histogram,
    render_routine_card_hud,
    render_sbar_cards,
    render_sbar_details,
    render_trends_summary_hud,
    severity_color,
)

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"

LEVELS: dict[str, tuple[str, str]] = {
    "normal": ("● ESTABLE", "#4ade80"),
    "watch": ("▲ REVISAR", "#fbbf24"),
    "alert": ("■ ATENCIÓN", "#fb7185"),
    "unknown": ("◌ SIN EVALUACIÓN", "#94a3b8"),
}

SIGNAL_SPECS: tuple[tuple[str, str, str, int], ...] = (
    ("hr", "FREC. CARDÍACA", "bpm", 0),
    ("rr", "RESPIRACIÓN", "resp/min", 0),
    ("spo2", "SATURACIÓN SpO₂", "%", 1),
    ("temp_c", "TEMPERATURA", "°C", 1),
    ("bp_sys", "PRESIÓN ARTERIAL", "mmHg", 0),
    ("co2", "ppCO₂ CABINA", "mmHg", 2),
    ("hydration_pct", "HIDRATACIÓN", "%", 0),
    ("dose_rate", "TASA DE DOSIS", "μSv/h", 2),
)

ROUTINES_META: tuple[tuple[str, str], ...] = (
    ("checkin", "Check-in de alerta y reacción"),
    ("hydration", "Hidratación de protocolo"),
    ("exercise", "Contramedida física"),
    ("co2_check", "Revisión de sensor/depurador CO₂"),
    ("shelter_checklist", "Lista de verificación de refugio"),
)

ACTIVITIES_CYCLE: tuple[tuple[str, str], ...] = (
    ("rest", "Reposo"),
    ("exercise", "Ejercicio"),
    ("recovery", "Recuperación"),
)

WINDOW_LABELS: dict[int, str] = {
    300: "5 min",
    900: "15 min",
    3600: "1 hora",
}

BADGE_GALLERY: tuple[tuple[str, str], ...] = (
    ("primera_rutina", "★ 1ª Rutina"),
    ("primer_checkin", "⚡ 1er Check-in"),
    ("racha_3", "🔥 Racha x3"),
    ("lista_refugio", "🛡 Refugio"),
)


def _fmt_value(value: Any, decimals: int = 1) -> str:
    if value is None or isinstance(value, bool):
        return "—"
    return f"{float(value):.{decimals}f}"


def _contiguous_series(history: list[dict[str, Any]], key: str, limit: int = 60) -> list[float]:
    """Extrae una serie contigua sin rellenar huecos ni valores None con cero."""
    contiguous: list[float] = []
    newer_at: datetime | None = None
    for sample in reversed(history[-limit:]):
        current = sample.get(key)
        if current is None or isinstance(current, bool):
            break
        raw_ts = sample.get("measured_at")
        if not raw_ts:
            break
        measured_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if newer_at is not None and (newer_at - measured_at).total_seconds() > 5.0:
            break
        contiguous.append(float(current))
        newer_at = measured_at
    contiguous.reverse()
    return contiguous


class MetricCard(Vertical):
    """Tarjeta HUD btop con valor, barra segmentada ▰▰◆▱▱, delta y sparkline contiguo."""

    def __init__(self, key: str, title: str, unit: str, decimals: int = 1) -> None:
        super().__init__(id=f"card-{key}", classes="metric is-missing")
        self.key = key
        self.caption = title
        self.unit = unit
        self.decimals = decimals
        initial_tip = build_signal_tooltip(self.key)
        self.tooltip = initial_tip
        self.hover_title = f"{self.caption} ({self.unit})"
        self.hover_summary = initial_tip

    def compose(self) -> ComposeResult:
        meta = SIGNAL_VISUAL_META.get(self.key)
        icon = meta[7] if meta else "◈"
        accent = meta[6] if meta else "#7dd3fc"
        tip = build_signal_tooltip(self.key)
        lbl = Label(
            Text.assemble((f"{icon} ", f"bold {accent}"), (self.caption, "bold #9bb3cf")),
            classes="metric-label",
        )
        lbl.tooltip = tip
        yield lbl
        val_w = Static("SIN SEÑAL (—)", id=f"value-{self.key}", classes="metric-value is-missing")
        val_w.tooltip = tip
        yield val_w
        gauge_w = Static(gauge_bar(None, self.key, width=14), id=f"gauge-{self.key}", classes="metric-gauge")
        gauge_w.tooltip = tip
        yield gauge_w
        spark_w = Sparkline([], id=f"spark-{self.key}", summary_function=max)
        spark_w.tooltip = tip
        yield spark_w
        unit_w = Label(f"{self.unit} · sin dato", id=f"unit-{self.key}", classes="metric-unit")
        unit_w.tooltip = tip
        yield unit_w

    def update_metric(
        self,
        latest: dict[str, Any],
        history: list[dict[str, Any]],
        baseline: dict[str, Any] | None = None,
    ) -> None:
        value = latest.get(self.key)
        val_widget = self.query_one(f"#value-{self.key}", Static)
        gauge_widget = self.query_one(f"#gauge-{self.key}", Static)
        unit_widget = self.query_one(f"#unit-{self.key}", Label)
        spark_widget = self.query_one(f"#spark-{self.key}", Sparkline)

        clean_val = None if (value is None or isinstance(value, bool)) else value
        tip = build_signal_tooltip(
            self.key,
            clean_val,
            latest.get("bp_dia"),
            baseline=baseline,
        )
        self.tooltip = tip
        self.hover_summary = tip
        val_widget.tooltip = tip
        gauge_widget.tooltip = tip
        spark_widget.tooltip = tip
        unit_widget.tooltip = tip

        for cls in ("is-missing", "is-nominal", "is-warn", "is-alert"):
            self.remove_class(cls)

        if value is None or isinstance(value, bool):
            self.add_class("is-missing")
            val_widget.update("SIN SEÑAL (—)")
            val_widget.add_class("is-missing")
            gauge_widget.update(gauge_bar(None, self.key, width=14))
            spark_widget.data = []
            unit_widget.update(f"{self.unit} · sensor sin señal")
            return

        num = float(value)
        sev = channel_severity(num, self.key)
        sev_clr = severity_color(sev)
        css_cls = {"nominal": "is-nominal", "watch": "is-warn", "alert": "is-alert"}.get(sev, "is-nominal")
        self.add_class(css_cls)
        val_widget.remove_class("is-missing")

        if self.key == "bp_sys":
            dia = latest.get("bp_dia")
            if dia is not None and not isinstance(dia, bool):
                val_text = f"{num:.0f}/{float(dia):.0f}"
            else:
                val_text = f"{num:.0f}/—"
        else:
            val_text = f"{num:.{self.decimals}f}"
        val_widget.update(Text(val_text, style=f"bold {sev_clr}"))

        gauge_txt = gauge_bar(num, self.key, width=14)
        if isinstance(baseline, dict) and baseline.get("status") == "ready" and self.key in {"hr", "rr"}:
            bval = baseline.get(self.key)
            if bval is not None and not isinstance(bval, bool):
                delta = num - float(bval)
                sign = "+" if delta >= 0 else ""
                gauge_txt.append(f" Δ{sign}{delta:.1f}", style="#93c5fd")
        gauge_widget.update(gauge_txt)

        series = _contiguous_series(history, self.key, limit=60)
        spark_widget.data = series
        unit_widget.update(f"{self.unit} · en vivo")


class AstroVitalsApp(App):
    """Consola operacional HUD TUI para monitoreo a bordo (separada del simulador externo)."""

    TITLE = "ASTRO-VITALS · Bio-Telemetry HUD"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #060d17; color: #dbe6f4; }
    #brand {
        height: 2; padding: 0 2; background: #0c192b;
        color: #dbe6f4; border-bottom: solid #1e3a5f;
        content-align: left middle;
    }
    #status-bar {
        height: 2; padding: 0 2; background: #0f2036;
        color: #a7bdd8; border-bottom: solid #243e5c;
    }
    TabbedContent { height: 1fr; }
    ContentSwitcher { height: 1fr; }
    TabPane { padding: 1 2; height: 1fr; }

    .metrics-row { height: 10; margin-bottom: 1; }
    .metric {
        width: 1fr; height: 10; border: round #27435e;
        margin-right: 1; padding: 0 1; background: #0a1422;
    }
    .metric.is-nominal { border: round #1f6f63; }
    .metric.is-warn { border: round #9a6d1f; }
    .metric.is-alert { border: heavy #a63244; background: #190d14; }
    .metric.is-missing { border: dashed #855e1c; }
    .metric-label { color: #8fa6c2; height: 1; text-style: bold; }
    .metric-value { text-style: bold; color: #4ade80; height: 2; padding-top: 1; }
    .metric-value.is-missing { color: #fbbf24; }
    .metric-gauge { height: 1; }
    Sparkline { height: 2; color: #38bdf8; background: #0e1c2f; }
    .metric-unit { color: #7e97b5; height: 1; }

    #graphic-hud-row { height: auto; min-height: 15; margin-bottom: 1; }
    #oscilloscope-panel {
        width: 1fr; height: auto; min-height: 15; border: round #1e4b6e;
        padding: 1 2; margin-right: 1; background: #081220;
    }
    #scanner-panel {
        width: 1fr; height: auto; min-height: 15; border: round #1e4b6e;
        padding: 1 2; background: #081220;
    }
    #oscilloscope-box { height: auto; margin-bottom: 1; }
    #ml-braille-box { height: auto; border-top: solid #1a314d; padding-top: 1; }
    #body-scanner-box { height: auto; }

    #detail-row { height: auto; min-height: 16; }
    #analysis-panel {
        width: 3fr; height: auto; min-height: 16; border: round #27435e;
        padding: 1 2; margin-right: 1; background: #0a1422;
    }
    #mission-panel {
        width: 2fr; height: auto; min-height: 16; border: round #27435e;
        padding: 1 2; background: #0a1422;
    }
    .panel-title { color: #38bdf8; text-style: bold; margin-bottom: 1; }
    #hypothesis {
        height: auto; text-style: bold; padding: 0 1;
        border-left: heavy #38bdf8; background: #0f1f36; margin-bottom: 1;
    }
    #evidence, #next-step, #ml-summary, #projections-box, #donki-box, #events-box {
        height: auto; margin-bottom: 1;
    }
    #question-prompt { height: auto; margin-bottom: 1; color: #ffca73; }
    .action-row { height: 3; margin-top: 1; margin-bottom: 1; }
    Button {
        min-width: 12; height: 3; margin-right: 1;
        background: #14283f; color: #d5e4f7; border: tall transparent;
    }
    Button:hover { background: #1e3b5c; }
    Button.selected { background: #155e57; color: #9cf5dc; text-style: bold; }
    Button.warn-btn { background: #4a3512; color: #ffda8a; }
    Button.alert-btn { background: #4f1d24; color: #ffb3ba; }

    .box {
        border: round #27435e; padding: 1 2; margin-bottom: 1;
        background: #0a1422; height: auto;
    }

    #trends-braille-grid { height: auto; margin-bottom: 1; }
    .braille-row { height: auto; margin-bottom: 1; }
    .braille-card {
        width: 1fr; height: auto; min-height: 9; border: round #1e4b6e;
        margin-right: 1; padding: 0 1; background: #081220;
    }
    #trends-table { height: 11; margin-bottom: 1; background: #0a1422; }
    .trend-sparks { height: 7; margin-bottom: 1; }
    .trend-spark-card {
        width: 1fr; height: 7; border: round #27435e;
        margin-right: 1; padding: 0 1; background: #0a1422;
    }

    #rxn-status, #rxn-Visual-chart {
        border: round #1e4b6e; background: #081220;
        padding: 1 2; margin-bottom: 1; height: auto;
    }
    #rxn-self-report {
        width: auto; padding: 0 2; height: 3; content-align: center middle;
        border: round #1e4b6e; background: #0c192b; color: #dbe6f4;
    }
    #btn-rxn-pad {
        width: 1fr; height: 5; margin: 1 0; text-style: bold;
        border: heavy #38bdf8;
    }
    #btn-rxn-pad.is-waiting { background: #5a3e0a; color: #fde68a; border: heavy #fbbf24; }
    #btn-rxn-pad.is-go { background: #0e6b3d; color: #ecfdf5; border: heavy #4ade80; }
    #btn-rxn-pad.is-false { background: #6b1d28; color: #ffe4e6; border: heavy #fb7185; }
    #btn-rxn-pad.is-done { background: #144363; color: #e0f2fe; border: heavy #38bdf8; }

    .routine-row {
        height: auto; min-height: 4; border: round #233b54;
        padding: 0 1; margin-bottom: 1; background: #0b1626;
    }
    .routine-row.is-due { border: round #9a6d1f; }
    .routine-info { width: 1fr; height: auto; padding-top: 1; }

    #report-scroll, #glossary-scroll {
        height: 1fr; border: round #27435e; padding: 1 2; background: #09121e;
    }
    #report-visual-cards { height: auto; margin-bottom: 1; }
    #report-markdown { height: auto; border-top: solid #1e3a5f; padding-top: 1; }
    #notice { color: #8ea4c1; margin-top: 1; height: auto; }
    Tooltip {
        background: #0d2137; color: #f1f5f9;
        border: round #38bdf8; padding: 1 2; max-width: 74;
    }
    #hover-inspector {
        height: 2; padding: 0 2; background: #0a192f;
        color: #cbd5e1; border-top: solid #1e4b6e;
    }
    Footer { background: #0c192b; }
    """

    BINDINGS = [
        Binding("1", "switch_tab('tab-monitor')", "Monitor", show=True),
        Binding("m", "switch_tab('tab-monitor')", "Monitor", show=False),
        Binding("t", "switch_tab('tab-trends')", "Tendencias", show=True),
        Binding("c", "switch_tab('tab-checkin')", "Check-in", show=True),
        Binding("r", "switch_tab('tab-routines')", "Rutinas", show=True),
        Binding("i", "switch_tab('tab-report')", "Informe SBAR", show=True),
        Binding("h", "switch_tab('tab-glossary')", "Glosario", show=True),
        Binding("a", "acknowledge", "Reconocer (ACK)", show=True),
        Binding("x", "cycle_activity", "Actividad", show=True),
        Binding("v", "toggle_privacy", "Privacidad SBAR", show=True),
        Binding("q", "quit", "Salir", show=True),
    ]

    def __init__(self, onboard_url: str | None = None) -> None:
        super().__init__()
        self.onboard_url = (
            onboard_url or os.getenv("ONBOARD_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.client: httpx.AsyncClient | None = None
        self.last_state: dict[str, Any] | None = None
        self.refreshing = False
        self.trends_window_s = 3600
        self.glossary_loaded = False
        self.activity_idx = 0
        self.ecg_tick = 0
        self._last_hover_signature: str | None = None

        # Estado del minijuego de reacción (6 intentos en terminal)
        self.rxn_phase = "idle"
        self.rxn_trial = 0
        self.rxn_total_trials = 6
        self.rxn_times: list[float] = []
        self.rxn_false_starts = 0
        self.rxn_lapses = 0
        self.rxn_go_at = 0.0
        self.rxn_sleep_hours = 7.0
        self.rxn_mood = 3
        self.rxn_timer = None
        self._rng = random.Random()

    def compose(self) -> ComposeResult:
        yield Static(self._render_brand(), id="brand")
        yield Static("Conectando con el nodo a bordo…", id="status-bar")

        with TabbedContent(initial="tab-monitor", id="main-tabs"):
            with TabPane("01 · MONITOR E IA", id="tab-monitor"):
                with VerticalScroll():
                    with Horizontal(id="metrics-row-1", classes="metrics-row"):
                        for key, title, unit, dec in SIGNAL_SPECS[:4]:
                            yield MetricCard(key, title, unit, dec)
                    with Horizontal(id="metrics-row-2", classes="metrics-row"):
                        for key, title, unit, dec in SIGNAL_SPECS[4:]:
                            yield MetricCard(key, title, unit, dec)

                    with Horizontal(id="graphic-hud-row"):
                        with Vertical(id="oscilloscope-panel"):
                            yield Label("MONITOR DE LATIDO Y EVOLUCIÓN (+1 MIN)", classes="panel-title")
                            yield Static(
                                render_ecg_oscilloscope(None, None, None, "unknown", 0, width=42),
                                id="oscilloscope-box",
                            )
                            yield Static(
                                render_ml_forecast_braille([], {}, width=40),
                                id="ml-braille-box",
                            )
                        with Vertical(id="scanner-panel"):
                            yield Label("ESTADO DEL TRAJE POR ZONAS", classes="panel-title")
                            yield Static(
                                render_body_scanner({}, {"level": "unknown"}, None, False),
                                id="body-scanner-box",
                            )

                    with Horizontal(id="detail-row"):
                        with Vertical(id="analysis-panel"):
                            yield Label("ESTADO ACTUAL Y PREDICCIÓN A BORDO", classes="panel-title")
                            yield Static("Esperando lecturas del traje y cabina…", id="hypothesis")
                            yield Static("", id="evidence")
                            yield Static("", id="next-step")
                            yield Static("Preparando pronóstico de pulso y referencia personal…", id="ml-summary")

                        with Vertical(id="mission-panel"):
                            yield Label("AIRE DE CABINA, RADIACIÓN Y ACTIVIDAD", classes="panel-title")
                            yield Static("Calculando aire de cabina y radiación…", id="projections-box")
                            yield Static("Sin alerta de tormenta solar activa.", id="donki-box")
                            yield Label("CONFIRMAR TU ACTIVIDAD ACTUAL", classes="panel-title")
                            yield Static(
                                "Confirma si estás descansando o en esfuerzo físico.",
                                id="question-prompt",
                            )
                            with Horizontal(classes="action-row"):
                                yield Button("Reposo", id="btn-act-rest")
                                yield Button("Ejercicio", id="btn-act-exercise")
                                yield Button("Recup.", id="btn-act-recovery")
                                yield Button("Confirmar aviso [A]", id="btn-ack-alert", classes="warn-btn")
                            yield Label("BITÁCORA DE CABINA", classes="panel-title")
                            yield Static("Los eventos aparecerán aquí.", id="events-box")

                    yield Static(
                        "Guía rápida: si un sensor pierde contacto verás SIN SEÑAL (—); comprueba el ajuste de tu traje.",
                        id="notice",
                    )

            with TabPane("02 · TENDENCIAS 1H", id="tab-trends"):
                with VerticalScroll():
                    with Horizontal(classes="action-row"):
                        yield Button("5 min", id="btn-win-300")
                        yield Button("15 min", id="btn-win-900")
                        yield Button("1 hora", id="btn-win-3600", classes="selected")
                        yield Button("Actualizar tendencias", id="btn-trends-refresh")
                    yield Static("Ventana: 1 hora · Esperando muestras…", id="trends-header", classes="box")
                    with Vertical(id="trends-braille-grid"):
                        with Horizontal(classes="braille-row"):
                            with Vertical(classes="braille-card"):
                                yield Label("CURVA BRAILLE · FC (bpm) [ref. línea base]", classes="metric-label")
                                yield Static(braille_chart([], width=42, height=4, unit="bpm"), id="braille-trend-hr")
                            with Vertical(classes="braille-card"):
                                yield Label("CURVA BRAILLE · FR (resp/min) [ref. línea base]", classes="metric-label")
                                yield Static(braille_chart([], width=42, height=4, unit="rpm"), id="braille-trend-rr")
                        with Horizontal(classes="braille-row"):
                            with Vertical(classes="braille-card"):
                                yield Label("CURVA BRAILLE · ppCO₂ (mmHg) [límite NASA 3.0]", classes="metric-label")
                                yield Static(braille_chart([], width=42, height=4, unit="mmHg"), id="braille-trend-co2")
                            with Vertical(classes="braille-card"):
                                yield Label("CURVA BRAILLE · TASA DE DOSIS (μSv/h)", classes="metric-label")
                                yield Static(braille_chart([], width=42, height=4, unit="μSv/h"), id="braille-trend-dose_rate")
                    yield DataTable(id="trends-table")
                    with Horizontal(classes="trend-sparks"):
                        for key, title in (
                            ("hr", "HISTORIAL FC (bpm)"),
                            ("rr", "HISTORIAL FR (resp/min)"),
                            ("co2", "HISTORIAL ppCO₂ (mmHg)"),
                            ("dose_rate", "HISTORIAL DOSIS (μSv/h)"),
                        ):
                            with Vertical(classes="trend-spark-card"):
                                yield Label(title, classes="metric-label")
                                yield Sparkline([], id=f"trend-spark-{key}", summary_function=max)
                                yield Label("sin datos", id=f"trend-meta-{key}", classes="metric-unit")

            with TabPane("03 · CHECK-IN / REACCIÓN", id="tab-checkin"):
                with VerticalScroll():
                    yield Static(
                        "🎮 PRUEBA DE REFLEJOS Y BIENESTAR · 6 intentos rápidos frente a tu propia marca habitual.",
                        classes="box",
                    )
                    yield Static(
                        render_reaction_cockpit("idle", 0, 6, [], 0, 0, None),
                        id="rxn-status",
                    )
                    yield Static(
                        render_reaction_histogram([], None, 7.0, 3, current_trial=0, phase="idle"),
                        id="rxn-Visual-chart",
                    )
                    yield Button(
                        "PULSA «INICIAR 6 INTENTOS» PARA COMENZAR (BARRA ESPACIADORA O CLIC)",
                        id="btn-rxn-pad",
                        disabled=True,
                    )
                    with Horizontal(classes="action-row"):
                        yield Button("Iniciar 6 intentos", id="btn-rxn-start")
                        yield Button("Sueño -0.5h", id="btn-sleep-dec")
                        yield Button("Sueño +0.5h", id="btn-sleep-inc")
                        yield Static("🔋 7.0 h | ✨ 3/5", id="rxn-self-report")
                    with Horizontal(classes="action-row"):
                        for score in range(1, 6):
                            yield Button(f"Ánimo {'★' * score} ({score})", id=f"btn-mood-{score}")
                    with Horizontal(classes="action-row"):
                        yield Button(
                            "Guardar mi prueba de hoy (+15 pts)",
                            id="btn-checkin-submit",
                            disabled=True,
                        )
                        yield Button(
                            "Registro rápido de bienestar",
                            id="btn-checkin-quick",
                        )
                    yield Static("Completa los 6 intentos y guarda tu prueba para ver el comparativo del día.", id="checkin-result", classes="box")

            with TabPane("04 · RUTINAS Y COACH", id="tab-routines"):
                with VerticalScroll():
                    yield Static("Cargando tu panel de hábitos y medallas…", id="coach-header", classes="box")
                    for rid, default_title in ROUTINES_META:
                        with Horizontal(id=f"routine-row-{rid}", classes="routine-row"):
                            yield Static(
                                f"{default_title}\nEsperando lecturas…",
                                id=f"routine-info-{rid}",
                                classes="routine-info",
                            )
                            yield Button(
                                "Completar (+10 pts)",
                                id=f"btn-routine-{rid}",
                            )

            with TabPane("05 · INFORME SBAR", id="tab-report"):
                with VerticalScroll():
                    yield Static(
                        render_privacy_hud_banner(False),
                        id="privacy-banner",
                    )
                    with Horizontal(classes="action-row"):
                        yield Button("Cambiar Privacidad SBAR [V]", id="btn-privacy-toggle")
                        yield Button("Recargar Informe", id="btn-report-refresh")
                        yield Button("Guardar informe de misión", id="btn-report-export")
                    with VerticalScroll(id="report-scroll"):
                        yield Static("Cargando cuadrantes SBAR…", id="report-visual-cards")
                        yield Static("Cargando informe SBAR…", id="report-markdown")

            with TabPane("06 · GLOSARIO", id="tab-glossary"):
                with VerticalScroll(id="glossary-scroll"):
                    with Horizontal(classes="action-row"):
                        yield Button("Recargar Glosario", id="btn-glossary-refresh")
                    yield Static("Cargando glosario orientativo de señales y niveles…", id="glossary-content")

        yield Static(
            format_hover_inspector(
                "Consola Operacional",
                "Pasa el mouse sobre cualquier señal, gráfica Braille, zona del traje o botón para ver qué significa y cómo interpretarlo.",
            ),
            id="hover-inspector",
        )
        yield Footer()

    def _render_brand(self) -> Text:
        utc_now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        return Text.assemble(
            ("◈ ASTRO-VITALS // BIO-TELEMETRY HUD v0.2", "bold #4ade80"),
            ("   ·   OPERACIÓN AUTÓNOMA EN CABINA   ·   ", "bold #93c5fd"),
            (f"MET {utc_now}", "bold #e2e8f0"),
        )

    async def on_mount(self) -> None:
        table = self.query_one("#trends-table", DataTable)
        table.add_columns(
            "Señal",
            "Unidad",
            "Muestras",
            "Mínimo",
            "Máximo",
            "Media",
            "Último",
            "Base Personal",
        )
        self.client = httpx.AsyncClient(timeout=2.0, trust_env=False)
        self.set_interval(1.0, self.refresh_data)
        self.set_interval(0.5, self._tick_oscilloscope)
        self._bind_static_tooltips()
        self._update_self_report_label()
        await self.refresh_data()
        await self.load_glossary()
        await self.refresh_trends()
        await self.refresh_report()

    def _bind_static_tooltips(self) -> None:
        for widget_id, (title, detail) in WIDGET_HOVER_HELP.items():
            for widget in self.query(f"#{widget_id}"):
                widget.tooltip = f"{title}\n{detail}"
        for key in ("hr", "rr", "co2", "dose_rate"):
            tip = build_signal_tooltip(key)
            for prefix in ("#trend-spark-", "#braille-trend-"):
                for widget in self.query(f"{prefix}{key}"):
                    widget.tooltip = tip

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self.is_mounted:
            return
        cur = event.widget
        while cur is not None:
            if isinstance(cur, MetricCard):
                sig = f"card:{cur.key}:{cur.hover_summary}"
                if sig != self._last_hover_signature:
                    self._last_hover_signature = sig
                    self.query_one("#hover-inspector", Static).update(
                        format_hover_inspector(cur.hover_title, cur.hover_summary)
                    )
                return
            wid = getattr(cur, "id", None)
            if wid and wid in WIDGET_HOVER_HELP:
                title, detail = WIDGET_HOVER_HELP[wid]
                sig = f"id:{wid}"
                if sig != self._last_hover_signature:
                    self._last_hover_signature = sig
                    self.query_one("#hover-inspector", Static).update(
                        format_hover_inspector(title, detail)
                    )
                return
            tip = getattr(cur, "tooltip", None)
            if tip:
                sig = f"tip:{wid}:{tip}"
                if sig != self._last_hover_signature:
                    self._last_hover_signature = sig
                    self.query_one("#hover-inspector", Static).update(
                        format_tooltip_inspector(str(tip))
                    )
                return
            cur = cur.parent

    async def on_unmount(self) -> None:
        self._cancel_rxn_timer()
        if self.client is not None:
            await self.client.aclose()

    def _cancel_rxn_timer(self) -> None:
        if self.rxn_timer is not None:
            self.rxn_timer.stop()
            self.rxn_timer = None

    def _tick_oscilloscope(self) -> None:
        self.ecg_tick += 1
        if self.is_mounted:
            self.query_one("#brand", Static).update(self._render_brand())
            if self.last_state is not None:
                latest = self.last_state.get("latest") or {}
                self.query_one("#oscilloscope-box", Static).update(
                    render_ecg_oscilloscope(
                        latest.get("hr"),
                        latest.get("rr"),
                        latest.get("spo2"),
                        str(latest.get("activity") or "unknown"),
                        self.ecg_tick,
                        width=42,
                    )
                )

    async def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id
        if tab_id == "tab-trends":
            await self.refresh_trends()
        elif tab_id == "tab-report":
            await self.refresh_report()
        elif tab_id == "tab-glossary" and not self.glossary_loaded:
            await self.load_glossary()

    async def refresh_data(self) -> None:
        if self.refreshing or self.client is None:
            return
        self.refreshing = True
        try:
            response = await self.client.get(f"{self.onboard_url}/api/v1/state")
            response.raise_for_status()
            self.last_state = response.json()
            self.render_state(self.last_state)
        except (httpx.HTTPError, ValueError):
            self.query_one("#status-bar", Static).update(
                Text("● SIN CONEXIÓN CON CABINA · Las lecturas visibles pueden estar desactualizadas.", style="#fb7185")
            )
            self.query_one("#hypothesis", Static).update(
                "Evaluación en espera: revisa la conexión con el módulo a bordo."
            )
        finally:
            self.refreshing = False

    def render_state(self, state: dict[str, Any]) -> None:
        latest = state.get("latest") or {}
        assessment = state.get("assessment") or {}
        baseline = state.get("baseline") or {}
        level_key = str(assessment.get("level", "unknown"))
        level_label, level_color = LEVELS.get(level_key, LEVELS["unknown"])

        env = state.get("environment") or {}
        env_name = env.get("name") or env.get("id") or "Estación"
        raw_source = humanize_source(latest.get("source"))
        age = state.get("age_s")
        age_txt = "sin lecturas" if age is None else f"hace {max(0.0, float(age)):.0f} s"

        privacy = state.get("privacy") or {}
        share_beh = bool(privacy.get("share_behavioral", False))
        priv_badge = "🔓 REPORTE COMPARTIDO" if share_beh else "🔒 SOLO EN CABINA"

        coach = state.get("coach") or {}
        pts = coach.get("points", 0)
        streak = coach.get("streak", 0)
        shelter_active = bool(state.get("shelter_active"))

        status_txt = Text()
        status_txt.append(f" {level_label} ", style=f"bold #06101a on {level_color}")
        status_txt.append(f"  🛰 {env_name}  ", style="bold #bae6fd")
        if shelter_active:
            status_txt.append(" 🛡 EN REFUGIO SOLAR ", style="bold #06101a on #38bdf8")
        if state.get("acknowledged"):
            status_txt.append(" ✓ AVISO VISTO ", style="bold #4ade80")
        status_txt.append(f" │ 📡 {raw_source} ({age_txt}) │ {priv_badge} │ 🏆 {pts} pts · racha {streak}", style="#cbd5e1")
        self.query_one("#status-bar", Static).update(status_txt)

        source_history: list[dict[str, Any]] = []
        current_src = latest.get("source")
        for sample in reversed(state.get("history") or []):
            if sample.get("source") != current_src:
                break
            source_history.append(sample)
        source_history.reverse()

        for card in self.query(MetricCard):
            card.update_metric(latest, source_history, baseline=baseline)

        ml = state.get("ml") or {}
        forecast = ml.get("forecast") or {}
        pattern = ml.get("pattern") or {}
        co2_sens = state.get("co2_sensitivity") or {}

        # Panel gráfico central: osciloscopio ECG + evolución pulso + Escáner Bio-Suit 7 zonas
        self.query_one("#oscilloscope-box", Static).update(
            render_ecg_oscilloscope(
                latest.get("hr"),
                latest.get("rr"),
                latest.get("spo2"),
                str(latest.get("activity") or "unknown"),
                self.ecg_tick,
                width=42,
            )
        )
        self.query_one("#ml-braille-box", Static).update(
            render_ml_forecast_braille(source_history, forecast, width=40)
        )
        self.query_one("#body-scanner-box", Static).update(
            render_body_scanner(
                latest,
                assessment,
                state.get("dose_total"),
                shelter_active,
            )
        )

        hyp_raw = assessment.get("hypothesis") or assessment.get("title") or "Esperando lecturas del traje"
        hyp_clean = clean_astronaut_text(hyp_raw) or "Esperando lecturas del traje"
        hyp_box = Text()
        hyp_box.append(f" {level_label} ", style=f"bold #06101a on {level_color}")
        hyp_box.append(f"  {hyp_clean}", style=f"bold {level_color}")
        self.query_one("#hypothesis", Static).update(hyp_box)

        ev_list = assessment.get("evidence") or []
        pat_hyp = pattern.get("hypothesis") if isinstance(pattern, dict) else None
        clean_ev = filter_astronaut_evidence(ev_list, pattern_hyp=pat_hyp)
        self.query_one("#evidence", Static).update(
            Text("\n".join(f"• {item}" for item in clean_ev) or "• Signos monitorizados en vivo.")
        )
        step_clean = clean_astronaut_text(assessment.get("next_step") or "Esperar lecturas del traje.")
        self.query_one("#next-step", Static).update(
            Text(f"👉 Qué hacer: {step_clean}", style="bold #93c5fd")
        )

        self.query_one("#ml-summary", Static).update(
            render_astronaut_ai_panel(latest, forecast, pattern, baseline, co2_sens)
        )

        # Aire de cabina (CO₂) y Radiación
        proj = state.get("projections") or {}
        co2_p = proj.get("co2") or {}
        rad_p = proj.get("radiation") or {}

        avg_1h = co2_p.get("moving_avg_1h_mmhg")
        nasa_ref = float(co2_p.get("nasa_1h_ref_mmhg", 3.0))
        eta_min = co2_p.get("eta_minutes")
        avg_str = f"{float(avg_1h):.2f} mmHg" if avg_1h is not None else "—"
        eta_str = (
            f"en ~{float(eta_min):.0f} min"
            if eta_min is not None
            else humanize_reason(co2_p.get("reason") or "estable")
        )

        dose_tot = rad_p.get("dose_total_usv", state.get("dose_total", 0.0))
        no_sh = rad_p.get("projected_without_shelter")
        with_sh = rad_p.get("projected_with_shelter")
        cov_dose = "lectura continua" if state.get("dose_complete", True) else "lectura parcial"

        proj_txt = Text()
        proj_txt.append(f"• CO₂ promedio 1h: {avg_str} ", style="#e2e8f0")
        if avg_1h is not None:
            ratio = min(1.0, float(avg_1h) / max(0.1, nasa_ref))
            bar_clr = "#fb7185" if ratio >= 1.0 else ("#fbbf24" if ratio >= 0.75 else "#4ade80")
            proj_txt.append(progress_ratio_bar(ratio, width=12, fill_color=bar_clr))
            proj_txt.append(f" / límite {nasa_ref:g} mmHg\n", style="#94a3b8")
        else:
            proj_txt.append(f"(límite en cabina: {nasa_ref:g} mmHg)\n", style="#94a3b8")
        proj_txt.append(f"• Tiempo hasta límite CO₂: {eta_str}\n", style="#cbd5e1")
        proj_txt.append(f"• Radiación acumulada: {float(dose_tot or 0.0):.3f} μSv ({cov_dose})\n", style="#f472b6")
        if no_sh is not None and with_sh is not None:
            max_d = max(1.0, float(no_sh), float(with_sh))
            proj_txt.append("• En 1h sin refugio: ", style="#cbd5e1")
            proj_txt.append(progress_ratio_bar(float(no_sh) / max_d, width=10, fill_color="#fb7185"))
            proj_txt.append(f" {float(no_sh):.2f} μSv\n", style="#fb7185")
            proj_txt.append("• En 1h con refugio: ", style="#cbd5e1")
            proj_txt.append(progress_ratio_bar(float(with_sh) / max_d, width=10, fill_color="#38bdf8"))
            proj_txt.append(f" {float(with_sh):.2f} μSv", style="#38bdf8")
        else:
            proj_txt.append("• Previsión radiación +1h: esperando sensor", style="#94a3b8")
        self.query_one("#projections-box", Static).update(proj_txt)

        # Tormenta solar con etapas claras en español
        ext = state.get("external_event")
        donki_txt = Text()
        if isinstance(ext, dict) and ext:
            active_phase = str(ext.get("phase", "watch")).lower()
            donki_txt.append(
                f"• Tormenta solar activa ({ext.get('sep_id', 'SOLAR')})\n",
                style="bold #fbbf24",
            )
            donki_txt.append("  Etapa: ", style="#94a3b8")
            solar_phases = (
                ("watch", "VIGILANCIA"),
                ("arrival", "LLEGADA"),
                ("peak", "PICO MÁX."),
                ("decay", "DESCENSO"),
            )
            for idx_p, (ph_id, ph_lbl) in enumerate(solar_phases):
                if idx_p > 0:
                    donki_txt.append(" ──▶ ", style="#475569")
                is_cur = ph_id == active_phase
                donki_txt.append(
                    f"[{ph_lbl}]",
                    style=("bold #06101a on #fbbf24" if is_cur else "#64748b"),
                )
        else:
            donki_txt.append("• Tormenta solar: Sin actividad externa en curso.", style="#94a3b8")
        self.query_one("#donki-box", Static).update(donki_txt)

        # Confirmación de actividad actual
        questions = state.get("questions") or []
        if questions:
            q = questions[0]
            opts = " | ".join(
                f"{opt['label']}: {humanize_level(opt['hypothetical_level'])}"
                for opt in q.get("options", [])
            )
            q_text = f"{q.get('prompt', 'Confirmar actividad')} ({opts})"
        else:
            act_now = humanize_activity(latest.get("activity"))
            q_text = f"Actividad actual: {act_now}. Pulsa abajo o [X] si cambiaste de tarea."
        self.query_one("#question-prompt", Static).update(q_text)

        # Bitácora reciente
        events = (state.get("events") or [])[-5:]
        rows = []
        for event in reversed(events):
            try:
                stamp = (
                    datetime.fromisoformat(str(event["at"]).replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                    .strftime("%H:%M:%S")
                )
            except (ValueError, KeyError):
                stamp = "—"
            rows.append(f"{stamp} UTC · {clean_astronaut_text(event.get('text', ''))}")
        self.query_one("#events-box", Static).update("\n".join(rows) or "Sin eventos todavía.")

        # Rutinas, Coach y Privacidad
        self._render_coach(coach, share_beh)
        self._render_rxn_state(coach)

    def _render_coach(self, coach: dict[str, Any], share_behavioral: bool) -> None:
        self.query_one("#coach-header", Static).update(
            render_coach_dashboard_hud(coach, BADGE_GALLERY)
        )

        routines_by_id = {item["id"]: item for item in (coach.get("routines") or [])}
        for rid, default_title in ROUTINES_META:
            item = routines_by_id.get(rid)
            if item is None:
                continue
            active = bool(item.get("active", True))
            due = bool(item.get("due"))
            self.query_one(f"#routine-info-{rid}", Static).update(
                render_routine_card_hud(item, default_title)
            )
            self.query_one(f"#routine-row-{rid}").set_class(active and due, "is-due")
            btn = self.query_one(f"#btn-routine-{rid}", Button)
            btn.disabled = not active

        self.query_one("#privacy-banner", Static).update(
            render_privacy_hud_banner(share_behavioral)
        )

    def _render_rxn_state(self, coach: dict[str, Any]) -> None:
        base_ms = coach.get("reaction_baseline_ms")
        base_val = float(base_ms) if base_ms is not None else None
        self.query_one("#rxn-status", Static).update(
            render_reaction_cockpit(
                self.rxn_phase,
                self.rxn_trial,
                self.rxn_total_trials,
                self.rxn_times,
                self.rxn_false_starts,
                self.rxn_lapses,
                base_val,
            )
        )
        self.query_one("#rxn-Visual-chart", Static).update(
            render_reaction_histogram(
                self.rxn_times,
                base_val,
                self.rxn_sleep_hours,
                self.rxn_mood,
                current_trial=self.rxn_trial,
                phase=self.rxn_phase,
            )
        )
        submit_btn = self.query_one("#btn-checkin-submit", Button)
        submit_btn.disabled = len(self.rxn_times) == 0

    def _update_self_report_label(self) -> None:
        self.query_one("#rxn-self-report", Static).update(
            f"🔋 {self.rxn_sleep_hours:.1f} h | ✨ {self.rxn_mood}/5"
        )
        for score in range(1, 6):
            btn = self.query_one(f"#btn-mood-{score}", Button)
            btn.set_class(score == self.rxn_mood, "selected")
        coach = (self.last_state or {}).get("coach") or {}
        self._render_rxn_state(coach)

    def _set_pad_visual(self, css_class: str, label: str, disabled: bool) -> None:
        pad = self.query_one("#btn-rxn-pad", Button)
        for cls in ("is-waiting", "is-go", "is-false", "is-done"):
            pad.remove_class(cls)
        if css_class:
            pad.add_class(css_class)
        pad.label = label
        pad.disabled = disabled

    def _start_rxn_test(self) -> None:
        self._cancel_rxn_timer()
        self.rxn_trial = 1
        self.rxn_times = []
        self.rxn_false_starts = 0
        self.rxn_lapses = 0
        self.rxn_go_at = 0.0
        self._schedule_rxn_wait()

    def _schedule_rxn_wait(self) -> None:
        self._cancel_rxn_timer()
        self.rxn_phase = "waiting"
        self._set_pad_visual("is-waiting", f"INTENTO {self.rxn_trial}/{self.rxn_total_trials} · ESPERA LA SEÑAL VERDE…", False)
        pad = self.query_one("#btn-rxn-pad", Button)
        pad.focus()
        delay_s = self._rng.uniform(1.0, 2.8)
        self.rxn_timer = self.set_timer(delay_s, self._on_rxn_go)
        self._render_rxn_state((self.last_state or {}).get("coach") or {})

    def _on_rxn_go(self) -> None:
        self.rxn_timer = None
        if self.rxn_phase != "waiting":
            return
        self.rxn_phase = "go"
        self.rxn_go_at = time.monotonic()
        self._set_pad_visual("is-go", "¡AHORA! PULSA ESTE BOTÓN O BARRA ESPACIADORA", False)
        self._render_rxn_state((self.last_state or {}).get("coach") or {})

    def _handle_rxn_pad_press(self) -> None:
        if self.rxn_phase == "waiting":
            self._cancel_rxn_timer()
            self.rxn_false_starts += 1
            self.rxn_phase = "false_start"
            self._set_pad_visual("is-false", "SALIDA EN FALSO — REINICIANDO INTENTO…", True)
            self.rxn_timer = self.set_timer(0.8, self._schedule_rxn_wait)
        elif self.rxn_phase == "go":
            elapsed_ms = max(1.0, round((time.monotonic() - self.rxn_go_at) * 1000.0, 1))
            self.rxn_times.append(elapsed_ms)
            if elapsed_ms > 500.0:
                self.rxn_lapses += 1
            if len(self.rxn_times) >= self.rxn_total_trials:
                self.rxn_phase = "done"
                med = statistics.median(self.rxn_times)
                self._set_pad_visual("is-done", f"PRUEBA COMPLETADA · MEDIANA {med:.1f} ms — LISTO PARA ENVIAR", True)
            else:
                self.rxn_phase = "between"
                self.rxn_trial = len(self.rxn_times) + 1
                self._set_pad_visual("is-waiting", f"REGISTRADO {elapsed_ms:.0f} ms — PREPARANDO SIGUIENTE…", True)
                self.rxn_timer = self.set_timer(0.5, self._schedule_rxn_wait)
        self._render_rxn_state((self.last_state or {}).get("coach") or {})

    async def on_key(self, event) -> None:
        if event.key == "space":
            tabs = self.query_one("#main-tabs", TabbedContent)
            if tabs.active == "tab-checkin" and self.rxn_phase in {"waiting", "go"}:
                event.stop()
                self._handle_rxn_pad_press()

    async def _submit_checkin(self, quick: bool = False) -> None:
        if self.client is None:
            return
        payload = (
            {
                "reaction_ms": [280.0, 295.0, 290.0, 300.0, 285.0, 290.0],
                "false_starts": 0,
                "lapses": 0,
                "sleep_hours": self.rxn_sleep_hours,
                "mood": self.rxn_mood,
                "source": "declared",
            }
            if quick
            else {
                "reaction_ms": list(self.rxn_times),
                "false_starts": self.rxn_false_starts,
                "lapses": self.rxn_lapses,
                "sleep_hours": self.rxn_sleep_hours,
                "mood": self.rxn_mood,
                "source": "declared",
            }
        )
        try:
            resp = await self.client.post(f"{self.onboard_url}/api/v1/checkin", json=payload)
            resp.raise_for_status()
            data = resp.json()
            self.query_one("#checkin-result", Static).update(
                render_checkin_result_card(data)
            )
            self.notify("Prueba de reflejos y bienestar guardada (+15 pts por constancia).")
            await self.refresh_data()
        except httpx.HTTPError:
            self.notify("No se pudo guardar el registro en cabina.", severity="error")

    async def refresh_trends(self) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.get(
                f"{self.onboard_url}/api/v1/trends",
                params={"window_s": self.trends_window_s},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            self.query_one("#trends-header", Static).update("No se pudieron consultar las tendencias en este momento.")
            return

        label = WINDOW_LABELS.get(self.trends_window_s, f"{self.trends_window_s} s")
        baseline = (self.last_state or {}).get("baseline") or {}
        self.query_one("#trends-header", Static).update(
            render_trends_summary_hud(label, data, baseline)
        )
        for win in (300, 900, 3600):
            self.query_one(f"#btn-win-{win}", Button).set_class(win == self.trends_window_s, "selected")

        signals = data.get("signals") or {}
        table = self.query_one("#trends-table", DataTable)
        table.clear()
        for key, title, unit, dec in SIGNAL_SPECS:
            sig = signals.get(key) or {}
            base_val = "—"
            if baseline.get("status") == "ready" and key in {"hr", "rr"}:
                base_val = _fmt_value(baseline.get(key), 1)
            table.add_row(
                title,
                unit,
                str(sig.get("count", 0)),
                _fmt_value(sig.get("min"), dec),
                _fmt_value(sig.get("max"), dec),
                _fmt_value(sig.get("mean"), dec),
                _fmt_value(sig.get("latest"), dec),
                base_val,
            )

        points = data.get("points") or []
        trend_cfg = (
            ("hr", "#38bdf8", "bpm", baseline.get("hr") if baseline.get("status") == "ready" else None, None),
            ("rr", "#34d399", "rpm", baseline.get("rr") if baseline.get("status") == "ready" else None, None),
            ("co2", "#facc15", "mmHg", None, 3.0),
            ("dose_rate", "#f472b6", "μSv/h", None, 100.0),
        )
        for key, color, unit, base_ref, thr_ref in trend_cfg:
            series = [
                float(pt[key])
                for pt in points
                if pt.get(key) is not None and not isinstance(pt.get(key), bool)
            ]
            self.query_one(f"#braille-trend-{key}", Static).update(
                braille_chart(
                    series,
                    width=42,
                    height=4,
                    color=color,
                    threshold=thr_ref,
                    baseline=base_ref,
                    unit=unit,
                )
            )
            self.query_one(f"#trend-spark-{key}", Sparkline).data = series
            self.query_one(f"#trend-meta-{key}", Label).update(
                f"{len(series)} lecturas válidas" if series else "sin lecturas válidas"
            )

    async def refresh_report(self) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.get(f"{self.onboard_url}/api/v1/report")
            resp.raise_for_status()
            data = resp.json()
            self.query_one("#report-visual-cards", Static).update(render_sbar_cards(data))
            self.query_one("#report-markdown", Static).update(render_sbar_details(data))
        except (httpx.HTTPError, ValueError):
            self.query_one("#report-visual-cards", Static).update("No se pudo cargar el resumen de episodio.")
            self.query_one("#report-markdown", Static).update("Sin conexión con el módulo a bordo para consultar el informe.")

    async def _export_report(self) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.get(f"{self.onboard_url}/api/v1/report")
            resp.raise_for_status()
            md = resp.json().get("markdown", "")
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            out_path = REPORTS_DIR / "episodio_sbar.md"
            out_path.write_text(md, encoding="utf-8")
            self.notify(f"Informe SBAR guardado correctamente ({out_path.name}).")
        except (httpx.HTTPError, OSError, ValueError):
            self.notify("Error al guardar el informe SBAR.", severity="error")

    async def load_glossary(self) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.get(f"{self.onboard_url}/api/v1/glossary")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            self.query_one("#glossary-content", Static).update("No se pudo cargar el glosario en este momento.")
            return

        self.query_one("#glossary-content", Static).update(render_glossary_rich(data))
        self.glossary_loaded = True

    async def action_acknowledge(self) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.post(f"{self.onboard_url}/api/v1/ack")
            resp.raise_for_status()
            self.notify("Alerta reconocida (+5 pts participación); la condición sigue evaluándose.")
        except httpx.HTTPError:
            self.notify("No hay alerta vigente reconocible o el nodo no responde.", severity="warning")
        await self.refresh_data()

    async def _declare_activity(self, activity: str, label: str) -> None:
        if self.client is None:
            return
        try:
            resp = await self.client.post(
                f"{self.onboard_url}/api/v1/context/activity",
                json={"activity": activity, "note": f"Declarado desde consola operacional ({label})"},
            )
            resp.raise_for_status()
            self.notify(f"Actividad declarada: {label}")
            await self.refresh_data()
        except httpx.HTTPError:
            self.notify("No se pudo registrar la actividad.", severity="error")

    async def action_cycle_activity(self) -> None:
        self.activity_idx = (self.activity_idx + 1) % len(ACTIVITIES_CYCLE)
        act_id, label = ACTIVITIES_CYCLE[self.activity_idx]
        await self._declare_activity(act_id, label)

    async def action_toggle_privacy(self) -> None:
        if self.client is None:
            return
        current = bool(((self.last_state or {}).get("privacy") or {}).get("share_behavioral", False))
        try:
            resp = await self.client.post(
                f"{self.onboard_url}/api/v1/privacy",
                json={"share_behavioral": not current},
            )
            resp.raise_for_status()
            self.notify(
                "Privacidad: compartir resumen en SBAR activado."
                if not current
                else "Privacidad: datos conductuales retenidos SOLO A BORDO."
            )
            await self.refresh_data()
            await self.refresh_report()
        except httpx.HTTPError:
            self.notify("No se pudo cambiar la privacidad SBAR.", severity="error")

    async def _complete_routine(self, routine_id: str) -> None:
        if self.client is None:
            return
        r_label = dict(ROUTINES_META).get(routine_id, routine_id.replace("_", " "))
        try:
            resp = await self.client.post(f"{self.onboard_url}/api/v1/routines/{routine_id}/done")
            resp.raise_for_status()
            self.notify(f"Rutina «{r_label}» completada (+10 pts participación).")
            await self.refresh_data()
        except httpx.HTTPError:
            self.notify(f"No se pudo completar la rutina «{r_label}».", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn-ack-alert":
            await self.action_acknowledge()
        elif bid == "btn-act-rest":
            await self._declare_activity("rest", "Reposo")
        elif bid == "btn-act-exercise":
            await self._declare_activity("exercise", "Ejercicio")
        elif bid == "btn-act-recovery":
            await self._declare_activity("recovery", "Recuperación")
        elif bid in {"btn-win-300", "btn-win-900", "btn-win-3600"}:
            self.trends_window_s = int(bid.removeprefix("btn-win-"))
            await self.refresh_trends()
        elif bid == "btn-trends-refresh":
            await self.refresh_trends()
        elif bid == "btn-rxn-start":
            self._start_rxn_test()
        elif bid == "btn-rxn-pad":
            self._handle_rxn_pad_press()
        elif bid == "btn-sleep-dec":
            self.rxn_sleep_hours = max(0.0, round(self.rxn_sleep_hours - 0.5, 1))
            self._update_self_report_label()
        elif bid == "btn-sleep-inc":
            self.rxn_sleep_hours = min(24.0, round(self.rxn_sleep_hours + 0.5, 1))
            self._update_self_report_label()
        elif bid.startswith("btn-mood-"):
            self.rxn_mood = int(bid.removeprefix("btn-mood-"))
            self._update_self_report_label()
        elif bid == "btn-checkin-submit":
            await self._submit_checkin(quick=False)
        elif bid == "btn-checkin-quick":
            await self._submit_checkin(quick=True)
        elif bid.startswith("btn-routine-"):
            await self._complete_routine(bid.removeprefix("btn-routine-"))
        elif bid == "btn-privacy-toggle":
            await self.action_toggle_privacy()
        elif bid == "btn-report-refresh":
            await self.refresh_report()
        elif bid == "btn-report-export":
            await self._export_report()
        elif bid == "btn-glossary-refresh":
            await self.load_glossary()


if __name__ == "__main__":
    AstroVitalsApp().run()
