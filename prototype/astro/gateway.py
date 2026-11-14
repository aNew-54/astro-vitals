"""Independent demo gateway: sensor simulation or one BIDMC record over HTTP."""

from __future__ import annotations

import asyncio
import csv
import math
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from . import donki
from .config import get_param
from .profiles import get_profile

Scenario = Literal[
    "rest",
    "exercise",
    "cabin",
    "co2_ramp",
    "solar",
    "solar_event",
    "signal_loss",
    "bidmc",
]
EnvironmentId = Literal["transit", "station", "rover", "base"]
SolarPhase = Literal["watch", "arrival", "peak", "decay"]

BIDMC_PATH = Path(__file__).resolve().parents[1] / "data" / "bidmc_01_Numerics.csv"
TARGETS = {
    "rest": (72.0, 14.0, 2.0, 0.5),
    "exercise": (118.0, 25.0, 2.0, 0.5),
    "cabin": (105.0, 28.0, 5.0, 0.5),
    "solar": (74.0, 15.0, 2.0, 80.0),
    "signal_loss": (72.0, 14.0, 2.0, 0.5),
}


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def load_bidmc(path: Path) -> list[dict[str, float | None]]:
    """Read numeric parameters; preserve missingness and original relative time."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames is None:
            raise ValueError("El archivo BIDMC está vacío.")
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        if not {"Time [s]", "HR", "RESP"}.issubset(reader.fieldnames):
            raise ValueError("El CSV necesita Time [s], HR y RESP.")
        samples = []
        previous = -1.0
        for row in reader:
            original_time = _number(row["Time [s]"])
            if original_time is None or original_time < 0 or original_time <= previous:
                raise ValueError("El tiempo de BIDMC debe ser finito y creciente.")
            samples.append({
                "original_time_s": original_time,
                "hr": _number(row["HR"]),
                "rr": _number(row["RESP"]),
            })
            previous = original_time
    if not samples:
        raise ValueError("El archivo BIDMC no contiene muestras.")
    return samples


class ControlUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Scenario | None = None
    paused: bool | None = None
    shelter: bool | None = None
    environment: EnvironmentId | None = None
    solar_phase: SolarPhase | None = None


class Gateway:
    def __init__(self, onboard_url: str | None = None, bidmc_path: Path = BIDMC_PATH):
        self.onboard_url = (onboard_url or os.getenv("ONBOARD_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.bidmc_path = bidmc_path
        self.scenario: Scenario = "rest"
        self.environment: EnvironmentId = "station"
        self.paused = False
        self.shelter = False
        self._manual_solar_phase: SolarPhase | None = None
        self.sent_count = 0
        self.error: str | None = None
        self.started_at = time.monotonic()
        self._scenario_steps = 0
        self._values = list(TARGETS["rest"])
        self._random = random.Random(42)
        self._aux_random = random.Random(1042)
        self._rows: list[dict[str, float | None]] = []
        self._index = 0
        self._epoch = 0
        self._pending: tuple[dict, int] | None = None

    def _current_solar_phase(self) -> SolarPhase | None:
        if self.scenario != "solar_event":
            return None
        if self._manual_solar_phase is not None:
            return self._manual_solar_phase
        return donki.phase_at_elapsed(max(0.0, time.monotonic() - self.started_at))  # type: ignore[return-value]

    def control(self) -> dict:
        return {
            "scenario": self.scenario,
            "environment": self.environment,
            "paused": self.paused,
            "shelter": self.shelter,
            "solar_phase": self._current_solar_phase(),
            "sent_count": self.sent_count,
            "source": "bidmc" if self.scenario == "bidmc" else "simulated",
            "remaining_samples": max(0, len(self._rows) - self._index) if self.scenario == "bidmc" else None,
            "error": self.error,
        }

    def update(self, change: ControlUpdate) -> dict:
        if change.environment is not None:
            get_profile(change.environment)
            self.environment = change.environment
        if change.scenario is not None and (
            change.scenario != self.scenario or change.scenario == "bidmc"
        ):
            self.scenario = change.scenario
            self.started_at = time.monotonic()
            self._scenario_steps = 0
            self.shelter = False
            self._manual_solar_phase = None
            self.error = None
            self.paused = False
            self._epoch += 1
            self._index = 0
            if self.scenario == "co2_ramp":
                rest_targets = get_profile(self.environment)["rest_targets"]
                self._values = [
                    float(rest_targets["hr"]),
                    float(rest_targets["rr"]),
                    float(rest_targets["co2"]),
                    float(rest_targets["dose_rate"]),
                ]
            elif self.scenario == "bidmc":
                try:
                    self._rows = load_bidmc(self.bidmc_path)
                except (OSError, ValueError) as exc:
                    self._rows = []
                    self.paused = True
                    self.error = f"No se pudo abrir BIDMC: {exc}"
        if change.paused is not None:
            self.paused = change.paused
        if change.shelter is not None:
            self.shelter = change.shelter if self.scenario in {"solar", "solar_event"} else False
        if change.solar_phase is not None:
            self._manual_solar_phase = (
                change.solar_phase if self.scenario == "solar_event" else None
            )
        if self.scenario == "bidmc" and self._index >= len(self._rows):
            self.paused = True
            if self._rows:
                self.error = "Registro BIDMC finalizado. Vuelve a seleccionar BIDMC para reiniciar."
        return self.control()

    def make_packet(self) -> dict | None:
        if self.scenario == "bidmc":
            if self._index >= len(self._rows):
                self.paused = True
                self.error = "Registro BIDMC finalizado. Vuelve a seleccionar BIDMC para reiniciar."
                return None
            values = self._rows[self._index]
            payload = {
                **values,
                "co2": None,
                "dose_rate": None,
                "spo2": None,
                "bp_sys": None,
                "bp_dia": None,
                "temp_c": None,
                "hydration_pct": None,
                "activity": "unknown",
                "source": "bidmc",
            }
        else:
            profile = get_profile(self.environment)
            rest_targets = profile["rest_targets"]
            rad_mult = float(profile["radiation_multiplier"])

            if self.scenario == "co2_ramp":
                self._scenario_steps += 1
                elapsed_s = max(time.monotonic() - self.started_at, float(self._scenario_steps))
                ramp_rate_per_s = float(profile["co2_ramp_rate_mmhg_min"]) / 60.0
                co2_target = min(6.5, float(rest_targets["co2"]) + ramp_rate_per_s * elapsed_s)
                co2_excess = max(0.0, co2_target - float(rest_targets["co2"]))
                targets = (
                    min(115.0, float(rest_targets["hr"]) + co2_excess * 10.0),
                    min(32.0, float(rest_targets["rr"]) + co2_excess * 5.5),
                    co2_target,
                    float(rest_targets["dose_rate"]),
                )
                for index, target in enumerate(targets):
                    self._values[index] += (target - self._values[index]) * 0.4
            elif self.scenario == "solar_event":
                phase = self._current_solar_phase() or "watch"
                ctx = donki.get_solar_context(
                    phase=phase,
                    shelter=self.shelter,
                    shelter_factor=get_param("shelter_factor"),
                )
                dose_target = float(ctx["simulated_dose_rate_usvh"]) * rad_mult
                targets = (
                    float(rest_targets["hr"]) + 2.0,
                    float(rest_targets["rr"]) + 1.0,
                    float(rest_targets["co2"]),
                    dose_target,
                )
                for index in range(3):
                    self._values[index] += (targets[index] - self._values[index]) * 0.4
                self._values[3] = dose_target
            else:
                if self.scenario in {"rest", "signal_loss"}:
                    targets = (
                        float(rest_targets["hr"]),
                        float(rest_targets["rr"]),
                        float(rest_targets["co2"]),
                        float(rest_targets["dose_rate"]),
                    )
                elif self.scenario == "solar":
                    base_hr, base_rr, base_co2, base_dose = TARGETS["solar"]
                    targets = (base_hr, base_rr, base_co2, base_dose * rad_mult)
                else:
                    base_hr, base_rr, base_co2, base_dose = TARGETS[self.scenario]
                    targets = (base_hr, base_rr, base_co2, base_dose * rad_mult)
                for index, target in enumerate(targets):
                    if index == 3 and self.scenario == "solar" and self.shelter:
                        target = 3.0
                    self._values[index] += (target - self._values[index]) * 0.4

            hr, rr, co2, dose_rate = self._values
            # No consumir self._random antes de hr/rr para preservar compatibilidad determinista.
            hr_val = round(hr + self._random.uniform(-0.8, 0.8), 1)
            rr_val = round(rr + self._random.uniform(-0.25, 0.25), 1)
            co2_val = round(co2, 2)
            dose_val = round(dose_rate, 3)

            if self.scenario == "exercise":
                spo2_base, sys_base, dia_base, temp_base, hyd_base = 96.8, 134.0, 82.0, 37.3, 78.0
            elif co2_val >= 3.5:
                spo2_base, sys_base, dia_base, temp_base, hyd_base = 95.8, 124.0, 79.0, 36.8, 80.0
            else:
                spo2_base, sys_base, dia_base, temp_base, hyd_base = 98.2, 116.0, 74.0, 36.6, 84.0

            spo2_val = round(min(100.0, max(85.0, spo2_base + self._aux_random.uniform(-0.4, 0.4))), 1)
            bp_sys_val = round(sys_base + self._aux_random.uniform(-2.0, 2.0), 1)
            bp_dia_val = round(dia_base + self._aux_random.uniform(-1.5, 1.5), 1)
            temp_val = round(temp_base + self._aux_random.uniform(-0.1, 0.1), 1)
            hyd_val = round(min(100.0, max(20.0, hyd_base + self._aux_random.uniform(-0.5, 0.5))), 1)

            payload = {
                "hr": hr_val,
                "rr": rr_val,
                "co2": co2_val,
                "dose_rate": dose_val,
                "spo2": spo2_val,
                "bp_sys": bp_sys_val,
                "bp_dia": bp_dia_val,
                "temp_c": temp_val,
                "hydration_pct": hyd_val,
                "activity": "exercise" if self.scenario == "exercise" else "rest",
                "source": "simulated",
                "original_time_s": None,
            }
            if self.scenario == "signal_loss":
                for lost in ("hr", "rr", "spo2", "bp_sys", "bp_dia", "temp_c", "hydration_pct"):
                    payload[lost] = None
        return {
            "sample_id": str(uuid4()),
            "measured_at": datetime.now(UTC).isoformat(),
            **payload,
        }

    def _consume(self, packet: dict, epoch: int) -> None:
        if packet["source"] == "bidmc" and epoch == self._epoch:
            self._index += 1
            if self._index >= len(self._rows):
                self.paused = True
                self.error = "Registro BIDMC finalizado. Vuelve a seleccionar BIDMC para reiniciar."

    async def tick(self, client: httpx.AsyncClient) -> None:
        if self.paused:
            return
        if self._pending is None:
            packet = self.make_packet()
            if packet is None:
                return
            self._pending = (packet, self._epoch)
        packet, epoch = self._pending
        try:
            response = await client.post(f"{self.onboard_url}/api/v1/telemetry", json=packet)
        except httpx.RequestError:
            self.error = "API a bordo sin respuesta; paquete pendiente de reintento."
            return
        if 200 <= response.status_code < 300:
            self.sent_count += 1
            self.error = None
            self._pending = None
            self._consume(packet, epoch)
        elif response.status_code >= 500:
            self.error = f"API a bordo: HTTP {response.status_code}; reintentando el mismo paquete."
        else:
            self.error = f"Paquete rechazado: HTTP {response.status_code}; muestra descartada."
            self._pending = None
            self._consume(packet, epoch)

    async def run(self, stop: asyncio.Event) -> None:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            while not stop.is_set():
                started = time.monotonic()
                await self.tick(client)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=max(0.05, 1.0 - (time.monotonic() - started)))
                except TimeoutError:
                    pass


def create_app(gateway: Gateway | None = None, start_worker: bool = True) -> FastAPI:
    node = gateway or Gateway()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = asyncio.Event()
        task = asyncio.create_task(node.run(stop)) if start_worker else None
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task

    application = FastAPI(title="ASTRO-VITALS · Gateway de demostración", lifespan=lifespan)
    application.state.gateway = node

    @application.get("/health")
    async def health():
        return {"status": "ok", "service": "gateway"}

    @application.get("/control")
    async def get_control():
        return node.control()

    @application.post("/control")
    async def set_control(change: ControlUpdate):
        return node.update(change)

    return application


app = create_app()
