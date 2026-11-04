"""Astronaut console: all readings arrive through the onboard HTTP API."""

import os
from datetime import datetime, timezone

import httpx
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Label, Sparkline, Static

SCENARIOS = {
    "rest": "Reposo", "exercise": "Actividad", "cabin": "Cabina / CO₂",
    "solar": "Radiación", "signal_loss": "Señal ausente", "bidmc": "BIDMC real",
}
LEVELS = {
    "normal": ("ESTABLE", "#66e0bd"),
    "watch": ("REVISAR", "#ffca73"),
    "alert": ("ATENCIÓN", "#ff8d84"),
    "unknown": ("SIN EVALUACIÓN", "#a4b2ca"),
}


class Metric(Vertical):
    def __init__(self, key: str, title: str, unit: str):
        super().__init__(id=f"card-{key}", classes="metric")
        self.key, self.caption, self.unit = key, title, unit

    def compose(self) -> ComposeResult:
        yield Label(self.caption, classes="metric-label")
        yield Static("—", id=f"value-{self.key}", classes="metric-value")
        yield Sparkline([], id=f"spark-{self.key}", summary_function=max)
        yield Label(self.unit, id=f"unit-{self.key}", classes="metric-unit")

    def show_value(self, value, history):
        numeric = f"{value:.1f}" if value is not None else "—"
        self.query_one(f"#value-{self.key}", Static).update(numeric)
        # Do not connect gaps in a physiological series or replace them with zero.
        contiguous = []
        newer_at = None
        for sample in reversed(history[-60:]):
            current = sample.get(self.key)
            if current is None:
                break
            measured_at = datetime.fromisoformat(sample["measured_at"].replace("Z", "+00:00"))
            if newer_at is not None and (newer_at - measured_at).total_seconds() > 5:
                break
            contiguous.append(current)
            newer_at = measured_at
        self.query_one(Sparkline).data = list(reversed(contiguous))
        suffix = " · sin dato" if value is None else " · escala automática"
        self.query_one(f"#unit-{self.key}", Label).update(self.unit + suffix)


class AstroVitalsApp(App):
    TITLE = "ASTRO-VITALS · Consola de misión"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #0a111c; color: #dde6f4; }
    #brand { height: 3; padding: 1 2 0 2; background: #101c2d; }
    #strap { height: 2; padding: 0 2; background: #101c2d; color: #93a7c5; }
    #body { padding: 1 2; }
    #status { height: auto; min-height: 2; padding: 0 1; }
    #metrics { height: 9; }
    .metric { width: 1fr; height: 8; border: round #29445e; margin-right: 1; padding: 0 1; }
    .metric-label { color: #9bb0ca; height: 1; }
    .metric-value { text-style: bold; color: #72e1ca; height: 2; padding-top: 1; }
    Sparkline { height: 2; color: #72e1ca; background: #112236; margin-top: 0; }
    .metric-unit { color: #8ea4c1; height: 1; }
    #detail { height: auto; min-height: 15; }
    #analysis { width: 3fr; height: auto; min-height: 15; border: round #29445e; padding: 0 2; margin-right: 1; }
    #mission { width: 2fr; height: auto; min-height: 15; border: round #29445e; padding: 0 1; }
    .section { color: #93a7c5; height: 2; padding-top: 1; text-style: bold; }
    #hypothesis { height: auto; min-height: 2; text-style: bold; }
    #evidence, #next-step, #forecast, #exposure, #events { height: auto; margin-bottom: 1; }
    #method { height: auto; color: #8ea4c1; }
    #controls { height: auto; border: round #29445e; padding: 0 1; margin-top: 1; }
    .buttons { height: 3; }
    Button { min-width: 9; width: 1fr; margin-right: 1; height: 3; background: #14263a; border: tall transparent; color: #c4d6ed; }
    Button:hover { background: #213b55; }
    Button.selected { background: #1c4d4b; color: #99f5dc; }
    #gateway-status { height: auto; min-height: 2; color: #91a8c6; padding-top: 1; }
    #notice { height: auto; color: #93a7c5; margin-top: 1; }
    Footer { background: #101c2d; }
    """
    BINDINGS = [
        Binding("1", "scenario('rest')", "Reposo", show=False),
        Binding("2", "scenario('exercise')", "Actividad", show=False),
        Binding("3", "scenario('cabin')", "Cabina", show=False),
        Binding("4", "scenario('solar')", "Radiación", show=False),
        Binding("5", "scenario('signal_loss')", "Sin señal", show=False),
        Binding("6", "scenario('bidmc')", "BIDMC", show=False),
        Binding("p", "pause", "Pausar fuente"),
        Binding("s", "shelter", "Refugio simulado"),
        Binding("a", "acknowledge", "Reconocer"),
        Binding("q", "quit", "Salir"),
    ]

    def __init__(self, onboard_url=None, gateway_url=None):
        super().__init__()
        self.onboard_url = (onboard_url or os.getenv("ONBOARD_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.gateway_url = (gateway_url or os.getenv("GATEWAY_URL", "http://127.0.0.1:8002")).rstrip("/")
        self.client = None
        self.last_state = None
        self.gateway_state = {}
        self.refreshing = False

    def compose(self) -> ComposeResult:
        yield Static(Text.assemble(("◈  ASTRO", "bold #72e1ca"), ("-VITALS", "bold white"), "   /   CONSOLA A BORDO"), id="brand")
        yield Static("PROTOTIPO 0.1    ·    HÁBITAT 01    ·    DEMO INTERACTIVA", id="strap")
        with VerticalScroll(id="body"):
            yield Static("Conectando al nodo a bordo…", id="status")
            with Horizontal(id="metrics"):
                yield Metric("hr", "FRECUENCIA CARDÍACA", "bpm")
                yield Metric("rr", "RESPIRACIÓN", "resp/min")
                yield Metric("co2", "CO₂ DE CABINA", "mmHg")
                yield Metric("dose_rate", "TASA DE DOSIS", "μSv/h")
            with Horizontal(id="detail"):
                with Vertical(id="analysis"):
                    yield Label("01 / EVALUACIÓN ORIENTATIVA", classes="section")
                    yield Static("Esperando telemetría", id="hypothesis")
                    yield Static("", id="evidence")
                    yield Static("", id="next-step")
                    yield Static("", id="forecast")
                    yield Static("Motor: reglas de demostración · sin modelo entrenado", id="method")
                with Vertical(id="mission"):
                    yield Label("02 / EXPOSICIÓN Y BITÁCORA", classes="section")
                    yield Static("Sin dosimetría", id="exposure")
                    yield Static("Los eventos aparecerán aquí.", id="events")
            with Vertical(id="controls"):
                yield Label("LABORATORIO DE DEMO / fuente independiente por API", classes="section")
                with Horizontal(classes="buttons"):
                    for i, (key, name) in enumerate(SCENARIOS.items(), start=1):
                        yield Button(f"{i} {name}", id=f"scenario-{key}")
                yield Static("Conectando con la pasarela…", id="gateway-status")
            yield Static("Datos sintéticos o reproducción clínica terrestre, identificados en pantalla. Umbrales ilustrativos; sin validación clínica.", id="notice")
        yield Footer()

    async def on_mount(self):
        self.client = httpx.AsyncClient(timeout=1.5, trust_env=False)
        self.set_interval(1, self.refresh_data)
        await self.refresh_data()

    async def on_unmount(self):
        if self.client:
            await self.client.aclose()

    async def refresh_data(self):
        if self.refreshing or self.client is None:
            return
        self.refreshing = True
        try:
            try:
                response = await self.client.get(f"{self.onboard_url}/api/v1/state")
                response.raise_for_status()
                self.last_state = response.json()
                self.render_state(self.last_state)
            except (httpx.HTTPError, ValueError):
                self.query_one("#status", Static).update(Text("API SIN CONEXIÓN · Los valores conservados NO son actuales.", style="#ff8d84"))
                self.query_one("#hypothesis", Static).update("Evaluación suspendida: no se puede consultar el nodo")
                self.query_one("#forecast", Static).update("Pronóstico no disponible durante la desconexión.")
            try:
                response = await self.client.get(f"{self.gateway_url}/control")
                response.raise_for_status()
                self.render_gateway(response.json())
            except (httpx.HTTPError, ValueError):
                self.query_one("#gateway-status", Static).update("PASARELA SIN CONEXIÓN · Controles de simulación no disponibles.")
        finally:
            self.refreshing = False

    def render_state(self, state):
        latest = state.get("latest") or {}
        assessment = state["assessment"]
        level, color = LEVELS.get(assessment["level"], LEVELS["unknown"])
        is_replay = latest.get("source") == "bidmc"
        source = "REPLAY REAL · BIDMC 01" if is_replay else "SIMULACIÓN · ASTRONAUTA FICTICIO"
        age = state.get("age_s")
        age_label = "sin lecturas" if age is None else f"último dato hace {max(0, age):.0f} s"
        self.query_one("#status", Static).update(Text.assemble((f"● {level}", color), f"   {source}   ·   {age_label}"))
        # A source change starts a separate displayed series.
        history = []
        for sample in reversed(state.get("history", [])):
            if sample.get("source") != latest.get("source"):
                break
            history.append(sample)
        history.reverse()
        for metric in self.query(Metric):
            metric.show_value(latest.get(metric.key), history)
        self.query_one("#hypothesis", Static).update(Text(assessment["title"], style=color))
        self.query_one("#evidence", Static).update(Text("\n".join(f"• {item}" for item in assessment.get("evidence", []))))
        self.query_one("#next-step", Static).update(Text("Revisión sugerida: " + assessment.get("next_step", "Esperar datos.")))
        forecast = assessment.get("forecast_hr")
        forecast_label = "Sin referencia de pulso disponible."
        if forecast is not None:
            forecast_label = f"Referencia a +60 s: {forecast:.0f} bpm · mantiene el último valor."
        self.query_one("#forecast", Static).update(Text(forecast_label))
        self.query_one("#method", Static).update(Text(assessment.get("method", "Reglas demo")))
        dose = state.get("dose_total", 0)
        coverage = "cobertura parcial" if not state.get("dose_complete", True) else "intervalos válidos"
        dose_text = f"Dosis simulada integrada: {dose:.3f} μSv\n{coverage} · acumulado de esta sesión"
        if is_replay:
            dose_text += "\nBIDMC no incluye dosimetría ni CO₂."
        self.query_one("#exposure", Static).update(Text(dose_text))
        events = state.get("events", [])[-5:]
        rows = []
        for event in reversed(events):
            try:
                stamp = datetime.fromisoformat(event["at"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%H:%M:%S")
            except (ValueError, KeyError):
                stamp = "—"
            rows.append(f"{stamp} UTC  {event['text']}")
        self.query_one("#events", Static).update(Text("\n\n".join(rows) or "Sin eventos todavía."))
        notice = (
            "Fuente: BIDMC PPG and Respiration Dataset v1.0.0 · PhysioNet · licencia ODC-By 1.0. Atribución y enlaces en README."
            if is_replay else
            "Datos sintéticos · umbrales ilustrativos · sin validación clínica. El modo 6 reproduce un registro real de PhysioNet."
        )
        self.query_one("#notice", Static).update(Text(notice))

    def render_gateway(self, control):
        self.gateway_state = control
        scenario = control.get("scenario", "rest")
        for key in SCENARIOS:
            self.query_one(f"#scenario-{key}", Button).set_class(key == scenario, "selected")
        phase = "PAUSADA" if control.get("paused") else "EMITIENDO"
        text = f"{phase} · {SCENARIOS.get(scenario, scenario)} · {control.get('sent_count', 0)} muestras enviadas"
        if scenario == "solar":
            text += " · refugio simulado " + ("ACTIVO" if control.get("shelter") else "INACTIVO")
        if scenario == "bidmc":
            text += f" · {control.get('remaining_samples', '—')} muestras restantes"
        if control.get("error"):
            text += f"\n{control['error']}"
        self.query_one("#gateway-status", Static).update(Text(text))

    async def set_control(self, **changes):
        if self.client is None:
            return
        try:
            response = await self.client.post(f"{self.gateway_url}/control", json=changes)
            response.raise_for_status()
            self.render_gateway(response.json())
        except httpx.HTTPError:
            self.notify("No se pudo cambiar la fuente. Comprueba la pasarela.", severity="error")

    async def action_scenario(self, scenario):
        await self.set_control(scenario=scenario, paused=False)

    async def action_pause(self):
        await self.set_control(paused=not self.gateway_state.get("paused", False))

    async def action_shelter(self):
        if self.gateway_state.get("scenario") != "solar":
            self.notify("El refugio se simula dentro del escenario 4: radiación.")
            return
        await self.set_control(shelter=not self.gateway_state.get("shelter", False))

    async def action_acknowledge(self):
        if self.client is None:
            return
        try:
            response = await self.client.post(f"{self.onboard_url}/api/v1/ack")
            response.raise_for_status()
            self.notify("Reconocimiento registrado; la condición se sigue evaluando.")
        except httpx.HTTPError:
            self.notify("No hay una alerta actual reconocible o el nodo no responde.", severity="warning")
        await self.refresh_data()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("scenario-"):
            await self.action_scenario(event.button.id.removeprefix("scenario-"))


if __name__ == "__main__":
    AstroVitalsApp().run()
