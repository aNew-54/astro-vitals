"""REST + WebSocket bridge between SQLite, Engine, Gateway, and the web console."""

from __future__ import annotations

import asyncio
import os
from threading import RLock
from types import SimpleNamespace
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import ContextEventRequest, Telemetry
from .engine import ConflictError
from .gateway import ControlUpdate, Gateway
from .storage import DuplicateRecordError, Storage


class AstronautCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=128)
    mission: str = Field(min_length=1, max_length=128)
    mission_day: int = 1
    age: int | None = None
    blood_type: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    status: str = "nominal"


class MeasurementCreate(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    astronaut_id: int = 1
    sample_id: str | None = None
    timestamp: str | None = None
    measured_at: str | None = None
    scenario: str | None = None
    source: str | None = None
    eva_load: float | None = None

    heart_rate_bpm: float | None = None
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    spo2_percent: float | None = None
    body_temp_c: float | None = None
    respiratory_rate_rpm: float | None = None
    ambient_co2_mmhg: float | None = None
    hydration_percent: float | None = None
    radiation_usvh: float | None = None
    fatigue_index: float | None = None
    countermeasures_percent: float | None = None

    hr: float | None = None
    sys: float | None = None
    bp_sys: float | None = None
    dia: float | None = None
    bp_dia: float | None = None
    spo2: float | None = None
    temp: float | None = None
    temp_c: float | None = None
    rr: float | None = None
    co2: float | None = None
    hyd: float | None = None
    hydration_pct: float | None = None
    dose: float | None = None
    dose_rate: float | None = None
    fat: float | None = None
    cm: float | None = None


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    astronaut_id: int = 1
    measurement_id: int | None = None
    severity: str = "warning"
    metric: str = "general"
    zone: str | None = None
    message: str = Field(min_length=1)
    suggested_action: str | None = None
    acknowledged: bool = False
    created_at: str | None = None


class LogCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    astronaut_id: int = 1
    zone: str = "general"
    action: str = "Routine scan with no actions"
    metrics: dict[str, Any] | list[Any] | None = None
    metrics_json: str | None = None
    timestamp: str | None = None


class InsightCreate(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    astronaut_id: int = 1
    measurement_id: int | None = None
    risk_level: str = "info"
    category: str = "telemetry"
    zone: str | None = None
    description: str = Field(min_length=1)
    recommendation: str = ""
    timestamp: str | None = None


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    scenario: str | None = None
    paused: bool | None = None
    shelter: bool | None = None
    environment: str | None = None
    solar_phase: str | None = None
    emit_now: bool | None = None


def _apply_inprocess_gateway_update(
    gateway: Any,
    *,
    scenario: str | None,
    paused: bool | None,
    shelter: bool | None,
    environment: str | None,
    solar_phase: str | None,
) -> dict[str, Any]:
    fields = {
        key: value
        for key, value in (
            ("scenario", scenario),
            ("paused", paused),
            ("shelter", shelter),
            ("environment", environment),
            ("solar_phase", solar_phase),
        )
        if value is not None
    }
    if not fields:
        return dict(gateway.control()) if hasattr(gateway, "control") else {}

    if isinstance(gateway, Gateway):
        try:
            change = ControlUpdate(**fields)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return dict(gateway.update(change))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Test stubs: try ControlUpdate and if it rejects fields/values, pass an object/dict.
    try:
        change_obj: Any = ControlUpdate(**fields)
    except ValidationError:
        change_obj = SimpleNamespace(
            scenario=scenario,
            paused=paused,
            shelter=shelter,
            environment=environment,
            solar_phase=solar_phase,
        )

    try:
        result = gateway.update(change_obj)
    except (TypeError, AttributeError):
        result = gateway.update(fields)

    if hasattr(gateway, "control"):
        return dict(gateway.control())
    return dict(result) if isinstance(result, Mapping) else {}


def _emit_immediate_sample(
    gateway: Any,
    engine: Any,
    storage: Storage,
    requested_scenario: str | None,
    gw_data: dict[str, Any],
) -> dict[str, Any]:
    packet = gateway.make_packet()
    if packet is None:
        return gw_data

    raw_packet = packet.model_dump(mode="json") if hasattr(packet, "model_dump") else dict(packet)
    telemetry_fields = {k: v for k, v in raw_packet.items() if k in Telemetry.model_fields}
    try:
        sample = Telemetry(**telemetry_fields)
        engine.ingest(sample)
    except (ValidationError, ConflictError, ValueError):
        return gw_data

    if isinstance(gateway, Gateway):
        gateway._consume(raw_packet, gateway._epoch)
        gateway.sent_count += 1
        gw_data = dict(gateway.control())

    assessment = None
    if hasattr(engine, "state"):
        try:
            assessment = engine.state().get("assessment")
        except Exception:
            assessment = None

    storage.record_telemetry(
        raw_packet,
        assessment=assessment,
        scenario=requested_scenario or gw_data.get("scenario"),
    )
    return gw_data


def create_web_router(
    engine: Any = None,
    storage: Storage | None = None,
    gateway: Any = None,
    gateway_url: str | None = None,
    *,
    ws_poll_interval: float = 0.5,
) -> APIRouter:
    """Create the APIRouter with REST /api/* endpoints and /telemetry WebSocket."""
    db = storage if storage is not None else Storage(os.getenv("ASTRO_DB_PATH", ":memory:"))
    resolved_gateway_url = (gateway_url or os.getenv("GATEWAY_URL", "")).strip().rstrip("/") or None
    control_lock = RLock()
    control_meta: dict[str, Any] = {
        "scenario": "rest",
        "paused": False,
        "shelter": False,
        "environment": "station",
        "solar_phase": None,
    }

    router = APIRouter()

    def _fallback_control(error: str | None = None) -> dict[str, Any]:
        with control_lock:
            scenario = control_meta["scenario"]
            return {
                "scenario": scenario,
                "paused": control_meta["paused"],
                "shelter": control_meta["shelter"],
                "environment": control_meta["environment"],
                "solar_phase": control_meta["solar_phase"],
                "sent_count": 0,
                "source": "bidmc" if scenario == "bidmc" else "simulated",
                "remaining_samples": None,
                "error": error,
            }

    def _merge_control_meta(gw_data: dict[str, Any]) -> dict[str, Any]:
        with control_lock:
            for key in ("scenario", "paused", "shelter", "environment"):
                if key in gw_data and gw_data[key] is not None:
                    control_meta[key] = gw_data[key]
            if "solar_phase" in gw_data:
                control_meta["solar_phase"] = gw_data["solar_phase"]
            merged = dict(gw_data)
            merged.setdefault("scenario", control_meta["scenario"])
            merged.setdefault("paused", control_meta["paused"])
            merged.setdefault("shelter", control_meta["shelter"])
            merged["environment"] = merged.get("environment") or control_meta["environment"]
            merged["solar_phase"] = merged.get("solar_phase", control_meta["solar_phase"])
            return merged

    # ---------- Astronauts ----------

    @router.get("/api/astronauts/")
    def list_astronauts() -> list[dict[str, Any]]:
        return db.get_astronauts()

    @router.get("/api/astronauts/{astronaut_id}")
    def get_astronaut(astronaut_id: int) -> dict[str, Any]:
        astronaut = db.get_astronaut(astronaut_id)
        if astronaut is None:
            raise HTTPException(status_code=404, detail="Crew member not found.")
        return astronaut

    @router.post("/api/astronauts/", status_code=status.HTTP_201_CREATED)
    def create_astronaut(body: AstronautCreate) -> dict[str, Any]:
        try:
            return db.create_astronaut(body.model_dump())
        except DuplicateRecordError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ---------- Measurements ----------

    @router.get("/api/measurements/")
    def list_measurements(
        astronaut_id: int | None = None,
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return db.list_measurements(astronaut_id=astronaut_id, limit=limit)

    @router.get("/api/measurements/latest")
    def latest_measurements(astronaut_id: int | None = None) -> list[dict[str, Any]]:
        if astronaut_id is not None:
            latest = db.get_latest_measurement(astronaut_id=astronaut_id)
            return [latest] if latest is not None else []
        return db.get_latest_measurements()

    @router.post("/api/measurements/", status_code=status.HTTP_201_CREATED)
    def create_measurement(body: MeasurementCreate) -> dict[str, Any]:
        if db.get_astronaut(body.astronaut_id) is None:
            raise HTTPException(status_code=404, detail="Crew member not found.")
        return db.create_measurement(body.model_dump())

    # ---------- Alerts ----------

    @router.get("/api/alerts/")
    def list_alerts(
        astronaut_id: int | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[dict[str, Any]]:
        return db.list_alerts(
            astronaut_id=astronaut_id,
            severity=severity,
            acknowledged=acknowledged,
        )

    @router.post("/api/alerts/", status_code=status.HTTP_201_CREATED)
    def create_alert(body: AlertCreate) -> dict[str, Any]:
        return db.create_alert(body.model_dump())

    @router.patch("/api/alerts/{alert_id}/ack")
    def acknowledge_alert(alert_id: int) -> dict[str, Any]:
        updated = db.acknowledge_alert(alert_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Alert not found.")
        return updated

    # ---------- Logs ----------

    @router.get("/api/logs/")
    def list_logs(
        astronaut_id: int | None = None,
        limit: int = Query(default=50, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return db.list_logs(astronaut_id=astronaut_id, limit=limit)

    @router.post("/api/logs/", status_code=status.HTTP_201_CREATED)
    def create_log(body: LogCreate) -> dict[str, Any]:
        return db.create_log(body.model_dump())

    # ---------- Insights ----------

    @router.get("/api/insights/")
    def list_insights(
        limit: int = Query(default=50, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return db.get_insights(limit=limit)

    @router.post("/api/insights/", status_code=status.HTTP_201_CREATED)
    def create_insight(body: InsightCreate) -> dict[str, Any]:
        return db.create_insight(body.model_dump())

    # ---------- Gateway & Engine Control ----------

    @router.get("/api/control")
    async def get_control() -> dict[str, Any]:
        if gateway is not None:
            data = dict(gateway.control()) if hasattr(gateway, "control") else {}
            return _merge_control_meta(data)

        if resolved_gateway_url:
            try:
                async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                    response = await client.get(f"{resolved_gateway_url}/control")
                if 200 <= response.status_code < 300:
                    return _merge_control_meta(response.json())
                return _fallback_control(error=f"Gateway HTTP {response.status_code}")
            except httpx.HTTPError:
                return _fallback_control(error="Gateway not responding; using local state.")

        return _fallback_control()

    @router.post("/api/control")
    async def set_control(body: ControlRequest) -> dict[str, Any]:
        if body.environment is not None:
            env_name = body.environment.strip()
            if not env_name:
                raise HTTPException(status_code=422, detail="environment cannot be empty.")
            if engine is not None and hasattr(engine, "set_environment"):
                try:
                    engine.set_environment(env_name)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            with control_lock:
                control_meta["environment"] = env_name

        normalized_phase: str | None = None
        if body.solar_phase is not None:
            try:
                validated_event = ContextEventRequest(kind="solar", phase=body.solar_phase)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            normalized_phase = validated_event.phase

        gw_data: dict[str, Any]
        if gateway is not None:
            gw_data = _apply_inprocess_gateway_update(
                gateway,
                scenario=body.scenario,
                paused=body.paused,
                shelter=body.shelter,
                environment=body.environment,
                solar_phase=normalized_phase,
            )
        elif resolved_gateway_url:
            gw_payload = {
                key: value
                for key, value in (
                    ("scenario", body.scenario),
                    ("paused", body.paused),
                    ("shelter", body.shelter),
                    ("environment", body.environment),
                    ("solar_phase", normalized_phase),
                )
                if value is not None
            }
            try:
                async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                    if gw_payload:
                        response = await client.post(
                            f"{resolved_gateway_url}/control",
                            json=gw_payload,
                        )
                    else:
                        response = await client.get(f"{resolved_gateway_url}/control")
                if 200 <= response.status_code < 300:
                    gw_data = response.json()
                elif response.status_code == 422:
                    raise HTTPException(status_code=422, detail=response.text)
                else:
                    gw_data = _fallback_control(error=f"Gateway HTTP {response.status_code}")
            except httpx.HTTPError:
                with control_lock:
                    if body.scenario is not None:
                        control_meta["scenario"] = body.scenario
                        control_meta["shelter"] = False
                        control_meta["paused"] = False
                    if body.paused is not None:
                        control_meta["paused"] = body.paused
                    if body.shelter is not None:
                        control_meta["shelter"] = (
                            body.shelter if control_meta["scenario"] in {"solar", "solar_event"} else False
                        )
                gw_data = _fallback_control(error="Gateway not responding; using local state.")
        else:
            with control_lock:
                if body.scenario is not None:
                    control_meta["scenario"] = body.scenario
                    control_meta["shelter"] = False
                    control_meta["paused"] = False
                if body.paused is not None:
                    control_meta["paused"] = body.paused
                if body.shelter is not None:
                    control_meta["shelter"] = (
                        body.shelter if control_meta["scenario"] in {"solar", "solar_event"} else False
                    )
            gw_data = _fallback_control()

        with control_lock:
            if normalized_phase is not None:
                control_meta["solar_phase"] = normalized_phase
            elif gw_data.get("solar_phase") is not None:
                control_meta["solar_phase"] = gw_data["solar_phase"]
            elif body.scenario is not None:
                if body.scenario in {"solar", "solar_event"}:
                    control_meta["solar_phase"] = control_meta["solar_phase"] or "watch"
                else:
                    control_meta["solar_phase"] = None
            active_phase = control_meta["solar_phase"]

        effective_scenario = body.scenario if body.scenario is not None else gw_data.get("scenario")
        effective_shelter = bool(gw_data.get("shelter", False))
        is_solar = (effective_scenario in {"solar", "solar_event"}) or (normalized_phase is not None)

        if engine is not None and hasattr(engine, "set_external_event"):
            if is_solar:
                engine.set_external_event(
                    {
                        "kind": "solar",
                        "phase": active_phase or "watch",
                        "shelter": effective_shelter,
                    }
                )
            elif body.scenario is not None:
                engine.set_external_event({"kind": "clear"})

        should_emit = (body.emit_now is True) or (
            body.emit_now is None and gateway is not None and engine is not None
        )
        if (
            should_emit
            and not gw_data.get("paused")
            and gateway is not None
            and hasattr(gateway, "make_packet")
            and engine is not None
            and hasattr(engine, "ingest")
        ):
            gw_data = _emit_immediate_sample(
                gateway=gateway,
                engine=engine,
                storage=db,
                requested_scenario=body.scenario,
                gw_data=gw_data,
            )

        return _merge_control_meta(gw_data)

    # ---------- WebSocket ----------

    @router.websocket("/telemetry")
    async def telemetry_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        latest = db.get_latest_measurement()
        if latest is None:
            await websocket.send_json({"type": "no_data"})
            last_sent_id: int | None = None
        else:
            await websocket.send_json(db.to_ws_payload(latest))
            last_sent_id = latest["id"]

        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive(),
                        timeout=ws_poll_interval,
                    )
                    if message.get("type") == "websocket.disconnect":
                        break
                except TimeoutError:
                    pass

                current = db.get_latest_measurement()
                if current is not None and current["id"] != last_sent_id:
                    await websocket.send_json(db.to_ws_payload(current))
                    last_sent_id = current["id"]
        except (WebSocketDisconnect, RuntimeError):
            return

    return router
