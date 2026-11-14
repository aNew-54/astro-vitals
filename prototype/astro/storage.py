"""Persistencia SQLite pura (stdlib) para ASTRO-VITALS, preservando NULL estrictos."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterator, Mapping

NON_CLINICAL_PREFIX = "Hipótesis orientativa (escenario simulado)"
_IA_PREDICTION_RE = re.compile(r"\[IA\s*PREDICTION\]\s*:?\s*", re.IGNORECASE)
_HYPOTHESIS_RE = re.compile(r"^hip[óo]tesis\s*:\s*", re.IGNORECASE)

_DEFAULT_ASTRONAUT = {
    "id": 1,
    "code": "ASTRA-001",
    "name": "Cmdr. Elena Vance",
    "role": "Mission Commander",
    "mission": "ASTRA-01",
    "mission_day": 1,
    "age": 42,
    "blood_type": "O+",
    "height_cm": 170.0,
    "weight_kg": 65.0,
    "status": "nominal",
}

_METRIC_COLUMN_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("heart_rate_bpm", ("heart_rate_bpm", "hr")),
    ("systolic_bp", ("systolic_bp", "sys", "bp_sys")),
    ("diastolic_bp", ("diastolic_bp", "dia", "bp_dia")),
    ("spo2_percent", ("spo2_percent", "spo2")),
    ("body_temp_c", ("body_temp_c", "temp", "temp_c")),
    ("respiratory_rate_rpm", ("respiratory_rate_rpm", "rr")),
    ("ambient_co2_mmhg", ("ambient_co2_mmhg", "co2")),
    ("hydration_percent", ("hydration_percent", "hyd", "hydration_pct")),
    ("radiation_usvh", ("radiation_usvh", "dose", "dose_rate")),
    ("fatigue_index", ("fatigue_index", "fat")),
    ("countermeasures_percent", ("countermeasures_percent", "cm")),
    ("eva_load", ("eva_load",)),
)

_WS_FIELD_MAP: tuple[tuple[str, str, str], ...] = (
    ("hr", "heart_rate_bpm", "hr"),
    ("sys", "systolic_bp", "sys"),
    ("dia", "diastolic_bp", "dia"),
    ("spo2", "spo2_percent", "spo2"),
    ("temp", "body_temp_c", "temp"),
    ("rr", "respiratory_rate_rpm", "rr"),
    ("co2", "ambient_co2_mmhg", "co2"),
    ("hyd", "hydration_percent", "hyd"),
    ("dose", "radiation_usvh", "dose"),
    ("fat", "fatigue_index", "fat"),
    ("cm", "countermeasures_percent", "cm"),
)


class DuplicateRecordError(ValueError):
    """Error lanzado al intentar crear un registro con clave única duplicada."""


def utc_now_iso() -> str:
    """Retorna la marca de tiempo UTC actual en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(value: Any) -> str:
    if value is None:
        return utc_now_iso()
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    text = str(value).strip()
    return text or utc_now_iso()


def _to_float_or_none(value: Any) -> float | None:
    """Convierte a float finito preservando None/vacíos como NULL (nunca 0)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        num = float(text)
    elif isinstance(value, (int, float)):
        num = float(value)
    else:
        return None
    return num if math.isfinite(num) else None


def _pick_float(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        parsed = _to_float_or_none(payload[key])
        if parsed is not None:
            return parsed
    return None


def sanitize_non_clinical(text: str | None, *, force_prefix: bool = False) -> str:
    """Elimina '[IA PREDICTION]' y aplica encabezado orientativo no clínico."""
    raw = str(text or "").strip()
    had_ia_tag = bool(_IA_PREDICTION_RE.search(raw))
    cleaned = re.sub(r"\s{2,}", " ", _IA_PREDICTION_RE.sub("", raw)).strip()
    if not cleaned:
        return NON_CLINICAL_PREFIX if (force_prefix or had_ia_tag) else ""
    if cleaned.lower().startswith(NON_CLINICAL_PREFIX.lower()):
        return cleaned
    if force_prefix or had_ia_tag:
        stripped = _HYPOTHESIS_RE.sub("", cleaned).strip()
        return f"{NON_CLINICAL_PREFIX}: {stripped or cleaned}"
    return cleaned


def _infer_alert_metric_and_zone(
    title: str, sample: Mapping[str, Any], assessment: Mapping[str, Any]
) -> tuple[str, str]:
    lowered = title.lower()
    dose = _pick_float(sample, "dose_rate", "dose", "radiation_usvh")
    if "radiación" in lowered or "dosis" in lowered or (dose is not None and dose >= 40.0):
        return "dose_rate", "environment"
    if "co2" in lowered or "co₂" in lowered or "respiratorio" in lowered:
        return "co2", "cabin"
    if "pulso" in lowered or "frecuencia cardíaca" in lowered:
        return "hr", "cardiovascular"
    metric = str(assessment.get("metric") or "telemetry")
    zone = str(assessment.get("zone") or "cabin")
    return metric, zone


class Storage:
    """Almacenamiento SQLite seguro entre hilos para telemetría, alertas, bitácora e insights."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        self._lock = threading.RLock()
        self._memory_conn: sqlite3.Connection | None = None

        if self._is_memory:
            self._memory_conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                uri="mode=memory" in self.db_path,
            )
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()

    def close(self) -> None:
        """Cierra la conexión en memoria si existe."""
        with self._lock:
            if self._memory_conn is not None:
                self._memory_conn.close()
                self._memory_conn = None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._is_memory:
                if self._memory_conn is None:
                    raise RuntimeError("La conexión SQLite en memoria ya fue cerrada.")
                conn = self._memory_conn
                close_after = False
            else:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=30.0,
                    check_same_thread=False,
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                close_after = True

            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if close_after:
                    conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            if not self._is_memory:
                conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS astronauts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    mission TEXT NOT NULL,
                    mission_day INTEGER NOT NULL DEFAULT 1,
                    age INTEGER,
                    blood_type TEXT,
                    height_cm REAL,
                    weight_kg REAL,
                    status TEXT NOT NULL DEFAULT 'nominal'
                );

                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    astronaut_id INTEGER NOT NULL REFERENCES astronauts(id),
                    sample_id TEXT UNIQUE,
                    heart_rate_bpm REAL,
                    systolic_bp REAL,
                    diastolic_bp REAL,
                    spo2_percent REAL,
                    body_temp_c REAL,
                    respiratory_rate_rpm REAL,
                    ambient_co2_mmhg REAL,
                    hydration_percent REAL,
                    radiation_usvh REAL,
                    fatigue_index REAL,
                    countermeasures_percent REAL,
                    scenario TEXT,
                    eva_load REAL,
                    source TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    astronaut_id INTEGER NOT NULL,
                    measurement_id INTEGER,
                    severity TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    zone TEXT,
                    message TEXT NOT NULL,
                    suggested_action TEXT,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    astronaut_id INTEGER NOT NULL,
                    zone TEXT NOT NULL,
                    action TEXT NOT NULL,
                    metrics_json TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    astronaut_id INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO astronauts (
                    id, code, name, role, mission, mission_day,
                    age, blood_type, height_cm, weight_kg, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _DEFAULT_ASTRONAUT["id"],
                    _DEFAULT_ASTRONAUT["code"],
                    _DEFAULT_ASTRONAUT["name"],
                    _DEFAULT_ASTRONAUT["role"],
                    _DEFAULT_ASTRONAUT["mission"],
                    _DEFAULT_ASTRONAUT["mission_day"],
                    _DEFAULT_ASTRONAUT["age"],
                    _DEFAULT_ASTRONAUT["blood_type"],
                    _DEFAULT_ASTRONAUT["height_cm"],
                    _DEFAULT_ASTRONAUT["weight_kg"],
                    _DEFAULT_ASTRONAUT["status"],
                ),
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    @staticmethod
    def _row_to_alert(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["acknowledged"] = bool(item["acknowledged"])
        return item

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        raw_json = item.get("metrics_json")
        if raw_json:
            try:
                item["metrics"] = json.loads(raw_json)
            except json.JSONDecodeError:
                item["metrics"] = None
        else:
            item["metrics"] = None
        return item

    # ---------- Astronauts ----------

    def get_astronauts(self) -> list[dict[str, Any]]:
        """Lista todos los tripulantes ordenados por ID."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM astronauts ORDER BY id ASC").fetchall()
            return [dict(row) for row in rows]

    def get_astronaut(self, astronaut_id: int) -> dict[str, Any] | None:
        """Retorna un tripulante por ID o None si no existe."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM astronauts WHERE id = ?",
                (astronaut_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def create_astronaut(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Inserta un nuevo tripulante; lanza DuplicateRecordError si el código ya existe."""
        code = str(payload.get("code") or "").strip()
        name = str(payload.get("name") or "").strip()
        role = str(payload.get("role") or "").strip()
        mission = str(payload.get("mission") or "").strip()
        if not code or not name or not role or not mission:
            raise ValueError("code, name, role y mission son obligatorios.")

        mission_day = int(payload.get("mission_day") if payload.get("mission_day") is not None else 1)
        age = int(payload["age"]) if payload.get("age") is not None else None
        blood_type = str(payload["blood_type"]).strip() if payload.get("blood_type") is not None else None
        height_cm = _to_float_or_none(payload.get("height_cm"))
        weight_kg = _to_float_or_none(payload.get("weight_kg"))
        status = str(payload.get("status") or "nominal").strip()

        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO astronauts (
                        code, name, role, mission, mission_day,
                        age, blood_type, height_cm, weight_kg, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (code, name, role, mission, mission_day, age, blood_type, height_cm, weight_kg, status),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateRecordError(f"El código de tripulante '{code}' ya existe.") from exc

            row = conn.execute(
                "SELECT * FROM astronauts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    # ---------- Measurements ----------

    def _insert_measurement_in_tx(
        self,
        conn: sqlite3.Connection,
        payload: Mapping[str, Any],
        *,
        astronaut_id: int | None = None,
        scenario: str | None = None,
    ) -> dict[str, Any]:
        sample_id_raw = payload.get("sample_id")
        sample_id = str(sample_id_raw).strip() if sample_id_raw is not None and str(sample_id_raw).strip() else None

        if sample_id is not None:
            existing = conn.execute(
                "SELECT * FROM measurements WHERE sample_id = ?",
                (sample_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing)

        resolved_astronaut_id = int(
            astronaut_id if astronaut_id is not None else (payload.get("astronaut_id") or 1)
        )
        metrics = {
            column: _pick_float(payload, *aliases)
            for column, aliases in _METRIC_COLUMN_ALIASES
        }
        resolved_scenario = scenario if scenario is not None else payload.get("scenario")
        source = payload.get("source")
        timestamp = _normalize_timestamp(payload.get("measured_at") or payload.get("timestamp"))

        cursor = conn.execute(
            """
            INSERT INTO measurements (
                astronaut_id, sample_id,
                heart_rate_bpm, systolic_bp, diastolic_bp, spo2_percent,
                body_temp_c, respiratory_rate_rpm, ambient_co2_mmhg,
                hydration_percent, radiation_usvh, fatigue_index,
                countermeasures_percent, scenario, eva_load, source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_astronaut_id,
                sample_id,
                metrics["heart_rate_bpm"],
                metrics["systolic_bp"],
                metrics["diastolic_bp"],
                metrics["spo2_percent"],
                metrics["body_temp_c"],
                metrics["respiratory_rate_rpm"],
                metrics["ambient_co2_mmhg"],
                metrics["hydration_percent"],
                metrics["radiation_usvh"],
                metrics["fatigue_index"],
                metrics["countermeasures_percent"],
                str(resolved_scenario) if resolved_scenario is not None else None,
                metrics["eva_load"],
                str(source) if source is not None else None,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT * FROM measurements WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)

    def create_measurement(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Persiste una medición aceptando nombres largos o cortos sin convertir NULL en 0."""
        with self._connect() as conn:
            return self._insert_measurement_in_tx(conn, payload)

    def list_measurements(
        self, astronaut_id: int | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Lista mediciones recientes (NULL preservado), opcionalmente filtradas por tripulante."""
        with self._connect() as conn:
            if astronaut_id is not None:
                rows = conn.execute(
                    "SELECT * FROM measurements WHERE astronaut_id = ? ORDER BY id DESC LIMIT ?",
                    (astronaut_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM measurements ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(row) for row in rows]

    def get_latest_measurement(
        self, astronaut_id: int | None = None
    ) -> dict[str, Any] | None:
        """Retorna la medición más reciente o None si no hay registros."""
        with self._connect() as conn:
            if astronaut_id is not None:
                row = conn.execute(
                    "SELECT * FROM measurements WHERE astronaut_id = ? ORDER BY id DESC LIMIT 1",
                    (astronaut_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM measurements ORDER BY id DESC LIMIT 1"
                ).fetchone()
            return self._row_to_dict(row)

    def get_latest_measurements(self) -> list[dict[str, Any]]:
        """Retorna la medición más reciente de cada tripulante."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*
                FROM measurements m
                INNER JOIN (
                    SELECT astronaut_id, MAX(id) AS max_id
                    FROM measurements
                    GROUP BY astronaut_id
                ) latest ON m.id = latest.max_id
                ORDER BY m.astronaut_id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_measurement(self, measurement_id: int) -> dict[str, Any] | None:
        """Retorna una medición por ID o None si no existe."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM measurements WHERE id = ?",
                (measurement_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def record_telemetry(
        self,
        sample: Mapping[str, Any] | Any,
        assessment: Mapping[str, Any] | None = None,
        scenario: str | None = None,
        astronaut_id: int = 1,
    ) -> dict[str, Any]:
        """Guarda telemetría del Engine de forma idempotente y deriva alerta/insight si aplica."""
        raw = sample.model_dump(mode="json") if hasattr(sample, "model_dump") else dict(sample)
        sample_id_raw = raw.get("sample_id")
        sample_id = str(sample_id_raw).strip() if sample_id_raw is not None and str(sample_id_raw).strip() else None

        with self._connect() as conn:
            if sample_id is not None:
                existing = conn.execute(
                    "SELECT * FROM measurements WHERE sample_id = ?",
                    (sample_id,),
                ).fetchone()
                if existing is not None:
                    return dict(existing)

            measurement = self._insert_measurement_in_tx(
                conn,
                raw,
                astronaut_id=astronaut_id,
                scenario=scenario,
            )

            if isinstance(assessment, Mapping):
                level = str(assessment.get("level") or "").strip().lower()
                if level in {"watch", "alert"}:
                    severity = "warning" if level == "watch" else "critical"
                    raw_title = str(
                        assessment.get("hypothesis")
                        or assessment.get("title")
                        or "Cambio observado en telemetría"
                    )
                    message = sanitize_non_clinical(raw_title, force_prefix=True)
                    suggested_action = sanitize_non_clinical(
                        str(assessment.get("next_step") or "Revisar señales y contexto operativo.")
                    )
                    metric, zone = _infer_alert_metric_and_zone(raw_title, raw, assessment)

                    last_alert = conn.execute(
                        "SELECT * FROM alerts WHERE astronaut_id = ? ORDER BY id DESC LIMIT 1",
                        (astronaut_id,),
                    ).fetchone()
                    should_create_alert = (
                        last_alert is None
                        or bool(last_alert["acknowledged"])
                        or last_alert["severity"] != severity
                        or last_alert["metric"] != metric
                        or last_alert["message"] != message
                    )
                    if should_create_alert:
                        conn.execute(
                            """
                            INSERT INTO alerts (
                                astronaut_id, measurement_id, severity, metric,
                                zone, message, suggested_action, acknowledged, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                            """,
                            (
                                astronaut_id,
                                measurement["id"],
                                severity,
                                metric,
                                zone,
                                message,
                                suggested_action,
                                measurement["timestamp"],
                            ),
                        )
                        evidence_items = [
                            sanitize_non_clinical(str(item))
                            for item in (assessment.get("evidence") or [])
                            if item
                        ]
                        description = (
                            message
                            if not evidence_items
                            else f"{message} — {' '.join(evidence_items[:2])}"
                        )
                        conn.execute(
                            """
                            INSERT INTO insights (
                                astronaut_id, risk_level, category,
                                description, recommendation, timestamp
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                astronaut_id,
                                "critical" if severity == "critical" else "warning",
                                zone,
                                description,
                                suggested_action,
                                measurement["timestamp"],
                            ),
                        )

            return measurement

    # ---------- Alerts ----------

    def list_alerts(
        self,
        astronaut_id: int | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Lista alertas con filtros opcionales."""
        clauses: list[str] = []
        params: list[Any] = []
        if astronaut_id is not None:
            clauses.append("astronaut_id = ?")
            params.append(astronaut_id)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)
        if acknowledged is not None:
            clauses.append("acknowledged = ?")
            params.append(1 if acknowledged else 0)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM alerts {where} ORDER BY id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_alert(row) for row in rows]

    def create_alert(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Crea una alerta sanitizando cualquier texto clínico o '[IA PREDICTION]'."""
        astronaut_id = int(payload.get("astronaut_id") or 1)
        measurement_id = payload.get("measurement_id")
        severity = str(payload.get("severity") or "warning").strip().lower()
        metric = str(payload.get("metric") or "general").strip()
        zone = str(payload["zone"]).strip() if payload.get("zone") is not None else None
        message = sanitize_non_clinical(payload.get("message") or "Aviso de telemetría")
        raw_action = payload.get("suggested_action")
        suggested_action = sanitize_non_clinical(raw_action) if raw_action is not None else None
        acknowledged = 1 if payload.get("acknowledged") else 0
        created_at = _normalize_timestamp(payload.get("created_at"))

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO alerts (
                    astronaut_id, measurement_id, severity, metric,
                    zone, message, suggested_action, acknowledged, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    astronaut_id,
                    measurement_id,
                    severity,
                    metric,
                    zone,
                    message,
                    suggested_action,
                    acknowledged,
                    created_at,
                ),
            )
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return self._row_to_alert(row)

    def acknowledge_alert(self, alert_id: int) -> dict[str, Any] | None:
        """Marca una alerta como reconocida; retorna None si no existe."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?",
                (alert_id,),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
            return self._row_to_alert(row) if row is not None else None

    # ---------- Logs ----------

    def list_logs(
        self, astronaut_id: int | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Lista entradas de bitácora ordenadas de la más reciente a la más antigua."""
        with self._connect() as conn:
            if astronaut_id is not None:
                rows = conn.execute(
                    "SELECT * FROM logs WHERE astronaut_id = ? ORDER BY id DESC LIMIT ?",
                    (astronaut_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM logs ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [self._row_to_log(row) for row in rows]

    def create_log(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Crea un registro en la bitácora."""
        astronaut_id = int(payload.get("astronaut_id") or 1)
        zone = str(payload.get("zone") or "general").strip()
        action = str(payload.get("action") or "Escaneo rutinario sin acciones").strip()
        timestamp = _normalize_timestamp(payload.get("timestamp"))

        raw_metrics_json = payload.get("metrics_json")
        raw_metrics = payload.get("metrics")
        if raw_metrics_json is not None:
            metrics_json = (
                raw_metrics_json
                if isinstance(raw_metrics_json, str)
                else json.dumps(raw_metrics_json, ensure_ascii=False)
            )
        elif raw_metrics is not None:
            metrics_json = json.dumps(raw_metrics, ensure_ascii=False)
        else:
            metrics_json = None

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs (astronaut_id, zone, action, metrics_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (astronaut_id, zone, action, metrics_json, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM logs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return self._row_to_log(row)

    # ---------- Insights ----------

    def get_insights(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lista los insights más recientes."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM insights ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_insight(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Crea un insight no clínico y, si risk_level == 'critical', crea su alerta asociada."""
        astronaut_id = int(payload.get("astronaut_id") or 1)
        risk_level = str(payload.get("risk_level") or "info").strip().lower()
        category = str(payload.get("category") or "telemetry").strip()
        is_critical = risk_level == "critical"
        description = sanitize_non_clinical(
            payload.get("description") or "Observación de escenario simulado",
            force_prefix=is_critical,
        )
        recommendation = sanitize_non_clinical(payload.get("recommendation") or "")
        timestamp = _normalize_timestamp(payload.get("timestamp"))

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO insights (
                    astronaut_id, risk_level, category,
                    description, recommendation, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (astronaut_id, risk_level, category, description, recommendation, timestamp),
            )
            insight_row = conn.execute(
                "SELECT * FROM insights WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

            if is_critical:
                alert_message = sanitize_non_clinical(description, force_prefix=True)
                alert_action = recommendation or "Revisar telemetría y contexto operativo."
                conn.execute(
                    """
                    INSERT INTO alerts (
                        astronaut_id, measurement_id, severity, metric,
                        zone, message, suggested_action, acknowledged, created_at
                    ) VALUES (?, ?, 'critical', ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        astronaut_id,
                        payload.get("measurement_id"),
                        category,
                        str(payload.get("zone") or category),
                        alert_message,
                        alert_action,
                        timestamp,
                    ),
                )

            return dict(insight_row)

    # ---------- WebSocket Payload ----------

    @staticmethod
    def to_ws_payload(measurement: Mapping[str, Any]) -> dict[str, Any]:
        """Convierte una fila de measurements al contrato corto de WS /telemetry preservando None."""
        payload: dict[str, Any] = {
            "type": "telemetry",
            "astronaut_id": measurement.get("astronaut_id"),
            "measurement_id": measurement["id"] if "id" in measurement else measurement.get("measurement_id"),
            "timestamp": measurement.get("timestamp"),
            "source": measurement.get("source"),
            "scenario": measurement.get("scenario"),
            "eva_load": measurement.get("eva_load"),
        }
        for short_key, long_key, fallback_key in _WS_FIELD_MAP:
            if long_key in measurement:
                payload[short_key] = measurement[long_key]
            else:
                payload[short_key] = measurement.get(fallback_key)
        return payload
