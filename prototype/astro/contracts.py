"""Contrato reducido de telemetría; unidades fijas para esta demostración."""

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
    source: Literal["simulated", "bidmc"]
    original_time_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def preserve_real_data_provenance(self):
        if self.source == "bidmc" and (self.co2 is not None or self.dose_rate is not None):
            raise ValueError("BIDMC no contiene CO₂ ni dosimetría: deben ser null.")
        return self
