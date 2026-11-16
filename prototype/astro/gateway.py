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
    "exercise": (118.0, 25.0, 2.4, 0.6),
    "cabin": (86.0, 19.0, 4.8, 0.6),
    "co2_ramp": (72.0, 14.0, 2.0, 0.5),
    "solar": (74.0, 15.0, 2.0, 85.0),
    "solar_event": (74.0, 15.0, 2.0, 1.2),
    "signal_loss": (72.0, 14.0, 2.0, 0.5),
    "bidmc": (72.0, 14.0, 2.0, 0.5),
}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ControlUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario: Scenario | None = None
    paused: bool | None = None
    shelter: bool | None = None
    environment: EnvironmentId | None = None
    solar_phase: SolarPhase | None = None


class Gateway:
    def __init__(
        self,
        onboard_url: str | None = None,
        seed: int | None = None,
        scenario: Scenario = "rest",
        bidmc_path: Path | None = None,
    ):
        self.onboard_url = (onboard_url or os.getenv("ONBOARD_URL", "http://127.0.0.1:8001")).rstrip("/")
        self.seed = seed if seed is not None else _int_env("ASTRO_SEED", 7)
        self.rng = random.Random(self.seed)
        self.bidmc_path = bidmc_path or BIDMC_PATH
        self.scenario: Scenario = scenario
        self.paused = False
        self.shelter = False
        self.environment: str = "station"
        self._scenario_started_at = time.monotonic()
        self._solar_context: dict | None = None
        self.sent_count = 0
        self.error: str | None = None
        self._epoch = 0
        self._index = 0
        self._pending: tuple[dict, int] | None = None
        self.hr = TARGETS[self.scenario][0]
        self.rr = TARGETS[self.scenario][1]
        self.co2 = TARGETS[self.scenario][2]
        self.dose_rate = TARGETS[self.scenario][3]
        self._rows: list[dict[str, str]] = []

    def _load_rows(self) -> None:
        if self._rows or not self.bidmc_path.exists():
            return
        with self.bidmc_path.open("r", encoding="utf-8-sig", newline="") as handle:
            self._rows = list(csv.DictReader(handle))

    def _base_rate(self) -> float:
        if self.scenario in {"solar", "solar_event"} and self.shelter:
            return self.dose_rate * get_param("shelter_factor")
        return self.dose_rate

    def control(self) -> dict:
        payload = {
            "scenario": self.scenario,
            "paused": self.paused,
            "shelter": self.shelter,
            "environment": self.environment,
            "sent_count": self.sent_count,
            "source": "bidmc" if self.scenario == "bidmc" else "simulated",
            "remaining_samples": None,
            "error": self.error,
        }
        if self.scenario == "bidmc":
            payload["remaining_samples"] = max(0, len(self._rows) - self._index)
        if self.scenario in {"solar", "solar_event"} and self._solar_context is not None:
            payload["solar_phase"] = self._solar_context["phase"]
            payload["simulated_dose_rate_usvh"] = self._base_rate()
            payload["solar_event"] = self._solar_context
        else:
            payload["solar_phase"] = None
        return payload

    def update(self, change: ControlUpdate) -> dict:
        if change.environment is not None:
            get_profile(change.environment)
            self.environment = change.environment
        if change.scenario is not None:
            self.scenario = change.scenario
            self.shelter = False
            self.error = None
            self.paused = False
            self._pending = None
            self._index = 0
            self._epoch += 1
            self.hr, self.rr, self.co2, self.dose_rate = TARGETS[self.scenario]
            self._scenario_started_at = time.monotonic()
            self._solar_context = None
            if self.scenario == "bidmc":
                self._load_rows()
                if not self._rows:
                    self.error = f"Missing or empty BIDMC file: {self.bidmc_path}"
                    self.paused = True
            elif self.scenario == "co2_ramp":
                profile = get_profile(self.environment)
                self.co2 = float(profile.get("rest_targets", {}).get("co2", self.co2))
            elif self.scenario in {"solar", "solar_event"}:
                self._solar_context = donki.get_solar_context(
                    "watch",
                    shelter=self.shelter,
                    shelter_factor=get_param("shelter_factor"),
                )
                self.dose_rate = self._solar_context["base_dose_rate_usvh"]
        if change.solar_phase is not None and self.scenario in {"solar", "solar_event"}:
            self._solar_context = donki.get_solar_context(
                change.solar_phase,
                shelter=self.shelter,
                shelter_factor=get_param("shelter_factor"),
            )
            self.dose_rate = self._solar_context["base_dose_rate_usvh"]
        if change.paused is not None:
            self.paused = change.paused
        if change.shelter is not None:
            self.shelter = change.shelter and self.scenario in {"solar", "solar_event"}
            if self._solar_context is not None:
                self._solar_context = donki.get_solar_context(
                    self._solar_context["phase"],
                    shelter=self.shelter,
                    shelter_factor=get_param("shelter_factor"),
                )
                self.dose_rate = self._solar_context["base_dose_rate_usvh"]
        return self.control()

    @staticmethod
    def _float_or_none(raw: str | None) -> float | None:
        if raw is None:
            return None
        text = raw.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _resp(row: dict[str, str]) -> float | None:
        for key in ("RESP", "RESP,"):
            value = Gateway._float_or_none(row.get(key))
            if value is not None:
                return value
        return None

    def make_packet(self) -> dict | None:
        if self.scenario == "bidmc":
            self._load_rows()
            if self._index >= len(self._rows):
                self.paused = True
                return None
            row = self._rows[self._index]
            original = self._float_or_none(row.get("Time [s]"))
            payload = {
                "hr": self._float_or_none(row.get("HR")),
                "rr": self._resp(row),
                "co2": None,
                "dose_rate": None,
                "activity": "unknown",
                "source": "bidmc",
                "original_time_s": original,
            }
        else:
            if self.scenario == "co2_ramp":
                elapsed_s = max(0.0, time.monotonic() - self._scenario_started_at)
                profile = get_profile(self.environment)
                base_co2 = float(profile.get("rest_targets", {}).get("co2", 2.0))
                rate = float(profile.get("co2_ramp_rate_mmhg_min", 0.6))
                self.hr = _clamp(self.hr + self.rng.gauss(0.0, 0.6), 60.0, 90.0)
                self.rr = _clamp(self.rr + self.rng.gauss(0.0, 0.3), 10.0, 24.0)
                self.co2 = _clamp(base_co2 + rate * (elapsed_s / 60.0) + self.rng.gauss(0.0, 0.03), 0.0, 30.0)
                self.dose_rate = _clamp(self.dose_rate + self.rng.gauss(0.0, 0.03), 0.0, 2.0)
            elif self.scenario in {"solar", "solar_event"}:
                elapsed_s = max(0.0, time.monotonic() - self._scenario_started_at)
                phase = donki.phase_at_elapsed(elapsed_s)
                self._solar_context = donki.get_solar_context(
                    phase,
                    shelter=self.shelter,
                    shelter_factor=get_param("shelter_factor"),
                )
                self.hr = _clamp(self.hr + (74.0 - self.hr) * 0.35 + self.rng.gauss(0.0, 0.8), 60.0, 100.0)
                self.rr = _clamp(self.rr + (15.0 - self.rr) * 0.35 + self.rng.gauss(0.0, 0.4), 10.0, 30.0)
                self.co2 = _clamp(self.co2 + (2.0 - self.co2) * 0.3 + self.rng.gauss(0.0, 0.04), 0.0, 30.0)
                self.dose_rate = self._solar_context["base_dose_rate_usvh"]
            else:
                target_hr, target_rr, target_co2, target_dose = TARGETS[self.scenario]
                self.hr = _clamp(self.hr + (target_hr - self.hr) * 0.25 + self.rng.gauss(0.0, 0.8), 40.0, 180.0)
                self.rr = _clamp(self.rr + (target_rr - self.rr) * 0.25 + self.rng.gauss(0.0, 0.4), 8.0, 40.0)
                self.co2 = _clamp(self.co2 + (target_co2 - self.co2) * 0.25 + self.rng.gauss(0.0, 0.05), 0.0, 30.0)
                self.dose_rate = _clamp(self.dose_rate + (target_dose - self.dose_rate) * 0.25 + self.rng.gauss(0.0, 0.03), 0.0, 200.0)

            hr_val = round(self.hr, 2)
            rr_val = round(self.rr, 2)
            co2_val = round(self.co2, 3)
            dose_val = round(self._base_rate(), 4)
            spo2_val = round(_clamp(98.0 - self.co2 * 0.8 + self.rng.gauss(0.0, 0.1), 90.0, 100.0), 2)
            bp_sys_val = round(_clamp(120.0 + self.hr * 0.1 + self.rng.gauss(0.0, 0.5), 90.0, 160.0), 2)
            bp_dia_val = round(_clamp(80.0 + self.rr * 0.05 + self.rng.gauss(0.0, 0.3), 50.0, 100.0), 2)
            temp_val = round(_clamp(36.8 + self.hr * 0.001 + self.rng.gauss(0.0, 0.05), 36.0, 38.0), 2)
            hyd_val = round(_clamp(85.0 - self.hr * 0.05 + self.rng.gauss(0.0, 0.5), 60.0, 100.0), 2)

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
                self.error = "BIDMC record finished. Select BIDMC again to restart."

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
            self.error = "Onboard API not responding; packet pending retry."
            return
        if 200 <= response.status_code < 300:
            self.sent_count += 1
            self.error = None
            self._pending = None
            self._consume(packet, epoch)
        elif response.status_code >= 500:
            self.error = f"Onboard API: HTTP {response.status_code}; retrying the same packet."
        else:
            self.error = f"Packet rejected: HTTP {response.status_code}; sample discarded."
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

    application = FastAPI(title="ASTRO-VITALS · Demo gateway", lifespan=lifespan)
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
