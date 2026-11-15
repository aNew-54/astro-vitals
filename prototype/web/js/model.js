/* =========================================================
   ASTRA HEALTH · MODEL (no DOM)
   Single state that is FILLED from the API (REST + WebSocket).
   No data is generated here: only severity is evaluated to
   color the interface, and metrics and zones are described.
   Severity: 0 = nominal · 1 = caution · 2 = alert.
   ALL thresholds are simulation-only (educational, non-clinical).
   ========================================================= */
"use strict";

const SEV_LABEL = ["NOMINAL", "CAUTION", "ALERT"];
const SEV_KEY = ["ok", "warn", "alert"];
const SEV_MISSING = "NO SIGNAL";

/* ---------- 1. SINGLE STATE (empty until the first reading) ---------- */
const state = {
    ready: false,
    measurementId: null,
    astronautId: null,
    timestamp: null,
    source: null,
    scenario: null,
    evaLoad: null,

    hr: null,
    sys: null,
    dia: null,
    spo2: null,
    temp: null,
    rr: null,
    co2: null,
    hyd: null,
    fat: null,
    cm: null,
    dose: null
};

const isNum = v => typeof v === "number" && Number.isFinite(v);

/* SQLite may return dates without a time zone: they are interpreted as UTC. */
function parseTs(value) {
    if (!value) return null;
    const text = String(value);
    const iso = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`;
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? null : date;
}

/* ---------- 2. SEVERITY RULES ---------- */
const RULES = {
    hr:   v => (v < 50 || v > 120) ? 2 : (v < 60 || v > 100) ? 1 : 0,
    bp:   (s, d) => (s >= 140 || d >= 90 || s < 90) ? 2 : (s >= 130 || d >= 85 || s < 100) ? 1 : 0,
    spo2: v => v < 90 ? 2 : v < 95 ? 1 : 0,
    temp: v => (v >= 38.5 || v < 35) ? 2 : (v >= 37.6 || v < 36) ? 1 : 0,
    rr:   v => (v > 25 || v < 9) ? 2 : (v > 20 || v < 12) ? 1 : 0,
    co2:  v => v > 5 ? 2 : v >= 3 ? 1 : 0,
    hyd:  v => v < 60 ? 2 : v < 75 ? 1 : 0,
    fat:  v => v > 70 ? 2 : v >= 40 ? 1 : 0,
    cm:   v => v < 50 ? 2 : v < 75 ? 1 : 0,
    dose: v => v > 150 ? 2 : v >= 60 ? 1 : 0
};

const r0 = v => Math.round(v);
const r1 = v => Math.round(v * 10) / 10;

/* Evaluates using the values as displayed (rounded). Returns null if the signal is missing. */
function evaluate() {
    const s = state;

    return {
        hr: isNum(s.hr) ? RULES.hr(r0(s.hr)) : null,
        bp: isNum(s.sys) && isNum(s.dia) ? RULES.bp(r0(s.sys), r0(s.dia)) : null,
        spo2: isNum(s.spo2) ? RULES.spo2(r1(s.spo2)) : null,
        temp: isNum(s.temp) ? RULES.temp(r1(s.temp)) : null,
        rr: isNum(s.rr) ? RULES.rr(r0(s.rr)) : null,
        co2: isNum(s.co2) ? RULES.co2(r1(s.co2)) : null,
        hyd: isNum(s.hyd) ? RULES.hyd(r0(s.hyd)) : null,
        fat: isNum(s.fat) ? RULES.fat(r0(s.fat)) : null,
        cm: isNum(s.cm) ? RULES.cm(r0(s.cm)) : null,
        dose: isNum(s.dose) ? RULES.dose(r0(s.dose)) : null
    };
}

const MISSING_MSG = "No reading available from the current source.";

/* ---------- 3. METRIC DESCRIPTIONS (value, probable cause, action) ---------- */
const METRIC_INFO = {
    hr: {
        label: "HEART RATE",
        fmt: () => isNum(state.hr) ? `${r0(state.hr)} BPM` : "--",
        cause: () => !isNum(state.hr)
            ? MISSING_MSG
            : state.hr > 100
                ? "Tachycardia: EVA exertion, thermal stress, dehydration or hypoxia."
                : "Unusually low rate: check sensor contact and extreme fatigue.",
        action: () => !isNum(state.hr)
            ? MISSING_MSG
            : state.hr > 100
                ? "Reduce workload, hydrate and check temperature and SpO₂; repeat the reading in 5 min."
                : "Check the sensor patch; if it persists, review the record and the activity context."
    },
    bp: {
        label: "BLOOD PRESSURE",
        fmt: () => isNum(state.sys) && isNum(state.dia) ? `${r0(state.sys)}/${r0(state.dia)} mmHg` : "--/--",
        cause: () => (!isNum(state.sys) || !isNum(state.dia))
            ? MISSING_MSG
            : state.sys < 100
                ? "Low pressure: possible dehydration or fluid shift."
                : "Elevated pressure: overexertion, dehydration, stress or fluid shifts in microgravity.",
        action: () => (!isNum(state.sys) || !isNum(state.dia))
            ? MISSING_MSG
            : state.sys < 100
                ? "Hydrate, rest while seated/anchored and measure again."
                : "Pause intense activity, breathe calmly and measure again in 10 min."
    },
    spo2: {
        label: "SpO₂",
        fmt: () => isNum(state.spo2) ? `${r1(state.spo2).toFixed(1)} %` : "--",
        cause: () => !isNum(state.spo2)
            ? MISSING_MSG
            : "Low saturation: possible mild hypoxia (check O₂ pressure/composition and helmet seal).",
        action: () => !isNum(state.spo2)
            ? MISSING_MSG
            : "Stop exertion, verify the O₂ supply and the helmet fit."
    },
    temp: {
        label: "BODY TEMPERATURE",
        fmt: () => isNum(state.temp) ? `${r1(state.temp).toFixed(1)} °C` : "--",
        cause: () => !isNum(state.temp)
            ? MISSING_MSG
            : state.temp < 36
                ? "Low temperature: heat loss from the suit or a poorly placed sensor."
                : "High temperature: thermal stress (suit cooling system) or environmental load.",
        action: () => !isNum(state.temp)
            ? MISSING_MSG
            : state.temp < 36
                ? "Check the suit insulation and heating; add layers."
                : "Check suit cooling, hydrate and repeat the reading."
    },
    rr: {
        label: "RESPIRATORY RATE",
        fmt: () => isNum(state.rr) ? `${r0(state.rr)} rpm` : "--",
        cause: () => !isNum(state.rr)
            ? MISSING_MSG
            : "Breathing out of range: associated with exertion, elevated CO₂ or hypoxia.",
        action: () => !isNum(state.rr)
            ? MISSING_MSG
            : "Reduce exertion and check ambient ppCO₂ and SpO₂."
    },
    co2: {
        label: "ppCO₂",
        fmt: () => isNum(state.co2) ? `${r1(state.co2).toFixed(1)} mmHg` : "--",
        cause: () => !isNum(state.co2)
            ? MISSING_MSG
            : "Elevated ambient CO₂: possible scrubber failure or saturation / poor ventilation.",
        action: () => !isNum(state.co2)
            ? MISSING_MSG
            : "Check the CO₂ scrubbers and airflow, reduce exertion and notify Mission Control."
    },
    hyd: {
        label: "HYDRATION",
        fmt: () => isNum(state.hyd) ? `${r0(state.hyd)} %` : "--",
        cause: () => !isNum(state.hyd)
            ? MISSING_MSG
            : "Insufficient hydration: water intake below protocol.",
        action: () => !isNum(state.hyd)
            ? MISSING_MSG
            : "Drink per protocol, check the suit water bag and log the intake."
    },
    fat: {
        label: "FATIGUE",
        fmt: () => isNum(state.fat) ? `${r0(state.fat)}/100` : "--",
        cause: () => !isNum(state.fat)
            ? MISSING_MSG
            : "Accumulated fatigue: high EVA load, insufficient rest or prolonged confinement.",
        action: () => !isNum(state.fat)
            ? MISSING_MSG
            : "Reduce load, schedule rest and adjust the task plan."
    },
    cm: {
        label: "COUNTERMEASURES",
        fmt: () => isNum(state.cm) ? `${r0(state.cm)} %` : "--",
        cause: () => !isNum(state.cm)
            ? MISSING_MSG
            : "Low resistance-exercise compliance: long-term risk of bone and muscle loss.",
        action: () => !isNum(state.cm)
            ? MISSING_MSG
            : "Reschedule the exercise session and log its compliance."
    },
    dose: {
        label: "DOSE RATE",
        fmt: () => isNum(state.dose) ? `${state.dose < 10 ? state.dose.toFixed(2) : r0(state.dose)} µSv/h` : "--",
        cause: () => !isNum(state.dose)
            ? MISSING_MSG
            : "Elevated dose rate: possible solar particle event (SPE).",
        action: () => !isNum(state.dose)
            ? MISSING_MSG
            : "Move to the most shielded area, limit external activity and notify Mission Control."
    }
};

/* ---------- 4. BODY ZONES (NASA reference risks) ---------- */
const ZONES = {
    head: {
        code: "01", name: "HEAD / EYES", metrics: ["co2", "spo2", "bp"],
        nasa: "SANS: the eye and brain can change in flight due to fluid shift. Also elevated CO₂ and isolation stress (mental health and performance)."
    },
    lungs: {
        code: "02", name: "LUNGS", metrics: ["spo2", "rr", "co2"],
        nasa: "Closed environment: air quality, CO₂ and safe oxygen thresholds; mild hypoxia is a risk NASA studies."
    },
    heart: {
        code: "03", name: "HEART", metrics: ["hr", "bp"],
        nasa: "Cardiovascular risk on long missions: adaptation to altered gravity, radiation and exertion during EVA."
    },
    abdomen: {
        code: "04", name: "ABDOMEN / CORE", metrics: ["hyd", "temp"],
        nasa: "Nutrition and fluid balance, thermoregulation and immune responses altered by flight stress."
    },
    arms: {
        code: "05", name: "ARMS AND HANDS", metrics: ["hr", "hyd", "fat"],
        nasa: "EVA exertion, suit load and upper-limb muscle fatigue."
    },
    spine: {
        code: "06", name: "SPINE AND HIPS", metrics: ["temp", "hyd", "cm", "fat"],
        nasa: "Altered gravity: bone loss and spinal changes; resistive exercise is the main countermeasure."
    },
    legs: {
        code: "07", name: "LEGS", metrics: ["bp", "hr", "cm", "fat"],
        nasa: "Muscle atrophy and fluid shift under altered gravity; exercise countermeasures are key."
    }
};

const RADIATION_NASA = "Space radiation: a high-priority risk for NASA (long-term effects such as cancer, cardiovascular disease and cognitive changes).";

/* Computes the severity, cause and action of each zone from S = evaluate(). */
function computeZones(S) {
    const out = {};
    const radFloor = S.dose === 2;
    Object.keys(ZONES).forEach(id => {
        const z = ZONES[id];
        const items = z.metrics.map(k => ({ k, sev: S[k] }));
        const valid = items.filter(i => i.sev !== null && isNum(i.sev));
        let sev = valid.length ? Math.max(...valid.map(i => i.sev)) : null;
        let primary = valid.length ? valid.slice().sort((a, b) => b.sev - a.sev)[0].k : null;
        let viaRadiation = false;
        if (radFloor && (sev === null || sev < 1)) {
            sev = 1;
            primary = "dose";
            viaRadiation = true;
        }
        out[id] = {
            id,
            sev,
            items,
            primary: sev !== null && sev > 0 ? primary : null,
            viaRadiation
        };
    });
    return out;
}

/* Zone with the highest severity (for the scanner's AUTO mode). */
function worstZone(zones) {
    let best = null;
    Object.keys(zones).forEach(id => {
        if (isNum(zones[id].sev) && zones[id].sev > 0 && (!best || zones[id].sev > best.sev)) {
            best = zones[id];
        }
    });
    return best;
}
