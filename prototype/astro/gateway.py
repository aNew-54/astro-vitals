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

Scenario = Literal["rest", "exercise", "cabin", "solar", "signal_loss", "bidmc"]
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


class Gateway:
    def __init__(self, onboard_url: str | None = None, bidmc_path: Path = BIDMC_PATH):
        self.onboard_url = (onboard_url or os.getenv("ONBOARD_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.bidmc_path = bidmc_path
        self.scenario: Scenario = "rest"
        self.paused = False
        self.shelter = False
        self.sent_count = 0
        self.error: str | None = None
        self.started_at = time.monotonic()
        self._values = list(TARGETS["rest"])
        self._random = random.Random(42)
        self._rows: list[dict[str, float | None]] = []
        self._index = 0
        self._epoch = 0
        self._pending: tuple[dict, int] | None = None

    def control(self) -> dict:
        return {
            "scenario": self.scenario,
            "paused": self.paused,
            "shelter": self.shelter,
            "sent_count": self.sent_count,
            "source": "bidmc" if self.scenario == "bidmc" else "simulated",
            "remaining_samples": max(0, len(self._rows) - self._index) if self.scenario == "bidmc" else None,
            "error": self.error,
        }

    def update(self, change: ControlUpdate) -> dict:
        if change.scenario is not None and (
            change.scenario != self.scenario or change.scenario == "bidmc"
        ):
            self.scenario = change.scenario
            self.started_at = time.monotonic()
            self.shelter = False
            self.error = None
            self.paused = False
            self._epoch += 1
            self._index = 0
            if self.scenario == "bidmc":
                try:
                    self._rows = load_bidmc(self.bidmc_path)
                except (OSError, ValueError) as exc:
                    self._rows = []
                    self.paused = True
                    self.error = f"No se pudo abrir BIDMC: {exc}"
        if change.paused is not None:
            self.paused = change.paused
        if change.shelter is not None:
            self.shelter = change.shelter if self.scenario == "solar" else False
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
                **values, "co2": None, "dose_rate": None,
                "activity": "unknown", "source": "bidmc",
            }
        else:
            targets = TARGETS[self.scenario]
            for index, target in enumerate(targets):
                if index == 3 and self.scenario == "solar" and self.shelter:
                    target = 3.0
                self._values[index] += (target - self._values[index]) * 0.4
            hr, rr, co2, dose_rate = self._values
            payload = {
                "hr": round(hr + self._random.uniform(-0.8, 0.8), 1),
                "rr": round(rr + self._random.uniform(-0.25, 0.25), 1),
                "co2": round(co2, 2), "dose_rate": round(dose_rate, 3),
                "activity": "exercise" if self.scenario == "exercise" else "rest",
                "source": "simulated", "original_time_s": None,
            }
            if self.scenario == "signal_loss":
                payload["hr"] = payload["rr"] = None
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
