"""API de la nave para la pasarela y la TUI, sin conexiones físicas asumidas."""

from fastapi import FastAPI, HTTPException

from .contracts import Telemetry
from .engine import ConflictError, Engine


def create_app(engine=None):
    api = FastAPI(title="ASTRO-VITALS · prototipo", version="0.1.0")
    api.state.engine = engine or Engine()

    @api.get("/health")
    def health():
        return {"status": "ok", "prototype": True, "storage": "memory"}

    @api.post("/api/v1/telemetry")
    def telemetry(sample: Telemetry):
        try:
            return api.state.engine.ingest(sample)
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.get("/api/v1/state")
    def state():
        return api.state.engine.state()

    @api.post("/api/v1/ack")
    def acknowledge():
        try:
            return api.state.engine.acknowledge()
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return api


app = create_app()
