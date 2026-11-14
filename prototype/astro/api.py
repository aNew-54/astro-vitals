"""API de la nave para la pasarela, puente web SQLite y TUI."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .contracts import (
    ActivityDeclaration,
    CheckInRequest,
    ContextEventRequest,
    EnvironmentUpdate,
    PrivacyUpdate,
    Telemetry,
)
from .engine import ConflictError, Engine
from .gateway import ControlUpdate, Gateway
from .glossary import get_glossary
from .storage import Storage
from .web_bridge import create_web_router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(
    engine: Engine | None = None,
    storage: Storage | None = None,
    gateway: Gateway | None = None,
    gateway_url: str | None = None,
) -> FastAPI:
    api = FastAPI(title="ASTRO-VITALS · prototipo", version="0.2.0")
    db_path = os.getenv("ASTRO_DB_PATH", ":memory:")
    api.state.engine = engine or Engine()
    api.state.storage = storage if storage is not None else Storage(db_path)
    api.state.gateway = gateway

    storage_mode = "memory" if (storage is None and db_path == ":memory:") else "sqlite"

    @api.get("/health")
    def health():
        return {"status": "ok", "prototype": True, "storage": storage_mode}

    @api.post("/api/v1/telemetry")
    def telemetry(sample: Telemetry):
        try:
            result = api.state.engine.ingest(sample)
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if result.get("accepted") and not result.get("duplicate"):
            current_state = api.state.engine.state()
            if api.state.gateway is not None:
                scenario = api.state.gateway.scenario
            elif sample.source == "bidmc":
                scenario = "bidmc"
            elif api.state.engine.external_event is not None:
                scenario = "solar_event"
            else:
                scenario = sample.activity
            api.state.storage.record_telemetry(
                sample,
                assessment=current_state["assessment"],
                scenario=scenario,
            )
        return result

    @api.get("/api/v1/state")
    def state():
        return api.state.engine.state()

    @api.get("/api/v1/trends")
    def trends(window_s: int = Query(default=3600)):
        try:
            return api.state.engine.trends(window_s=window_s)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.get("/api/v1/glossary")
    def glossary():
        return get_glossary()

    @api.get("/api/v1/routines")
    def routines():
        return api.state.engine.state()["coach"]

    @api.post("/api/v1/routines/{routine_id}/done")
    def complete_routine(routine_id: str):
        try:
            return api.state.engine.complete_routine(routine_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            detail = str(exc)
            code = 404 if "desconocida" in detail.lower() else 422
            raise HTTPException(status_code=code, detail=detail) from exc

    @api.post("/api/v1/checkin")
    def checkin(req: CheckInRequest):
        try:
            return api.state.engine.submit_checkin(req)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/api/v1/context/activity")
    def context_activity(req: ActivityDeclaration):
        try:
            return api.state.engine.set_activity_declaration(req)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/api/v1/context/event")
    def context_event(req: ContextEventRequest):
        try:
            return api.state.engine.set_external_event(req)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/api/v1/context/environment")
    def context_environment(req: EnvironmentUpdate):
        try:
            profile = api.state.engine.set_environment(req.environment)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if api.state.gateway is not None:
            api.state.gateway.update(ControlUpdate(environment=req.environment))
        return profile

    @api.post("/api/v1/privacy")
    def update_privacy(req: PrivacyUpdate):
        return api.state.engine.set_privacy(req.share_behavioral)

    @api.get("/api/v1/report")
    def episode_report(share_behavioral: bool | None = Query(default=None)):
        return api.state.engine.report(share_behavioral=share_behavioral)

    @api.post("/api/v1/ack")
    def acknowledge():
        try:
            result = api.state.engine.acknowledge()
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not result.get("duplicate"):
            api.state.storage.create_log(
                {
                    "zone": "console",
                    "action": "Alerta reconocida por la tripulación (/api/v1/ack)",
                }
            )
        return result

    api.include_router(
        create_web_router(
            engine=api.state.engine,
            storage=api.state.storage,
            gateway=gateway,
            gateway_url=gateway_url,
        )
    )

    if WEB_DIR.is_dir() and (WEB_DIR / "index.html").is_file():

        @api.get("/", include_in_schema=False)
        def web_index():
            return FileResponse(WEB_DIR / "index.html")

        for asset_dir in ("css", "js", "fonts"):
            subdir = WEB_DIR / asset_dir
            if subdir.is_dir():
                api.mount(
                    f"/{asset_dir}",
                    StaticFiles(directory=subdir),
                    name=f"web-{asset_dir}",
                )

        api.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="web-ui")

    return api


app = create_app()
