"""Orientative and educational glossary of signals and levels for ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

SIGNAL_GLOSSARY: dict[str, dict[str, str]] = {
    "hr": {
        "what_is": "Heart rate expressed in beats per minute (bpm); in BIDMC records it comes from the ECG-derived HR channel.",
        "why_it_matters": "Provides an orientative view of physical effort, post-activity recovery, and sustained variations from a personal baseline.",
        "what_to_do": "Always interpret together with declared activity (rest, exercise, or recovery), check sensor contact, and observe the trend.",
        "limitations": "It varies by person, posture, stress, and movement; a value outside the demo threshold is a guidance hypothesis (simulated scenario), not a diagnosis.",
    },
    "rr": {
        "what_is": "Respiratory rate measured in breaths per minute (resp/min).",
        "why_it_matters": "Adds context to pulse to help distinguish an expected exercise response from changes associated with the cabin environment.",
        "what_to_do": "Compare the reading with cabin CO₂ and the current activity phase; review the sensor if abrupt jumps or signal gaps appear.",
        "limitations": "Sensitive to motion or speech artifacts; in historical BIDMC replays it lacks spatial context and CO₂.",
    },
    "co2": {
        "what_is": "Carbon dioxide partial pressure (ppCO₂) in the occupied cabin or module, measured in mmHg.",
        "why_it_matters": "In closed habitats without natural convection CO₂ can accumulate around the crew; the 1 h average of 3.0 mmHg (NASA OCHMO-TB-004) is used as an operational project reference, with headache symptoms reported from 2.3 mmHg.",
        "what_to_do": "Check cabin ventilation and scrubbers, compare with respiratory rate, reduce physical load in the simulation, and log an observation.",
        "limitations": "If a source provides ppm, known total pressure is required to convert to mmHg; an instantaneous reading is not the same as the 1 h average and is not a medical diagnosis.",
    },
    "dose_rate": {
        "what_is": "Instantaneous environmental equivalent dose rate read by the simulated dosimeter, in microsieverts per hour (μSv/h).",
        "why_it_matters": "Helps monitor simulated exposures during solar storm scenarios and integrate accumulated dose (μSv) over valid intervals.",
        "what_to_do": "Evaluate separately from physiological signals; in the simulated solar scenario, activate the demo shelter and check integration coverage.",
        "limitations": "It is a simulated source independent of the historical DONKI event; it does not model real shielding, particle propagation, or biological effects.",
    },
    "spo2": {
        "what_is": "Peripheral oxygen saturation estimated by pulse oximetry, in percent (%).",
        "why_it_matters": "Provides an orientative reference for oxygen delivery in compatible records and informational system displays.",
        "what_to_do": "Check oximeter fit, peripheral temperature, and simulated oxygen supply state when the source provides this channel.",
        "limitations": "Sensitive to movement, low perfusion, or ambient light; in this version it is informational and does not feed forecast or classification models.",
    },
    "bp_sys": {
        "what_is": "Estimated systolic blood pressure in millimeters of mercury (mmHg), corresponding to the peak pressure of the cardiac cycle.",
        "why_it_matters": "Provides context for cardiovascular and fluid-shift changes in educational space-adaptation exercises.",
        "what_to_do": "Record the measurement at stable rest and compare it with diastolic pressure and simulated hydration state.",
        "limitations": "Depends on posture and sensor used; it is not part of the minimum telemetry contract or current rules engine.",
    },
    "bp_dia": {
        "what_is": "Estimated diastolic blood pressure in millimeters of mercury (mmHg), corresponding to baseline pressure between beats.",
        "why_it_matters": "Complements systolic readings to track orientative hemodynamic behavior in demo scenarios.",
        "what_to_do": "Evaluate together with systolic pressure after pausing intense activity and note persistent changes for later review.",
        "limitations": "An isolated reading can fluctuate due to movement or sensor placement; it is strictly informational in this prototype.",
    },
    "temp_c": {
        "what_is": "Body or skin temperature estimated by a wearable sensor, expressed in degrees Celsius (°C).",
        "why_it_matters": "Provides orientative context about thermal load, suit or module regulation, and accumulated physical effort.",
        "what_to_do": "Check sensor thermal contact and simulated suit cooling state before interpreting deviations.",
        "limitations": "Skin temperature is not the same as core temperature and is influenced by suit microclimate or sensor shifts.",
    },
    "hydration_pct": {
        "what_is": "Orientative indicator of hydration state expressed as a percentage (%) within simulated scenarios.",
        "why_it_matters": "Serves as a reminder to monitor fluid balance during long shifts or sessions with thermal load and physical activity.",
        "what_to_do": "Compare with the simulated water-intake log and observe together with pulse and estimated pressures.",
        "limitations": "It is an illustrative simulation reference, not a real biochemical measurement; it does not feed automatic rules or ML models.",
    },
}

LEVEL_GLOSSARY: dict[str, dict[str, str]] = {
    "normal": {
        "label": "STABLE",
        "color": "#66e0bd",
        "meaning": "Guidance hypothesis (simulated scenario): available signals remain within demo margins for the declared activity.",
        "what_to_do": "Continue periodic monitoring and keep activity context up to date in the console.",
        "limitations": "Reflects only active channels in the recent window; it does not certify overall health status.",
    },
    "watch": {
        "label": "REVIEW",
        "color": "#ffca73",
        "meaning": "Guidance hypothesis (simulated scenario): one or more signals show a moderate variation relative to demo thresholds or personal reference.",
        "what_to_do": "Confirm current activity, check sensor fit, observe the trend over the next few minutes, and note context if it persists.",
        "limitations": "Thresholds are illustrative and may trigger due to posture changes, post-exercise transition, or measurement noise.",
    },
    "alert": {
        "label": "ATTENTION",
        "color": "#ff8d84",
        "meaning": "Guidance hypothesis (simulated scenario): readings exceed configured demo limits for cabin, dosimetry, or physiological response.",
        "what_to_do": "Review the shown evidence, check sensors, ventilation, or simulated shelter as applicable, acknowledge the notice, and log the observation.",
        "limitations": "Acknowledging the notice records that it was seen but does not resolve the condition; it is not a medical diagnosis or confirmation of a real incident.",
    },
    "unknown": {
        "label": "NO ASSESSMENT",
        "color": "#a4b2ca",
        "meaning": "Recent readings are missing, required signals are absent, activity is unknown, or the historical record lacks spatial context.",
        "what_to_do": "Check gateway connection, sensor quality, and activity context before interpreting the latest visible values.",
        "limitations": "Gaps are never filled with zeros; with insufficient coverage or stale data, the system abstains from assessment.",
    },
}


def get_glossary() -> dict[str, Any]:
    """Return the full glossary of orientative signals and levels."""
    return {
        "signals": {key: dict(entry) for key, entry in SIGNAL_GLOSSARY.items()},
        "levels": {key: dict(entry) for key, entry in LEVEL_GLOSSARY.items()},
    }
