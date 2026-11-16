"""Telemetry and control/context request contract; fixed units for this demo."""

import math
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    sample_id: str = Field(min_length=1, max_length=128)
    measured_at: AwareDatetime
    hr: float | None = Field(default=None, ge=0, le=300, description="bpm")
    rr: float | None = Field(default=None, ge=0, le=100, description="resp/min")
    co2: float | None = Field(default=None, ge=0, le=100, description="mmHg")
    dose_rate: float | None = Field(default=None, ge=0, description="μSv/h")
    activity: Literal["rest", "exercise", "recovery", "unknown"]
    source: Literal["simulated", "bidmc", "replayed", "measured"]
    original_time_s: float | None = Field(default=None, ge=0)

    crew_id: str | None = Field(default=None, max_length=64)
    location_id: str | None = Field(default=None, max_length=64)
    spo2: float | None = Field(default=None, ge=0, le=100, description="%")
    bp_sys: float | None = Field(default=None, ge=0, le=300, description="mmHg")
    bp_dia: float | None = Field(default=None, ge=0, le=200, description="mmHg")
    temp_c: float | None = Field(default=None, ge=20, le=45, description="°C")
    hydration_pct: float | None = Field(default=None, ge=0, le=100, description="%")
    extras: dict[str, float | str | None] | None = None
    source_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def preserve_real_data_provenance(self):
        if self.source == "bidmc" and (self.co2 is not None or self.dose_rate is not None):
            raise ValueError("BIDMC does not contain CO₂ or dosimetry: they must be null.")
        return self

    @model_validator(mode="after")
    def validate_extras(self):
        if self.extras is None:
            return self
        for key, value in self.extras.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Keys in 'extras' must be non-empty strings.")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not math.isfinite(value):
                    raise ValueError(f"Non-finite value in extras[{key!r}].")
        return self


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    reaction_ms: list[float] = Field(min_length=1)
    false_starts: int = Field(default=0, ge=0)
    lapses: int | None = Field(default=None, ge=0)
    sleep_hours: float = Field(default=7.0, ge=0, le=24)
    mood: int = Field(default=3, ge=1, le=5)
    source: Literal["declared", "simulated"] = "declared"

    @model_validator(mode="after")
    def validate_reaction_ms(self):
        for value in self.reaction_ms:
            if not math.isfinite(value) or value <= 0:
                raise ValueError("All reaction_ms values must be finite and greater than 0.")
        return self


class ActivityDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    activity: Literal["rest", "exercise", "recovery", "unknown"]
    started_at: AwareDatetime | None = None
    note: str | None = None


class ContextEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["solar", "clear"] = "solar"
    phase: Literal["watch", "arrival", "peak", "decay"] = "watch"
    shelter: bool = False


class PrivacyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    share_behavioral: bool


class EnvironmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    environment: Literal["transit", "station", "rover", "base"]
