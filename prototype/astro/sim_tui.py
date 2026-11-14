"""TUI independiente del Simulador de Escenarios y Sensores de Traje."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Static

from astro.tui_graphics import (
    WIDGET_HOVER_HELP,
    build_signal_tooltip,
    channel_severity,
    clean_astronaut_text,
    format_hover_inspector,
    format_tooltip_inspector,
    gauge_bar,
    humanize_activity,
    humanize_level,
    humanize_source,
    severity_color,
)


SCENARIO_BUTTONS: list[tuple[str, str, str]] = [
    ("rest", "1 · Descanso en cabina", "1"),
    ("exercise", "2 · Caminata / Ejercicio", "2"),
    ("cabin", "3 · Aire con CO₂ alto", "3"),
    ("co2_ramp", "4 · Subida de CO₂", "4"),
    ("solar_event", "5 · Tormenta solar", "5"),
    ("signal_loss", "6 · Sensor desconectado", "6"),
    ("bidmc", "7 · Registro biomédico", "7"),
]

ENVIRONMENTS: list[tuple[str, str]] = [
    ("station", "Estación orbital"),
    ("transit", "Nave en tránsito"),
    ("rover", "Vehículo rover"),
    ("base", "Base lunar"),
]

SOLAR_PHASES: list[tuple[str, str]] = [
    ("watch", "Vigilancia"),
    ("arrival", "Llegada"),
    ("peak", "Pico máximo"),
    ("decay", "Descenso"),
]

ACTIVITIES: tuple[str, ...] = ("rest", "exercise", "recovery", "unknown")

SUIT_CHANNELS: list[dict[str, Any]] = [
    {
        "key": "hr",
        "label": "FC (BPM)",
        "default": 74.0,
        "step": 4.0,
        "min": 30.0,
        "max": 210.0,
        "fmt": "{:.0f}",
        "null_group": "hr",
        "null_btn_id": "toggle-null-hr",
    },
    {
        "key": "rr",
        "label": "FR (rpm)",
        "default": 15.0,
        "step": 1.0,
        "min": 4.0,
        "max": 45.0,
        "fmt": "{:.0f}",
        "null_group": "rr",
        "null_btn_id": "toggle-null-rr",
    },
    {
        "key": "co2",
        "label": "ppCO₂ (mmHg)",
        "default": 2.4,
        "step": 0.5,
        "min": 0.2,
        "max": 25.0,
        "fmt": "{:.1f}",
        "null_group": "co2",
        "null_btn_id": "toggle-null-co2",
    },
    {
        "key": "dose_rate",
        "label": "Dosis (µSv/h)",
        "default": 18.0,
        "step": 25.0,
        "min": 0.0,
        "max": 2500.0,
        "fmt": "{:.1f}",
        "null_group": "dose_rate",
        "null_btn_id": "toggle-null-dose",
    },
    {
        "key": "spo2",
        "label": "SpO₂ (%)",
        "default": 98.0,
        "step": 1.0,
        "min": 70.0,
        "max": 100.0,
        "fmt": "{:.1f}",
        "null_group": "spo2",
        "null_btn_id": "toggle-null-spo2",
    },
    {
        "key": "bp_sys",
        "label": "PA Sist. (mmHg)",
        "default": 116.0,
        "step": 5.0,
        "min": 65.0,
        "max": 210.0,
        "fmt": "{:.0f}",
        "null_group": "bp",
        "null_btn_id": "toggle-null-bp",
    },
    {
        "key": "bp_dia",
        "label": "PA Diast. (mmHg)",
        "default": 74.0,
        "step": 4.0,
        "min": 40.0,
        "max": 130.0,
        "fmt": "{:.0f}",
        "null_group": "bp",
        "null_btn_id": None,
    },
    {
        "key": "temp_c",
        "label": "Temp. (°C)",
        "default": 36.7,
        "step": 0.2,
        "min": 33.5,
        "max": 41.0,
        "fmt": "{:.1f}",
        "null_group": "temp_c",
        "null_btn_id": "toggle-null-temp",
    },
    {
        "key": "hydration_pct",
        "label": "Hidratación (%)",
        "default": 84.0,
        "step": 3.0,
        "min": 30.0,
        "max": 100.0,
        "fmt": "{:.0f}",
        "null_group": "hydration_pct",
        "null_btn_id": "toggle-null-hyd",
    },
]

CHANNEL_BY_KEY: dict[str, dict[str, Any]] = {ch["key"]: ch for ch in SUIT_CHANNELS}


def _fmt_or_no_signal(value: Any, decimals: int = 1, unit: str = "") -> str:
    if value is None:
        return "SIN SEÑAL (—)"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "SIN SEÑAL (—)"
    suffix = f" {unit}".rstrip()
    if decimals == 0:
        return f"{num:.0f}{(' ' + suffix) if suffix else ''}"
    return f"{num:.{decimals}f}{(' ' + suffix) if suffix else ''}"


class SimulatorTUIApp(App[None]):
    """Ventana independiente del simulador de escenarios y sensores de traje."""

    TITLE = "ASTRO-VITALS · Simulador de Escenarios y Sensores"
    SUB_TITLE = "Ventana separada de inyección · No clínica"

    BINDINGS = [
        Binding("1", "set_scenario('rest')", "Reposo"),
        Binding("2", "set_scenario('exercise')", "Ejercicio"),
        Binding("3", "set_scenario('cabin')", "Cabina CO₂"),
        Binding("4", "set_scenario('co2_ramp')", "Rampa CO₂"),
        Binding("5", "set_scenario('solar_event')", "Solar"),
        Binding("6", "set_scenario('signal_loss')", "Pérdida señal"),
        Binding("7", "set_scenario('bidmc')", "BIDMC"),
        Binding("e", "cycle_environment", "Entorno"),
        Binding("f", "cycle_solar_phase", "Fase DONKI"),
        Binding("s", "toggle_shelter", "Refugio"),
        Binding("p", "toggle_pause", "Pausa"),
        Binding("n", "send_manual_packet", "Enviar paquete"),
        Binding("b", "toggle_stream_manual", "Stream 1 Hz"),
        Binding("q", "quit", "Salir"),
    ]

    CSS = """
    Screen {
        background: #09101a;
        color: #e2e8f0;
    }

    #sim-banner {
        background: #132238;
        color: #f8fafc;
        border: solid #38bdf8;
        padding: 0 2;
        margin: 0 1;
        height: 3;
    }

    #sim-columns {
        height: 1fr;
        margin: 0 1;
    }

    .sim-panel {
        border: round #1e4b6e;
        background: #081220;
        padding: 1;
        margin: 0 1 0 0;
        height: 1fr;
    }

    #sim-left-col {
        width: 42%;
    }

    #sim-right-col {
        width: 58%;
        margin-right: 0;
    }

    .section-title {
        color: #38bdf8;
        text-style: bold;
        margin-bottom: 1;
    }

    #scenario-grid {
        grid-size: 2;
        grid-gutter: 1;
        height: auto;
        margin-bottom: 1;
    }

    #env-grid, #phase-grid {
        grid-size: 2;
        grid-gutter: 1;
        height: auto;
        margin-bottom: 1;
    }

    .sim-btn {
        width: 100%;
        min-height: 3;
    }

    .sim-btn.active {
        background: #0284c7;
        color: #ffffff;
        text-style: bold;
    }

    .control-row {
        height: auto;
        margin-bottom: 1;
    }

    .control-row Button {
        width: 1fr;
        margin-right: 1;
    }

    #sim-suit-builder {
        height: auto;
        border: solid #243b55;
        background: #0b1420;
        padding: 1;
        margin-bottom: 1;
    }

    .channel-row {
        height: 3;
        align: left middle;
    }

    .ch-label {
        width: 14;
        color: #cbd5e1;
    }

    .ch-val {
        width: 14;
        color: #f8fafc;
        text-style: bold;
    }

    .ch-val.missing {
        color: #fbbf24;
    }

    .ch-bar {
        width: 17;
        margin-right: 1;
    }

    .mini-btn {
        min-width: 4;
        width: 4;
        margin-right: 1;
    }

    .null-btn {
        min-width: 19;
        width: 21;
    }

    .null-btn.is-null {
        background: #92400e;
        color: #fef3c7;
        text-style: bold;
    }

    #manual-action-row {
        height: auto;
        margin: 1 0;
    }

    #manual-action-row Button {
        width: 1fr;
        margin-right: 1;
    }

    #manual-packet-preview {
        border: solid #1e293b;
        background: #070d16;
        color: #93c5fd;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }

    #sim-onboard-mirror {
        border: solid #1e3a5f;
        background: #08111d;
        color: #e2e8f0;
        padding: 1;
        height: auto;
    }

    Tooltip {
        background: #0d2137;
        color: #f1f5f9;
        border: round #38bdf8;
        padding: 1 2;
        max-width: 74;
    }

    #sim-hover-inspector {
        height: 2;
        padding: 0 2;
        margin: 0 1;
        background: #0a192f;
        color: #cbd5e1;
        border-top: solid #1e4b6e;
    }

    #sim-status-bar {
        background: #101d2f;
        color: #cbd5e1;
        padding: 0 2;
        margin: 0 1;
        height: 2;
        border-top: solid #1e3a5f;
    }
    """

    def __init__(
        self,
        onboard_url: str | None = None,
        gateway_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        resolved_onboard = onboard_url or os.environ.get("ONBOARD_URL", "http://127.0.0.1:8000")
        resolved_gateway = gateway_url or os.environ.get("GATEWAY_URL", "http://127.0.0.1:8002")
        self.onboard_url = resolved_onboard.rstrip("/")
        self.gateway_url = resolved_gateway.rstrip("/")

        self.control_state: dict[str, Any] = {
            "scenario": "rest",
            "environment": "station",
            "solar_phase": "watch",
            "shelter": False,
            "paused": False,
        }
        self.suit_values: dict[str, float | None] = {
            ch["key"]: float(ch["default"]) for ch in SUIT_CHANNELS
        }
        self._last_non_null: dict[str, float] = {
            ch["key"]: float(ch["default"]) for ch in SUIT_CHANNELS
        }
        self.suit_activity_idx: int = 0
        self.stream_manual: bool = False
        self.sent_packets_count: int = 0
        self.last_status_note: str = "Esperando conexión con API y pasarela..."
        self.latest_mirror: dict[str, Any] | None = None
        self._last_hover_signature: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            "SIMULADOR EXTERNO DE MISIÓN Y TRAJE · Herramienta de pruebas orientativa · "
            "Puedes desconectar cualquier sensor del traje para simular pérdida de señal en misión.",
            id="sim-banner",
        )
        with Horizontal(id="sim-columns"):
            with VerticalScroll(id="sim-left-col", classes="sim-panel"):
                yield Static("PASARELA DE ESCENARIOS (1-7)", classes="section-title")
                with Grid(id="scenario-grid"):
                    for sc_id, label, _key in SCENARIO_BUTTONS:
                        yield Button(label, id=f"scn-{sc_id}", classes="sim-btn")

                yield Static("ENTORNO OPERATIVO (e)", classes="section-title")
                with Grid(id="env-grid"):
                    for env_id, label in ENVIRONMENTS:
                        yield Button(label, id=f"env-{env_id}", classes="sim-btn")

                yield Static("FASE SOLAR DONKI (f)", classes="section-title")
                with Grid(id="phase-grid"):
                    for phase_id, label in SOLAR_PHASES:
                        yield Button(label, id=f"phase-{phase_id}", classes="sim-btn")

                yield Static("CONTROLES DE FLUJO", classes="section-title")
                with Horizontal(classes="control-row"):
                    yield Button("Pausa pasarela (p): OFF", id="btn-sim-pause", classes="sim-btn")
                    yield Button("Refugio radiación (s): OFF", id="btn-sim-shelter", classes="sim-btn")

                yield Static("LO QUE VE EL ASTRONAUTA EN CABINA", classes="section-title")
                yield Static("Esperando primera lectura de la cabina.", id="sim-onboard-mirror")

            with VerticalScroll(id="sim-right-col", classes="sim-panel"):
                yield Static("SENSORES DEL TRAJE ESPACIAL (AJUSTE MANUAL)", classes="section-title")
                with Vertical(id="sim-suit-builder"):
                    for ch in SUIT_CHANNELS:
                        key = ch["key"]
                        with Horizontal(classes="channel-row"):
                            yield Static(ch["label"], classes="ch-label")
                            yield Static(
                                self._format_channel_value(key),
                                id=f"val-{key}",
                                classes="ch-val",
                            )
                            yield Static(
                                gauge_bar(self.suit_values[key], key, width=12),
                                id=f"bar-{key}",
                                classes="ch-bar",
                            )
                            yield Button("-", id=f"dec-{key}", classes="mini-btn")
                            yield Button("+", id=f"inc-{key}", classes="mini-btn")
                            if ch["null_btn_id"]:
                                yield Button(
                                    "Desconectar sensor",
                                    id=ch["null_btn_id"],
                                    classes="null-btn",
                                )
                            else:
                                yield Static("(PA conjunta)", classes="ch-label")

                    with Horizontal(classes="channel-row"):
                        yield Static("Actividad:", classes="ch-label")
                        yield Button(
                            f"Actividad: {humanize_activity(ACTIVITIES[self.suit_activity_idx])}",
                            id="btn-cycle-activity",
                            classes="sim-btn",
                        )

                with Horizontal(id="manual-action-row"):
                    yield Button("Enviar lectura del traje (n)", id="btn-send-manual", classes="sim-btn")
                    yield Button("Envío continuo 1/seg (b): OFF", id="btn-stream-manual", classes="sim-btn")

                yield Static("LECTURAS ACTUALES ENVIADAS POR EL TRAJE", classes="section-title")
                yield Static("", id="manual-packet-preview")

        yield Static(
            format_hover_inspector(
                "Simulador de Escenarios y Traje",
                "Pasa el mouse sobre escenarios, fases solares o canales del traje para ver su explicación.",
            ),
            id="sim-hover-inspector",
        )
        yield Static(self.last_status_note, id="sim-status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._bind_static_tooltips()
        self._refresh_ui_state()
        self.set_interval(1.0, self._poll_tick)
        self.call_later(self._fetch_remote_state)

    def _bind_static_tooltips(self) -> None:
        for widget_id, (title, detail) in WIDGET_HOVER_HELP.items():
            for widget in self.query(f"#{widget_id}"):
                widget.tooltip = f"{title}\n{detail}"

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self.is_mounted:
            return
        cur = event.widget
        while cur is not None:
            wid = getattr(cur, "id", None)
            if wid and wid in WIDGET_HOVER_HELP:
                title, detail = WIDGET_HOVER_HELP[wid]
                sig = f"id:{wid}"
                if sig != self._last_hover_signature:
                    self._last_hover_signature = sig
                    self.query_one("#sim-hover-inspector", Static).update(
                        format_hover_inspector(title, detail)
                    )
                return
            tip = getattr(cur, "tooltip", None)
            if tip:
                sig = f"tip:{wid}:{tip}"
                if sig != self._last_hover_signature:
                    self._last_hover_signature = sig
                    self.query_one("#sim-hover-inspector", Static).update(
                        format_tooltip_inspector(str(tip))
                    )
                return
            cur = cur.parent

    def _poll_tick(self) -> None:
        if self.stream_manual:
            self._send_manual_telemetry(auto_pause=True)
        self._fetch_remote_state()

    def _format_channel_value(self, key: str) -> str:
        val = self.suit_values.get(key)
        if val is None:
            return "SIN SEÑAL (—)"
        fmt = CHANNEL_BY_KEY[key]["fmt"]
        return fmt.format(val)

    def _build_manual_payload(self) -> dict[str, Any]:
        return {
            "sample_id": f"sim-suit-{uuid.uuid4().hex[:10]}",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "hr": self.suit_values["hr"],
            "rr": self.suit_values["rr"],
            "co2": self.suit_values["co2"],
            "dose_rate": self.suit_values["dose_rate"],
            "spo2": self.suit_values["spo2"],
            "bp_sys": self.suit_values["bp_sys"],
            "bp_dia": self.suit_values["bp_dia"],
            "temp_c": self.suit_values["temp_c"],
            "hydration_pct": self.suit_values["hydration_pct"],
            "activity": ACTIVITIES[self.suit_activity_idx],
            "source": "simulated",
            "original_time_s": None,
        }

    def _is_group_null(self, null_group: str) -> bool:
        if null_group == "bp":
            return self.suit_values["bp_sys"] is None and self.suit_values["bp_dia"] is None
        return self.suit_values.get(null_group) is None

    def _refresh_ui_state(self) -> None:
        if not self.is_mounted:
            return

        current_scn = self.control_state.get("scenario", "rest")
        for sc_id, _label, _key in SCENARIO_BUTTONS:
            btn = self.query_one(f"#scn-{sc_id}", Button)
            btn.set_class(sc_id == current_scn, "active")

        current_env = self.control_state.get("environment", "station")
        for env_id, _label in ENVIRONMENTS:
            btn = self.query_one(f"#env-{env_id}", Button)
            btn.set_class(env_id == current_env, "active")

        current_phase = self.control_state.get("solar_phase", "watch")
        for phase_id, _label in SOLAR_PHASES:
            btn = self.query_one(f"#phase-{phase_id}", Button)
            btn.set_class(phase_id == current_phase, "active")

        paused = bool(self.control_state.get("paused", False))
        btn_pause = self.query_one("#btn-sim-pause", Button)
        btn_pause.label = f"Pausa pasarela (p): {'ON' if paused else 'OFF'}"
        btn_pause.set_class(paused, "active")

        shelter = bool(self.control_state.get("shelter", False))
        btn_shelter = self.query_one("#btn-sim-shelter", Button)
        btn_shelter.label = f"Refugio radiación (s): {'ON' if shelter else 'OFF'}"
        btn_shelter.set_class(shelter, "active")

        btn_stream = self.query_one("#btn-stream-manual", Button)
        btn_stream.label = f"Envío continuo 1/seg (b): {'ON' if self.stream_manual else 'OFF'}"
        btn_stream.set_class(self.stream_manual, "active")

        btn_act = self.query_one("#btn-cycle-activity", Button)
        btn_act.label = f"Actividad: {humanize_activity(ACTIVITIES[self.suit_activity_idx])}"

        for ch in SUIT_CHANNELS:
            key = ch["key"]
            cur_val = self.suit_values[key]
            ch_tip = build_signal_tooltip(
                key,
                cur_val,
                self.suit_values.get("bp_dia") if key == "bp_sys" else None,
            )
            val_widget = self.query_one(f"#val-{key}", Static)
            val_widget.update(self._format_channel_value(key))
            val_widget.set_class(cur_val is None, "missing")
            val_widget.tooltip = ch_tip

            bar_widget = self.query_one(f"#bar-{key}", Static)
            bar_widget.update(gauge_bar(cur_val, key, width=12))
            bar_widget.tooltip = ch_tip

            self.query_one(f"#inc-{key}", Button).tooltip = ch_tip
            self.query_one(f"#dec-{key}", Button).tooltip = ch_tip

            if ch["null_btn_id"]:
                null_btn = self.query_one(f"#{ch['null_btn_id']}", Button)
                is_null = self._is_group_null(ch["null_group"])
                null_btn.set_class(is_null, "is-null")
                null_btn.label = "Reconectar sensor" if is_null else "Desconectar sensor"
                null_btn.tooltip = ch_tip

        self.query_one("#manual-packet-preview", Static).update(
            self._render_manual_preview()
        )
        self._render_mirror()
        self.query_one("#sim-status-bar", Static).update(
            f"{self.last_status_note} | Paquetes manuales enviados: {self.sent_packets_count}"
        )

    def _render_manual_preview(self) -> Text:
        """Resumen legible de los sensores actuales del traje para la tripulación."""
        out = Text()
        for ch in SUIT_CHANNELS:
            key = ch["key"]
            raw_v = self.suit_values.get(key)
            val_txt = self._format_channel_value(key)
            clr = severity_color(channel_severity(raw_v, key))
            out.append(f"  {ch['label']:<15} ", style="#94a3b8")
            out.append(f"{val_txt}\n", style=f"bold {clr}")
        out.append(f"  {'Actividad':<15} ", style="#94a3b8")
        out.append(humanize_activity(ACTIVITIES[self.suit_activity_idx]), style="bold #bae6fd")
        return out

    def _render_mirror(self) -> None:
        mirror = self.query_one("#sim-onboard-mirror", Static)
        state = self.latest_mirror
        if not state:
            mirror.update(
                "Esperando primera lectura de la consola a bordo…\n"
                f"Cabina: {self.onboard_url} · Pasarela: {self.gateway_url}"
            )
            return

        telemetry = state.get("latest") or {}
        assessment = state.get("assessment") or {}
        level = str(assessment.get("level") or "unknown").lower()
        lvl_colors = {"normal": "#4ade80", "watch": "#fbbf24", "alert": "#fb7185", "unknown": "#94a3b8"}
        lvl_clr = lvl_colors.get(level, "#94a3b8")
        env = (state.get("environment") or {}).get("name") or (state.get("environment") or {}).get("id") or "—"
        source = humanize_source(telemetry.get("source"))
        hyp = clean_astronaut_text(assessment.get("hypothesis") or "Esperando datos del traje.")

        out = Text()
        out.append(f" ● {humanize_level(level)} ", style=f"bold #06101a on {lvl_clr}")
        out.append(f" Módulo: {env} │ {source}\n", style="#bae6fd")

        mirror_channels = (
            ("hr", "FC   ", 0, "BPM"),
            ("rr", "FR   ", 0, "rpm"),
            ("co2", "ppCO₂", 2, "mmHg"),
            ("dose_rate", "Dosis", 1, "µSv/h"),
            ("spo2", "SpO₂ ", 1, "%"),
            ("temp_c", "Temp ", 1, "°C"),
            ("hydration_pct", "Hidr.", 0, "%"),
        )
        for ch_key, ch_lbl, dec, unit in mirror_channels:
            raw_v = telemetry.get(ch_key)
            val_s = _fmt_or_no_signal(raw_v, dec, unit)
            val_clr = severity_color(channel_severity(raw_v, ch_key))
            out.append(f"  {ch_lbl} ", style="#94a3b8")
            out.append(gauge_bar(raw_v, ch_key, width=10))
            out.append(f" {val_s}\n", style=f"bold {val_clr}")

        out.append(f"Estado: {hyp}", style=lvl_clr)
        mirror.update(out)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("scn-"):
            self.action_set_scenario(btn_id[4:])
            return
        if btn_id.startswith("env-"):
            self._apply_control({"environment": btn_id[4:]})
            return
        if btn_id.startswith("phase-"):
            self._apply_control({"solar_phase": btn_id[6:]})
            return
        if btn_id == "btn-sim-pause":
            self.action_toggle_pause()
            return
        if btn_id == "btn-sim-shelter":
            self.action_toggle_shelter()
            return
        if btn_id.startswith("inc-"):
            self._step_channel(btn_id[4:], +1)
            return
        if btn_id.startswith("dec-"):
            self._step_channel(btn_id[4:], -1)
            return
        if btn_id.startswith("toggle-null-"):
            self._toggle_null_by_button(btn_id)
            return
        if btn_id == "btn-cycle-activity":
            self.suit_activity_idx = (self.suit_activity_idx + 1) % len(ACTIVITIES)
            self._refresh_ui_state()
            return
        if btn_id == "btn-send-manual":
            self.action_send_manual_packet()
            return
        if btn_id == "btn-stream-manual":
            self.action_toggle_stream_manual()

    def _step_channel(self, key: str, direction: int) -> None:
        ch = CHANNEL_BY_KEY.get(key)
        if not ch:
            return
        current = self.suit_values[key]
        if current is None:
            current = self._last_non_null[key]
        nxt = max(float(ch["min"]), min(float(ch["max"]), current + direction * float(ch["step"])))
        nxt = round(nxt, 2)
        self.suit_values[key] = nxt
        self._last_non_null[key] = nxt
        self._refresh_ui_state()

    def _toggle_null_by_button(self, btn_id: str) -> None:
        target_group: str | None = None
        for ch in SUIT_CHANNELS:
            if ch["null_btn_id"] == btn_id:
                target_group = ch["null_group"]
                break
        if target_group is None:
            return

        if target_group == "bp":
            if self._is_group_null("bp"):
                self.suit_values["bp_sys"] = self._last_non_null["bp_sys"]
                self.suit_values["bp_dia"] = self._last_non_null["bp_dia"]
            else:
                if self.suit_values["bp_sys"] is not None:
                    self._last_non_null["bp_sys"] = float(self.suit_values["bp_sys"])
                if self.suit_values["bp_dia"] is not None:
                    self._last_non_null["bp_dia"] = float(self.suit_values["bp_dia"])
                self.suit_values["bp_sys"] = None
                self.suit_values["bp_dia"] = None
        else:
            if self.suit_values[target_group] is None:
                self.suit_values[target_group] = self._last_non_null[target_group]
            else:
                self._last_non_null[target_group] = float(self.suit_values[target_group])
                self.suit_values[target_group] = None

        self._refresh_ui_state()

    def action_set_scenario(self, scenario: str) -> None:
        self.stream_manual = False
        self._apply_control({"scenario": scenario, "paused": False})

    def action_cycle_environment(self) -> None:
        ids = [item[0] for item in ENVIRONMENTS]
        cur = self.control_state.get("environment", "station")
        nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
        self._apply_control({"environment": nxt})

    def action_cycle_solar_phase(self) -> None:
        ids = [item[0] for item in SOLAR_PHASES]
        cur = self.control_state.get("solar_phase", "watch")
        nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
        self._apply_control({"solar_phase": nxt})

    def action_toggle_shelter(self) -> None:
        self._apply_control({"shelter": not bool(self.control_state.get("shelter", False))})

    def action_toggle_pause(self) -> None:
        self._apply_control({"paused": not bool(self.control_state.get("paused", False))})

    def action_send_manual_packet(self) -> None:
        self._send_manual_telemetry(auto_pause=True)

    def action_toggle_stream_manual(self) -> None:
        self.stream_manual = not self.stream_manual
        if self.stream_manual:
            self.last_status_note = "Stream manual 1 Hz activado (pausando pasarela)."
            self._send_manual_telemetry(auto_pause=True)
        else:
            self.last_status_note = "Stream manual 1 Hz detenido."
        self._refresh_ui_state()

    @work(exclusive=True, group="poll")
    async def _fetch_remote_state(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                ctrl_ok = False
                try:
                    resp = await client.get(f"{self.onboard_url}/api/control")
                    if resp.status_code == 200:
                        self.control_state.update(resp.json())
                        ctrl_ok = True
                except Exception:
                    pass

                if not ctrl_ok:
                    try:
                        gw = await client.get(f"{self.gateway_url}/control")
                        if gw.status_code == 200:
                            self.control_state.update(gw.json())
                    except Exception:
                        pass

                st = await client.get(f"{self.onboard_url}/api/v1/state")
                if st.status_code == 200:
                    self.latest_mirror = st.json()
                    self.last_status_note = f"Conectado · API {self.onboard_url} · Pasarela {self.gateway_url}"
                else:
                    self.last_status_note = f"API respondió HTTP {st.status_code}"
        except Exception as exc:
            self.last_status_note = f"Sin conexión con servicios ({type(exc).__name__})"

        self._refresh_ui_state()

    @work(exclusive=True, group="control")
    async def _apply_control(self, patch: dict[str, Any]) -> None:
        self.control_state.update(patch)
        self._refresh_ui_state()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(f"{self.onboard_url}/api/control", json=patch)
                if resp.status_code == 200:
                    self.control_state.update(resp.json())
                    self.last_status_note = f"Control aplicado en /api/control: {patch}"
                else:
                    gw = await client.post(f"{self.gateway_url}/control", json=patch)
                    if gw.status_code == 200:
                        self.control_state.update(gw.json())
                        if "environment" in patch:
                            await client.post(
                                f"{self.onboard_url}/api/v1/context/environment",
                                json={"environment": patch["environment"]},
                            )
                        self.last_status_note = f"Control aplicado por respaldo /control: {patch}"
                    else:
                        self.last_status_note = f"Error control HTTP {resp.status_code}/{gw.status_code}"
        except Exception as exc:
            self.last_status_note = f"Control no enviado ({type(exc).__name__})"
        self._refresh_ui_state()

    @work(exclusive=False, group="telemetry")
    async def _send_manual_telemetry(self, auto_pause: bool = True) -> None:
        payload = self._build_manual_payload()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                if auto_pause and not self.control_state.get("paused", False):
                    try:
                        pause_resp = await client.post(
                            f"{self.onboard_url}/api/control", json={"paused": True}
                        )
                        if pause_resp.status_code == 200:
                            self.control_state.update(pause_resp.json())
                    except Exception:
                        pass
                resp = await client.post(f"{self.onboard_url}/api/v1/telemetry", json=payload)
                if resp.status_code in (200, 201):
                    self.sent_packets_count += 1
                    self.last_status_note = f"Paquete de traje enviado ({payload['sample_id']})"
                else:
                    self.last_status_note = f"Error al inyectar telemetría HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as exc:
            self.last_status_note = f"Fallo enviando paquete ({type(exc).__name__})"
        self._refresh_ui_state()
