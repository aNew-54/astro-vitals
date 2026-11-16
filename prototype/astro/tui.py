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
    "rest": "Rest",
    "exercise": "Activity",
    "cabin": "Cabin / CO₂",
    "solar": "Radiation",
    "signal_loss": "Signal loss",
    "bidmc": "Real BIDMC",
}
LEVELS = {
    "normal": ("STABLE", "#66e0bd"),
    "watch": ("REVIEW", "#ffca73"),
    "alert": ("ATTENTION", "#ff8d84"),
    "unknown": ("NO ASSESSMENT", "#a4b2ca"),
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
        suffix = " · no data" if value is None else " · auto scale"
        self.query_one(f"#unit-{self.key}", Label).update(self.unit + suffix)


class AstroVitalsApp(App):
    TITLE = "ASTRO-VITALS · Mission console"
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
    #notice { height: auto; color: #93a5c5; margin-top: 1; }
    Footer { background: #101c2d; }
    """
    BINDINGS = [
        Binding("1", "scenario('rest')", "Rest", show=False),
        Binding("2", "scenario('exercise')", "Activity", show=False),
        Binding("3", "scenario('cabin')", "Cabin", show=False),
        Binding("4", "scenario('solar')", "Radiation", show=False),
        Binding("5", "scenario('signal_loss')", "No signal", show=False),
        Binding("6", "scenario('bidmc')", "BIDMC", show=False),
        Binding("p", "pause", "Pause source"),
        Binding("s", "shelter", "Simulated shelter"),
        Binding("a", "acknowledge", "Acknowledge"),
        Binding("q", "quit", "Quit"),
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
        yield Static(Text.assemble(("◈  ASTRO", "bold #72e1ca"), ("-VITALS", "bold white"), "   /   ONBOARD CONSOLE"), id="brand")
        yield Static("PROTOTYPE 0.1    ·    HABITAT 01    ·    INTERACTIVE DEMO", id="strap")
        with VerticalScroll(id="body"):
            yield Static("Connecting to onboard node…", id="status")
            with Horizontal(id="metrics"):
                yield Metric("hr", "HEART RATE", "bpm")
                yield Metric("rr", "RESPIRATION", "resp/min")
                yield Metric("co2", "CABIN CO₂", "mmHg")
                yield Metric("dose_rate", "DOSE RATE", "μSv/h")
            with Horizontal(id="detail"):
                with Vertical(id="analysis"):
                    yield Label("01 / ORIENTATIVE ASSESSMENT", classes="section")
                    yield Static("Waiting for telemetry", id="hypothesis")
                    yield Static("", id="evidence")
                    yield Static("", id="next-step")
                    yield Static("", id="forecast")
                    yield Static("Engine: demo rules · no trained model", id="method")
                with Vertical(id="mission"):
                    yield Label("02 / EXPOSURE AND LOG", classes="section")
                    yield Static("No dosimetry", id="exposure")
                    yield Static("Events will appear here.", id="events")
            with Vertical(id="controls"):
                yield Label("DEMO LAB / independent source via API", classes="section")
                with Horizontal(classes="buttons"):
                    for i, (key, name) in enumerate(SCENARIOS.items(), start=1):
                        yield Button(f"{i} {name}", id=f"scenario-{key}")
                yield Static("Connecting to gateway…", id="gateway-status")
            yield Static("Synthetic data or terrestrial clinical replay, identified on screen. Illustrative thresholds; no clinical validation.", id="notice")
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
                self.query_one("#status", Static).update(Text("API DISCONNECTED · Retained values are NOT current.", style="#ff8d84"))
                self.query_one("#hypothesis", Static).update("Assessment suspended: cannot query node")
                self.query_one("#forecast", Static).update("Forecast unavailable while disconnected.")
            try:
                response = await self.client.get(f"{self.gateway_url}/control")
                response.raise_for_status()
                self.render_gateway(response.json())
            except (httpx.HTTPError, ValueError):
                self.query_one("#gateway-status", Static).update("GATEWAY DISCONNECTED · Simulation controls unavailable.")
        finally:
            self.refreshing = False

    def render_state(self, state):
        latest = state.get("latest") or {}
        assessment = state["assessment"]
        level, color = LEVELS.get(assessment["level"], LEVELS["unknown"])
        is_replay = latest.get("source") == "bidmc"
        source = "REAL REPLAY · BIDMC 01" if is_replay else "SIMULATION · FICTIONAL ASTRONAUT"
        age = state.get("age_s")
        age_label = "no readings" if age is None else f"last data {max(0, age):.0f} s ago"
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
        self.query_one("#next-step", Static).update(Text("Suggested review: " + assessment.get("next_step", "Wait for data.")))
        forecast = assessment.get("forecast_hr")
        forecast_label = "No pulse reference available."
        if forecast is not None:
            forecast_label = f"+60 s reference: {forecast:.0f} bpm · keeps last value."
        self.query_one("#forecast", Static).update(Text(forecast_label))
        self.query_one("#method", Static).update(Text(assessment.get("method", "Demo rules")))
        dose = state.get("dose_total", 0)
        coverage = "partial coverage" if not state.get("dose_complete", True) else "valid intervals"
        dose_text = f"Integrated simulated dose: {dose:.3f} μSv\n{coverage} · accumulated this session"
        if is_replay:
            dose_text += "\nBIDMC does not include dosimetry or CO₂."
        self.query_one("#exposure", Static).update(Text(dose_text))
        events = state.get("events", [])[-5:]
        rows = []
        for event in reversed(events):
            try:
                stamp = datetime.fromisoformat(event["at"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%H:%M:%S")
            except (ValueError, KeyError):
                stamp = "—"
            rows.append(f"{stamp} UTC  {event['text']}")
        self.query_one("#events", Static).update(Text("\n\n".join(rows) or "No events yet."))
        notice = (
            "Source: BIDMC PPG and Respiration Dataset v1.0.0 · PhysioNet · ODC-By 1.0 license. Attribution and links in README."
            if is_replay
            else "Synthetic data · illustrative thresholds · no clinical validation. Mode 6 replays a real PhysioNet record."
        )
        self.query_one("#notice", Static).update(Text(notice))

    def render_gateway(self, control):
        self.gateway_state = control
        scenario = control.get("scenario", "rest")
        for key in SCENARIOS:
            self.query_one(f"#scenario-{key}", Button).set_class(key == scenario, "selected")
        phase = "PAUSED" if control.get("paused") else "EMITTING"
        text = f"{phase} · {SCENARIOS.get(scenario, scenario)} · {control.get('sent_count', 0)} samples sent"
        if scenario == "solar":
            text += " · simulated shelter " + ("ACTIVE" if control.get("shelter") else "INACTIVE")
        if scenario == "bidmc":
            text += f" · {control.get('remaining_samples', '—')} samples remaining"
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
            self.notify("Could not change source. Check the gateway.", severity="error")

    async def action_scenario(self, scenario):
        await self.set_control(scenario=scenario, paused=False)

    async def action_pause(self):
        await self.set_control(paused=not self.gateway_state.get("paused", False))

    async def action_shelter(self):
        if self.gateway_state.get("scenario") != "solar":
            self.notify("Shelter is simulated inside scenario 4: radiation.")
            return
        await self.set_control(shelter=not self.gateway_state.get("shelter", False))

    async def action_acknowledge(self):
        if self.client is None:
            return
        try:
            response = await self.client.post(f"{self.onboard_url}/api/v1/ack")
            response.raise_for_status()
            self.notify("Acknowledgment recorded; condition continues to be evaluated.")
        except httpx.HTTPError:
            self.notify("No current recognizable alert or node not responding.", severity="warning")
        await self.refresh_data()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("scenario-"):
            await self.action_scenario(event.button.id.removeprefix("scenario-"))


if __name__ == "__main__":
    AstroVitalsApp().run()
