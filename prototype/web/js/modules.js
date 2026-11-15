/* =========================================================
   ASTRA HEALTH · DRAWER MODULES
   Builds the HTML for each module from:
     · state / D        → live telemetry and severity
     · backend.cache    → astronaut, history, alerts,
                          logbook and insights (API + SQLite)
   ========================================================= */
"use strict";

const D = {};                       // severity shown per metric (0/1/2 or null)
const eventLog = [];                // local console log (not published)
const ui = {
    mood: null,                     // mood self-report: good | ok | bad
    histRange: "24h",
    histMetric: "hr",
    fx: { scan: true, glow: true, flicker: false },
    alerts: {
        enabled: true,
        sound: true,
        priority: "alta",           // critica | alta | todas
        methods: { screen: true, log: true, haptic: false, earth: true }
    },
    mission: {
        name: "ARTEMIS-SIM",
        id: "AST-MSN-042",
        duration: "180",
        sync: "auto",               // auto | manual | earth
        link: "nominal"             // nominal | reducido | contingencia
    },
    rxn: {
        phase: "idle",              // idle | waiting | go | false_start | between | done
        totalTrials: 6,
        trial: 0,
        times: [],
        falseStarts: 0,
        lapses: 0,
        goAt: 0,
        timerId: null,
        sleepHours: 7.5,
        moodScore: 3,
        submitting: false,
        lastResult: null,
        error: null
    },
    reportOpen: false,
    reportLoading: false,
    reportError: null
};

const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const isMissingSev = sev => sev === null || sev === undefined || !Number.isFinite(sev);
const sevColor = sev => isMissingSev(sev)
    ? "var(--amber-glow)"
    : (["var(--green-glow)", "var(--amber-glow)", "var(--red-glow)"][sev] || "var(--amber-glow)");
const sevLabel = sev => isMissingSev(sev) ? SEV_MISSING : (SEV_LABEL[sev] || SEV_MISSING);
const sevStatusKey = sev => isMissingSev(sev) ? "warn" : (SEV_KEY[sev] || "warn");
const sevStyle = sev => `style="--c:${sevColor(sev)}"`;
const segVal = (value, unit = "", cls = "") =>
    `<span class="seg-readout"><span class="seg ${cls}">${value}</span>${unit ? `<span class="seg-unit">${unit}</span>` : ""}</span>`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const pct = (v, lo, hi) => clamp((v - lo) / (hi - lo) * 100, 0, 100);
const sanitizeNonClinical = text => String(text ?? "")
    .replace(/\[IA\s*PREDICTION\]\s*:?\s*/gi, "Indicative hypothesis (simulated scenario): ")
    .trim();

function medianReactionMs(times) {
    if (!Array.isArray(times) || times.length === 0) return null;
    const sorted = times.filter(isNum).slice().sort((a, b) => a - b);
    if (sorted.length === 0) return null;
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 !== 0
        ? Math.round(sorted[mid])
        : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

function asFiniteOrNull(val) {
    if (val === null || val === undefined || val === "" || typeof val === "boolean") return null;
    const n = Number(val);
    return Number.isFinite(n) ? n : null;
}

function extractOnboardInsights() {
    const ob = (backend.cache.onboard && typeof backend.cache.onboard === "object") ? backend.cache.onboard : {};
    const ctrl = (backend.cache.control && typeof backend.cache.control === "object") ? backend.cache.control : {};
    const assessment = (ob.assessment && typeof ob.assessment === "object") ? ob.assessment : {};
    const ml = (ob.ml && typeof ob.ml === "object") ? ob.ml : {};
    const proj = (ob.projections && typeof ob.projections === "object") ? ob.projections : {};
    const baseline = (ob.baseline && typeof ob.baseline === "object") ? ob.baseline : {};

    const levelRaw = String(assessment.level || "unknown").toLowerCase();
    const levelSev = levelRaw === "alert" ? 2 : levelRaw === "watch" ? 1 : levelRaw === "normal" ? 0 : null;
    const levelText = levelRaw === "alert" ? "ALERT" : levelRaw === "watch" ? "CAUTION" : levelRaw === "normal" ? "NOMINAL" : "UNDER OBSERVATION";

    const patternObj = (ob.pattern && typeof ob.pattern === "object")
        ? ob.pattern
        : (ml.pattern && typeof ml.pattern === "object"
            ? ml.pattern
            : (assessment.pattern && typeof assessment.pattern === "object" ? assessment.pattern : null));

    const rawHypothesis = assessment.hypothesis
        || patternObj?.hypothesis_text
        || assessment.title
        || "Waiting for telemetry and onboard assessment";
    const hypothesis = sanitizeNonClinical(rawHypothesis);

    const evidence = Array.isArray(assessment.evidence)
        ? assessment.evidence.map(e => sanitizeNonClinical(e)).filter(Boolean)
        : [];
    const nextStep = assessment.next_step ? sanitizeNonClinical(assessment.next_step) : null;
    const assessmentMethod = assessment.method ? sanitizeNonClinical(assessment.method) : null;

    // HR forecast +60 s (ML vs persistence)
    const fObj = (ob.forecast && typeof ob.forecast === "object")
        ? ob.forecast
        : (ml.forecast && typeof ml.forecast === "object"
            ? ml.forecast
            : (assessment.forecast && typeof assessment.forecast === "object"
                ? assessment.forecast
                : (proj.forecast && typeof proj.forecast === "object" ? proj.forecast : null)));

    const forecastBpm = asFiniteOrNull(
        fObj
            ? (fObj.value_bpm ?? fObj.predicted_hr ?? fObj.hr_bpm ?? fObj.value ?? fObj.hr)
            : (assessment.forecast_hr ?? proj.forecast_hr)
    );
    const persistenceBpm = asFiniteOrNull(
        fObj?.persistence_bpm ?? fObj?.baseline_persistence_bpm ?? assessment.forecast_hr
    );
    const forecastMethod = sanitizeNonClinical(
        fObj?.method || fObj?.model_version || assessment.forecast_method || proj.forecast_method || "Waiting"
    );
    const forecastStatus = fObj?.status || (forecastBpm !== null ? "available" : "unavailable");
    const forecastReason = fObj?.reason ? sanitizeNonClinical(fObj.reason) : null;

    // CO2 sensitivity
    const sensObj = (ob.co2_sensitivity && typeof ob.co2_sensitivity === "object")
        ? ob.co2_sensitivity
        : (ob.sensitivity && typeof ob.sensitivity === "object"
            ? ob.sensitivity
            : (baseline.co2_sensitivity && typeof baseline.co2_sensitivity === "object"
                ? baseline.co2_sensitivity
                : (proj.co2_sensitivity && typeof proj.co2_sensitivity === "object" ? proj.co2_sensitivity : null)));
    const co2Slope = asFiniteOrNull(sensObj?.slope ?? sensObj?.s);
    const co2R2 = asFiniteOrNull(sensObj?.r2 ?? sensObj?.r_squared);
    const co2PersonalThreshold = asFiniteOrNull(
        sensObj?.personal_threshold_mmhg ?? sensObj?.co2_personal ?? sensObj?.threshold_mmhg
    );
    const co2SensStatus = sensObj?.status || null;
    const co2SensReason = sensObj?.reason || sensObj?.message || null;

    // Projections: CO2 ETA and dose with/without shelter
    const co2ProjObj = (proj.co2 && typeof proj.co2 === "object") ? proj.co2 : proj;
    let co2EtaMin = asFiniteOrNull(
        co2ProjObj.eta_minutes ?? co2ProjObj.eta_min ?? proj.co2_eta_minutes ?? proj.co2_eta_min ?? proj.eta_minutes
    );
    if (co2EtaMin === null) {
        const etaSec = asFiniteOrNull(co2ProjObj.eta_s ?? proj.co2_eta_s ?? proj.eta_s);
        if (etaSec !== null) co2EtaMin = etaSec / 60;
    }
    const co2EtaAssumption = co2ProjObj.assumption || proj.co2_assumption || null;
    const co2EtaReason = co2ProjObj.reason || proj.co2_reason || co2ProjObj.status || null;

    const radProjObj = (proj.radiation && typeof proj.radiation === "object")
        ? proj.radiation
        : ((proj.dose && typeof proj.dose === "object") ? proj.dose : proj);
    const doseWithoutShelter = asFiniteOrNull(
        radProjObj.projected_without_shelter ?? radProjObj.without_shelter ?? radProjObj.without_shelter_usv
    );
    const doseWithShelter = asFiniteOrNull(
        radProjObj.projected_with_shelter ?? radProjObj.with_shelter ?? radProjObj.with_shelter_usv
    );
    const doseHorizonH = asFiniteOrNull(radProjObj.horizon_hours ?? radProjObj.hours);
    const doseTotal = asFiniteOrNull(ob.dose_total);
    const doseComplete = ob.dose_complete;

    // External DONKI event
    const ext = (ob.external_event && typeof ob.external_event === "object") ? ob.external_event : null;

    // Coach / Routines
    const rCache = backend.cache.routines;
    const rObj = (rCache && !Array.isArray(rCache) && typeof rCache === "object") ? rCache : {};
    const cObj = (ob.coach && typeof ob.coach === "object") ? ob.coach : {};
    const routines = Array.isArray(rCache)
        ? rCache
        : (Array.isArray(rObj.routines) ? rObj.routines : (Array.isArray(cObj.routines) ? cObj.routines : []));
    const points = asFiniteOrNull(cObj.points ?? rObj.points) ?? 0;
    const streak = asFiniteOrNull(cObj.streak ?? rObj.streak) ?? 0;
    const badges = Array.isArray(cObj.badges) ? cObj.badges : (Array.isArray(rObj.badges) ? rObj.badges : []);
    const scoringPolicy = cObj.scoring_policy || rObj.scoring_policy
        || "Points are awarded only for participation, never for physiological results or speed.";
    const demoTimeLabel = cObj.demo_time_label || rObj.demo_time_label || "Demo interval";
    const latestCheckin = cObj.latest_checkin || rObj.latest_checkin || null;
    const reactionBaselineMs = asFiniteOrNull(cObj.reaction_baseline_ms ?? rObj.reaction_baseline_ms);

    const shareBehavioral = Boolean(
        backend.cache.privacy?.share_behavioral ?? ob.privacy?.share_behavioral ?? false
    );

    const envRaw = ctrl.environment ?? ob.environment;
    const environment = typeof envRaw === "object" && envRaw
        ? (envRaw.name || envRaw.id || "station")
        : (envRaw || "station");

    return {
        hasOnboard: Boolean(backend.cache.onboard),
        levelRaw,
        levelSev,
        levelText,
        hypothesis,
        patternText: patternObj ? sanitizeNonClinical(patternObj.hypothesis_text || patternObj.label || patternObj.status || "") : null,
        patternReason: patternObj?.reason ? sanitizeNonClinical(patternObj.reason) : null,
        evidence,
        nextStep,
        assessmentMethod,
        forecast: {
            valueBpm: forecastBpm,
            persistenceBpm,
            method: forecastMethod,
            status: forecastStatus,
            reason: forecastReason,
            targetTime: fObj?.target_time || null
        },
        co2Sensitivity: {
            slope: co2Slope,
            r2: co2R2,
            thresholdMmhg: co2PersonalThreshold,
            status: co2SensStatus,
            reason: co2SensReason ? sanitizeNonClinical(co2SensReason) : null
        },
        projections: {
            co2EtaMin,
            co2EtaAssumption: co2EtaAssumption ? sanitizeNonClinical(co2EtaAssumption) : null,
            co2EtaReason: co2EtaReason ? sanitizeNonClinical(co2EtaReason) : null,
            doseWithoutShelter,
            doseWithShelter,
            doseHorizonH,
            doseTotal,
            doseComplete
        },
        externalEvent: ext,
        coach: {
            points,
            streak,
            badges,
            routines,
            scoringPolicy,
            demoTimeLabel,
            latestCheckin,
            reactionBaselineMs
        },
        privacy: { shareBehavioral },
        environment,
        shelter: Boolean(ctrl.shelter)
    };
}

function nowTime() {
    return new Date().toLocaleTimeString("en-US", { hour12: false });
}

function logEvent(sev, text) {
    eventLog.unshift({ time: nowTime(), sev, text });
    if (eventLog.length > 40) eventLog.pop();
}

const sevFromApi = level => level === "critical" ? 2 : level === "warning" ? 1 : 0;

function fmtDateTime(value) {
    const date = parseTs(value);
    return date
        ? date.toLocaleString("en-US", { hour12: false })
        : "—";
}

function moduleHead(kicker, title, badgeHtml) {
    return `
        <div class="module-head">
            <div>
                <span class="module-kicker">${kicker}</span>
                <h3>${title}</h3>
            </div>
            ${badgeHtml}
        </div>`;
}

function emptyPanel(text) {
    return `
        <div class="monitor-panel" style="padding:10px">
            <p class="module-note" style="margin:0">${esc(text)}</p>
        </div>`;
}

/* ---------- HISTORY (API measurements) ---------- */
const HIST_RANGES = {
    "24h": { ms: 24 * 3600 * 1000, label: "24 H" },
    "7d":  { ms: 7 * 24 * 3600 * 1000, label: "7 DAYS" },
    "42d": { ms: 42 * 24 * 3600 * 1000, label: "MISSION" }
};

const HIST_METRICS = {
    hr:   { label: "HEART RATE", short: "HR",   unit: "BPM", lo: 50,   hi: 110, dec: 0, sev: v => RULES.hr(Math.round(v)) },
    spo2: { label: "SpO₂ SATURATION",     short: "SpO₂", unit: "%",   lo: 90,   hi: 100, dec: 1, sev: v => RULES.spo2(Math.round(v * 10) / 10) },
    temp: { label: "TEMPERATURE",         short: "TEMP", unit: "°C",  lo: 35.5, hi: 38,  dec: 1, sev: v => RULES.temp(Math.round(v * 10) / 10) }
};

function historySeries(metric) {
    const windowMs = HIST_RANGES[ui.histRange].ms;
    const now = Date.now();

    return (backend.cache.history || [])
        .map(item => ({ t: parseTs(item.timestamp), v: item[metric] }))
        .filter(item => isNum(item.v))
        .filter(item => !item.t || now - item.t.getTime() <= windowMs)
        .sort((a, b) => (a.t ? a.t.getTime() : 0) - (b.t ? b.t.getTime() : 0))
        .map(item => item.v);
}

function htmlHistory() {
    const M = HIST_METRICS[ui.histMetric];
    const data = historySeries(ui.histMetric);
    const shown = data.length > 60 ? data.slice(-60) : data;

    const rangeTabs = Object.keys(HIST_RANGES).map(k =>
        `<button type="button" class="tab-btn ${k === ui.histRange ? "is-on" : ""}" data-hist-range="${k}" aria-pressed="${k === ui.histRange}">${HIST_RANGES[k].label}</button>`).join("");
    const metricTabs = Object.keys(HIST_METRICS).map(k =>
        `<button type="button" class="tab-btn ${k === ui.histMetric ? "is-on" : ""}" data-hist-metric="${k}" aria-pressed="${k === ui.histMetric}">${HIST_METRICS[k].short}</button>`).join("");

    const tabs = `
        <div class="module-section-title"><span>TIME RANGE</span><span>${HIST_RANGES[ui.histRange].label}</span></div>
        <div class="tab-row" role="group" aria-label="Time range">${rangeTabs}</div>

        <div class="module-section-title"><span>PARAMETER</span><span>${data.length} SAMPLES</span></div>
        <div class="tab-row" role="group" aria-label="Parameter">${metricTabs}</div>`;

    if (shown.length === 0) {
        return moduleHead("02 / HISTORY", "History and baseline",
            `<span class="badge-status" ${sevStyle(1)}>NO DATA</span>`) +
            `<p class="module-intro">Trend of your parameters based on the measurements persisted in SQLite.</p>` +
            tabs +
            emptyPanel("There are no measurements of this parameter in the selected period. Change the range or record new measurements.") +
            `<p class="module-note">* History served by GET /api/measurements.</p>`;
    }

    const min = Math.min(...shown), max = Math.max(...shown);
    const avg = shown.reduce((a, b) => a + b, 0) / shown.length;
    const current = shown[shown.length - 1];
    const curSev = M.sev(current);
    const f = v => v.toFixed(M.dec);

    const bars = shown.map((v, i) => {
        const h = Math.max(4, pct(v, M.lo, M.hi));
        const last = i === shown.length - 1;
        return `<div class="hist-bar ${last ? "now" : ""}" style="height:${h.toFixed(1)}%;--c:${sevColor(M.sev(v))}" title="${last ? "Now" : "Sample " + (i + 1)}: ${f(v)} ${M.unit}"></div>`;
    }).join("");

    const baseBottom = pct(avg, M.lo, M.hi);

    const stats = [["MINIMUM", min], ["AVERAGE", avg], ["MAXIMUM", max], ["CURRENT", current]]
        .map(([label, v], i) => `
            <div class="stat-card" ${i === 3 ? sevStyle(curSev) : ""}>
                <span class="stat-label">${label}</span>
                ${segVal(f(v), M.unit, "seg-sm")}
            </div>`).join("");

    const delta = current - avg;
    const stable = Math.abs(delta) < (max - min) * 0.1;
    const trendLabel = stable ? "STABLE TREND" : delta > 0 ? "UPWARD TREND" : "DOWNWARD TREND";
    const trendText = stable
        ? `The current reading stays close to the period average (${f(avg)} ${M.unit}).`
        : `The current reading is ${Math.abs(delta).toFixed(M.dec)} ${M.unit} ${delta > 0 ? "above" : "below"} the period average.`;

    return moduleHead("02 / HISTORY", "History and baseline",
        `<span class="badge-status" ${sevStyle(curSev)}>${SEV_LABEL[curSev]}</span>`) +
        `<p class="module-intro">Trend of your parameters based on the measurements persisted in SQLite. The dotted line marks the period average.</p>` +
        tabs +
        `<div class="stat-grid">${stats}</div>

        <div class="monitor-panel" style="padding:8px">
            <div class="monitor-header"><span>${M.label}</span><span class="blue-text">● AVERAGE ${f(avg)} ${M.unit}</span></div>
            <div class="hist-chart">${bars}<div class="hist-base" style="bottom:calc(${baseBottom.toFixed(1)}% * .945)"></div></div>
            <div class="chart-legend"><span><i></i> CURRENT READING</span><span><i class="lg-base"></i> PERIOD AVERAGE</span></div>
        </div>

        <div class="trend-note" ${sevStyle(curSev)}>
            <b>${trendLabel}</b>
            <span>${trendText}</span>
        </div>
        <p class="module-note">* Last ${shown.length} of ${data.length} measurements in the period. Source: GET /api/measurements.</p>`;
}

function formatSbarMarkdown(report) {
    if (!report) return "";
    if (typeof report === "string") return sanitizeNonClinical(report);
    if (typeof report.markdown === "string" && report.markdown.trim()) {
        return sanitizeNonClinical(report.markdown);
    }
    const sit = report.situacion || report.situation || {};
    const ant = report.antecedentes || report.background || {};
    const ev = report.evaluacion || report.assessment || {};
    const rec = report.recomendacion || report.recommendation || {};
    return [
        "# Episode Report (SBAR)",
        "",
        "## 1. Situation",
        `- Level: ${sit.level ?? "--"}`,
        `- Title: ${sanitizeNonClinical(sit.title || "--")}`,
        `- Timestamp: ${sit.timestamp ?? "--"}`,
        "",
        "## 2. Background",
        `- Activity: ${ant.activity ?? "--"}`,
        `- Accumulated dose (μSv): ${ant.dose_total_usv ?? "--"}`,
        "",
        "## 3. Assessment",
        `- Indicative hypothesis (simulated scenario): ${sanitizeNonClinical(ev.hypothesis || "--")}`,
        "",
        "## 4. Recommendation",
        `- Next step (illustrative): ${sanitizeNonClinical(rec.next_step || "--")}`
    ].join("\n");
}

function htmlOnboardAndReportBlock() {
    const I = extractOnboardInsights();
    const report = backend.cache.report;

    const forecastStr = I.forecast.valueBpm !== null
        ? `${r0(I.forecast.valueBpm)} BPM`
        : "-- BPM";
    const persistStr = I.forecast.persistenceBpm !== null
        ? ` (persistence: ${r0(I.forecast.persistenceBpm)} BPM)`
        : "";
    const forecastDetail = `${I.forecast.method}${I.forecast.reason ? ` · ${I.forecast.reason}` : ""}`;

    let sensText = "Calibrating CO₂ sensitivity (requires sufficient variation and r² ≥ 0.6).";
    if (I.co2Sensitivity.slope !== null) {
        const r2Part = I.co2Sensitivity.r2 !== null ? ` · r² = ${I.co2Sensitivity.r2.toFixed(2)}` : "";
        const thrPart = I.co2Sensitivity.thresholdMmhg !== null
            ? ` · Estimated personal threshold: ${I.co2Sensitivity.thresholdMmhg.toFixed(2)} mmHg`
            : "";
        sensText = `Slope: +${I.co2Sensitivity.slope.toFixed(2)} br/min/mmHg${r2Part}${thrPart}`;
    } else if (I.co2Sensitivity.reason) {
        sensText = I.co2Sensitivity.reason;
    }

    const etaText = I.projections.co2EtaMin !== null
        ? `ETA to CO₂ limit: ~${I.projections.co2EtaMin.toFixed(1)} min${I.projections.co2EtaAssumption ? ` (${I.projections.co2EtaAssumption})` : ""}`
        : (I.projections.co2EtaReason || "CO₂ ETA: no projectable upward trend.");

    let radProjText = "Dose projection: no active rate or waiting for data.";
    if (I.projections.doseWithoutShelter !== null || I.projections.doseWithShelter !== null) {
        const horizon = I.projections.doseHorizonH !== null ? ` in ${I.projections.doseHorizonH} h` : "";
        const wo = I.projections.doseWithoutShelter !== null ? `${I.projections.doseWithoutShelter.toFixed(1)} µSv` : "--";
        const wi = I.projections.doseWithShelter !== null ? `${I.projections.doseWithShelter.toFixed(1)} µSv` : "--";
        radProjText = `Projected dose${horizon}: without shelter ${wo} · with shelter ${wi}`;
    }
    const doseAccText = I.projections.doseTotal !== null
        ? `Accumulated dose: ${I.projections.doseTotal.toFixed(2)} µSv${I.projections.doseComplete === false ? " (incomplete coverage)" : ""}`
        : "Accumulated dose: no complete reading";

    const extHtml = I.externalEvent
        ? `<div class="onboard-card" ${sevStyle(1)}>
            <small>EXTERNAL NASA DONKI EVENT · ${esc(String(I.externalEvent.phase || "ACTIVE").toUpperCase())}</small>
            <h4>${esc(sanitizeNonClinical(I.externalEvent.title || I.externalEvent.event_id || "Historical solar event"))}</h4>
            <p>${esc(sanitizeNonClinical(I.externalEvent.summary || I.externalEvent.note || "Historical solar storm context on the demonstration timeline."))}</p>
            ${I.externalEvent.start_time ? `<p><b>Historical date:</b> ${esc(I.externalEvent.start_time)}</p>` : ""}
           </div>`
        : "";

    const reportMd = report ? formatSbarMarkdown(report) : "";
    const reportPreview = (ui.reportOpen && report)
        ? `<div class="sbar-preview"><pre>${esc(reportMd)}</pre></div>`
        : "";

    return `
        <div class="module-section-title"><span>ON-BOARD ASSESSMENT AND INDICATIVE HYPOTHESIS</span><span>/api/v1/state</span></div>
        <div class="onboard-card" ${sevStyle(I.levelSev)}>
            <small>INDICATIVE HYPOTHESIS (SIMULATED SCENARIO) · ${esc(I.levelText)}</small>
            <h4>${esc(I.hypothesis)}</h4>
            ${I.patternText ? `<p><b>Simulated pattern:</b> ${esc(I.patternText)}${I.patternReason ? ` (${esc(I.patternReason)})` : ""}</p>` : ""}
            ${I.evidence.length ? `<ul>${I.evidence.slice(0, 4).map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}
            ${I.nextStep ? `<p style="margin-top:6px"><b>Suggested review:</b> ${esc(I.nextStep)}</p>` : ""}
            ${I.assessmentMethod ? `<p><small>${esc(I.assessmentMethod)}</small></p>` : ""}
        </div>

        <div class="onboard-card" ${sevStyle(I.forecast.valueBpm !== null ? 0 : null)}>
            <small>HR FORECAST +60 s · ML VS PERSISTENCE</small>
            <h4>${esc(forecastStr)}${esc(persistStr)}</h4>
            <p>${esc(forecastDetail)}</p>
        </div>

        <div class="onboard-card" ${sevStyle(I.co2Sensitivity.slope !== null ? 0 : null)}>
            <small>CO₂ SENSITIVITY AND PROJECTIONS (ETA / SHELTER)</small>
            <p>${esc(sensText)}</p>
            <p>${esc(etaText)}</p>
            <p>${esc(radProjText)}</p>
            <p>${esc(doseAccText)}</p>
        </div>

        ${extHtml}

        <div class="module-section-title"><span>SBAR EPISODE REPORT</span><span>${I.privacy.shareBehavioral ? "WITH BEHAVIORAL" : "ON-BOARD ONLY"}</span></div>
        <div class="sbar-actions">
            <button type="button" class="hw-btn" id="btn-view-report">${ui.reportLoading ? "LOADING..." : (ui.reportOpen ? "REFRESH SBAR VIEW" : "LOAD SBAR VIEW")}</button>
            <button type="button" class="hw-btn" id="btn-download-report">DOWNLOAD SBAR (.MD)</button>
        </div>
        ${ui.reportError ? `<p class="module-note" style="color:var(--amber-glow)">${esc(ui.reportError)}</p>` : ""}
        ${reportPreview}`;
}

/* ---------- MONITORING ---------- */
function htmlMonitoring() {
    const groups = [
        ["VITAL SIGNS", [
            ["hr", "HEART RATE", "BPM", () => isNum(state.hr) ? r0(state.hr) : "--"],
            ["bp", "BLOOD PRESSURE", "mmHg", () => (isNum(state.sys) && isNum(state.dia)) ? `${r0(state.sys)}/${r0(state.dia)}` : "--/--"],
            ["spo2", "SpO₂ SATURATION", "%", () => isNum(state.spo2) ? r1(state.spo2).toFixed(1) : "--"],
            ["temp", "BODY TEMPERATURE", "°C", () => isNum(state.temp) ? r1(state.temp).toFixed(1) : "--"]
        ]],
        ["BREATHING AND ENVIRONMENT", [
            ["rr", "RESPIRATORY RATE", "br/min", () => isNum(state.rr) ? r0(state.rr) : "--"],
            ["co2", "AMBIENT ppCO₂", "mmHg", () => isNum(state.co2) ? r1(state.co2).toFixed(1) : "--"],
            ["dose", "DOSE RATE", "µSv/h", () => isNum(state.dose) ? r0(state.dose) : "--"]
        ]],
        ["RECOVERY", [
            ["hyd", "HYDRATION", "%", () => isNum(state.hyd) ? r0(state.hyd) : "--"],
            ["fat", "ACCUMULATED FATIGUE", "/100", () => isNum(state.fat) ? r0(state.fat) : "--"],
            ["cm", "COUNTERMEASURES", "%", () => isNum(state.cm) ? r0(state.cm) : "--"]
        ]]
    ];

    const validSevs = Object.keys(METRIC_INFO).map(k => D[k]).filter(isNum);
    const worst = !state.ready ? null : (validSevs.length ? Math.max(...validSevs) : null);

    const body = state.ready
        ? groups.map(([title, rows]) => `
            <div class="module-section-title"><span>${title}</span><span>TELEMETRY</span></div>
            <div class="metric-list">
                ${rows.map(([k, label, unit, val]) => {
                    const sev = D[k];
                    return `
                        <div class="metric-line" ${sevStyle(sev)}>
                            <div class="ml-label">
                                <b>${label}</b>
                                <small>${sevLabel(sev)} · READING #${state.measurementId ?? "--"}</small>
                            </div>
                            <div class="ml-value">${segVal(val(), unit)}</div>
                        </div>`;
                }).join("")}
            </div>`).join("")
        : emptyPanel("There is no live telemetry yet. The indicators will show values once the first sample arrives.");

    return moduleHead("01 / MONITORING", "Real-time monitoring",
        `<span class="badge-status" ${sevStyle(worst)}>${state.ready ? sevLabel(worst) : "NO DATA"}</span>`) +
        `<p class="module-intro">Physiological and environmental indicators of the crew member. Channels with no reading show "--" and ${SEV_MISSING} without being replaced by zero.</p>` +
        body +
        htmlOnboardAndReportBlock() +
        `<p class="module-note">* Source: ${esc(state.source || "--")} · ${esc(fmtDateTime(state.timestamp))}.</p>`;
}

/* ---------- ALERTS AND JOURNAL ---------- */
function htmlAlerts() {
    const derived = Object.keys(METRIC_INFO)
        .filter(k => isNum(D[k]) && D[k] > 0)
        .sort((a, b) => D[b] - D[a]);
    const missingCount = Object.keys(METRIC_INFO).filter(k => !isNum(D[k])).length;

    const dbAlerts = backend.cache.alerts || [];
    const logs = backend.cache.logs || [];
    const I = extractOnboardInsights();

    const derivedCards = state.ready
        ? (derived.length
            ? derived.map(k => `
                <div class="alert-card" ${sevStyle(D[k])}>
                    <small>${SEV_LABEL[D[k]]} — ${METRIC_INFO[k].label}</small>
                    <h4>${METRIC_INFO[k].fmt()}</h4>
                    <p>${esc(METRIC_INFO[k].cause())}</p>
                    <p><b>Suggested action:</b> ${esc(METRIC_INFO[k].action())}</p>
                </div>`).join("")
            : (missingCount === Object.keys(METRIC_INFO).length
                ? emptyPanel("All signals are at NO SIGNAL (--). No false alarms are issued and none are evaluated as nominal.")
                : `<div class="alert-card" ${sevStyle(0)}><small>INFORMATION</small><h4>NO ALERTS ON ACTIVE CHANNELS</h4><p>${missingCount ? `${missingCount} channels with no reading (--). ` : ""}Active channels are within the demonstration range.</p></div>`))
        : emptyPanel("No telemetry: alerts cannot be evaluated.");

    const dbCards = dbAlerts.length
        ? dbAlerts.map(a => {
            const sev = sevFromApi(a.severity);
            return `
                <div class="alert-card" ${sevStyle(sev)}>
                    <small>${SEV_LABEL[sev]} — ${esc(a.metric)}${a.zone ? " · " + esc(a.zone).toUpperCase() : ""}</small>
                    <h4>${esc(sanitizeNonClinical(a.message))}</h4>
                    <p>${esc(sanitizeNonClinical(a.suggested_action || "No suggested action recorded."))}</p>
                    <p><b>Recorded:</b> ${esc(fmtDateTime(a.created_at))} · ${a.acknowledged ? "ACKNOWLEDGED" : "PENDING"}</p>
                    ${a.acknowledged ? "" : `<button class="hw-btn" type="button" data-ack-alert="${a.id}">ACKNOWLEDGE</button>`}
                </div>`;
        }).join("")
        : emptyPanel("There are no alerts recorded by the API.");

    const logItems = logs.length
        ? logs.slice(0, 14).map(l => `<li><time>${esc(fmtDateTime(l.timestamp))}</time>${esc(l.zone)} — ${esc(l.action || "No action recorded")}</li>`).join("")
        : "<li>No entries in the journal.</li>";

    const worst = derived.length
        ? Math.max(...derived.map(k => D[k]))
        : (state.ready && missingCount === Object.keys(METRIC_INFO).length ? null : 0);

    const ackOnboardBtn = (I.levelRaw === "watch" || I.levelRaw === "alert")
        ? `<div style="margin-bottom:8px"><button class="hw-btn" type="button" data-ack-onboard="1">ACKNOWLEDGE ON-BOARD NOTICE (+5 PTS)</button></div>`
        : "";

    return moduleHead("03 / ALERTS", "Alerts and journal",
        `<span class="badge-status" ${sevStyle(worst)}>${derived.length ? `${derived.length} ACTIVE` : (worst === null ? SEV_MISSING : "NO ALERTS")}</span>`) +
        `${ui.alerts.enabled ? "" : `<div class="settings-status" ${sevStyle(1)}><span class="status-dot"></span><span>Notifications <b>SUSPENDED</b> from Settings. Alerts are still evaluated and recorded.</span></div>`}
        ${ackOnboardBtn}

        <div class="module-section-title"><span>ALERTS DERIVED FROM TELEMETRY</span><span>${derived.length}</span></div>
        ${derivedCards}

        ${htmlOnboardAndReportBlock()}

        <div class="module-section-title"><span>RECORDED ALERTS (API)</span><span>${dbAlerts.length}</span></div>
        ${dbCards}

        <div class="module-section-title"><span>JOURNAL</span><span>GET /api/logs</span></div>
        <ul class="log-list">${logItems}</ul>
        <p class="module-note">* Indicative demonstration suggestions. They do not constitute a clinical diagnosis.</p>`;
}

/* ---------- WELLBEING ---------- */
function wellbeingModel() {
    const fatValid = isNum(state.fat);
    const hydValid = isNum(state.hyd);
    const cmValid = isNum(state.cm);
    const hrValid = isNum(state.hr);
    const co2Valid = isNum(state.co2);
    const evaValid = isNum(state.evaLoad);

    const fat = fatValid
        ? (state.fat > 70 ? ["HIGH", 2] : state.fat >= 40 ? ["MODERATE", 1] : ["LOW", 0])
        : [SEV_MISSING, null];

    const moodPenalty = ui.mood === "bad" ? 25 : ui.mood === "ok" ? 10 : 0;
    const hasStressSignal = evaValid || hrValid || co2Valid;
    const stressScore = hasStressSignal
        ? (evaValid ? state.evaLoad * 0.4 : 0)
            + (hrValid ? Math.max(0, state.hr - 80) * 0.8 : 0)
            + (co2Valid ? Math.max(0, state.co2 - 2.5) * 8 : 0)
            + moodPenalty
        : null;
    const stress = stressScore === null
        ? [SEV_MISSING, null]
        : (stressScore < 25 ? ["LOW", 0] : stressScore < 50 ? ["MODERATE", 1] : ["HIGH", 2]);

    const hasWellbeingSignals = fatValid || hydValid || cmValid;
    let score = null;
    if (hasWellbeingSignals) {
        const fatPenalty = fatValid ? state.fat * 0.25 : 0;
        const stressPenalty = stressScore !== null ? stressScore * 0.3 : 0;
        const hydPenalty = hydValid ? (100 - state.hyd) * 0.2 : 0;
        const cmPenalty = cmValid ? (100 - state.cm) * 0.15 : 0;
        score = Math.round(clamp(100 - fatPenalty - stressPenalty - hydPenalty - cmPenalty, 0, 100));
    }
    const scoreSev = score === null ? null : (score >= 75 ? 0 : score >= 55 ? 1 : 2);

    const exercise = cmValid
        ? Math.round(clamp(state.cm * 0.72 - (evaValid ? state.evaLoad : 0) * 0.06, 0, 120))
        : null;
    const exerciseSev = exercise === null ? null : (exercise >= 45 ? 0 : exercise >= 25 ? 1 : 2);

    const sleep = (fatValid && hrValid)
        ? clamp(8.4 - state.fat * 0.028 - Math.max(0, state.hr - 80) * 0.008, 4.5, 9)
        : null;
    const sleepSev = sleep === null ? null : (sleep >= 7 ? 0 : sleep >= 6 ? 1 : 2);

    const water = hydValid ? clamp(1.4 + state.hyd / 100 * 1.6, 1.2, 3.4) : null;
    const hydSev = hydValid ? RULES.hyd(r0(state.hyd)) : null;

    const kcal = (cmValid && fatValid)
        ? Math.round((1850 + state.cm * 4.2 - state.fat * 2.1) / 10) * 10
        : null;

    const mood = { good: ["GOOD", 0], ok: ["FAIR", 1], bad: ["POOR", 2] }[ui.mood] || ["NO REPORT", 0];

    return {
        fat,
        stress,
        score,
        scoreSev,
        exercise,
        exerciseSev,
        sleep,
        sleepSev,
        water,
        kcal,
        hydSev,
        mood
    };
}

function htmlReactionGame() {
    const rx = ui.rxn;
    const med = medianReactionMs(rx.times);
    const phaseText = {
        idle: "PRESS «START TEST» TO BEGIN (6 ATTEMPTS)",
        waiting: "WAIT FOR THE GREEN SIGNAL...",
        go: "NOW! CLICK HERE",
        false_start: "FALSE START — WAITING...",
        between: "RECORDED — NEXT ATTEMPT...",
        done: `COMPLETED · MEDIAN ${med ?? "--"} ms`
    }[rx.phase] || "PRESS «START TEST»";

    const padClass = {
        waiting: "is-waiting",
        go: "is-go",
        false_start: "is-false",
        done: "is-done"
    }[rx.phase] || "";

    const padDisabled = (rx.phase === "idle" || rx.phase === "done" || rx.phase === "between") ? "disabled" : "";
    const submitDisabled = (rx.times.length === 0 || rx.phase !== "done" || rx.submitting) ? "disabled" : "";
    const running = ["waiting", "go", "false_start", "between"].includes(rx.phase);

    let resultHtml = "";
    if (rx.error) {
        resultHtml = `<div class="rxn-result" style="--c:var(--red-glow)">${esc(rx.error)}</div>`;
    } else if (rx.lastResult) {
        const r = rx.lastResult;
        const deltaStr = isNum(r.delta_ms) ? `${r.delta_ms >= 0 ? "+" : ""}${r.delta_ms} ms` : "--";
        resultHtml = `
            <div class="rxn-result" style="--c:${r.drift_detected ? "var(--amber-glow)" : "var(--green-glow)"}">
                <b>Check-in recorded (+${r.points_awarded ?? 15} pts for participation)</b>
                <p style="margin:4px 0 0">Median: <b>${r.median_ms ?? med ?? "--"} ms</b> · Baseline: ${r.baseline_ms ?? "--"} ms · Delta: ${deltaStr} · Lapses: ${r.lapses ?? 0} · False starts: ${r.false_starts ?? 0}</p>
                <p style="margin:4px 0 0">${esc(sanitizeNonClinical(r.interpretation || "Indicative hypothesis (simulated scenario): behavioral follow-up recorded."))}</p>
            </div>`;
    }

    return `
        <div class="module-section-title"><span>BEHAVIORAL CHECK-IN · REACTION MINI-GAME</span><span>POST /api/v1/checkin</span></div>
        <div class="rxn-panel">
            <p style="margin:0 0 6px;font-size:11px;color:var(--muted)">Short psychomotor vigilance test (6 attempts with a random wait of 1.0–3.5 s). Indicative in-browser measurement; not a diagnosis.</p>
            <div class="rxn-stats">
                <div>ATTEMPT<b id="rxn-stat-trial">${rx.trial} / ${rx.totalTrials}</b></div>
                <div>CURRENT MEDIAN<b id="rxn-stat-med">${med !== null ? `${med} ms` : "-- ms"}</b></div>
                <div>FALSE STARTS<b id="rxn-stat-false">${rx.falseStarts}</b></div>
                <div>LAPSES (&gt;500 ms)<b id="rxn-stat-lapses">${rx.lapses}</b></div>
            </div>
            <button type="button" class="rxn-pad ${padClass}" id="rxn-pad" ${padDisabled}>${phaseText}</button>
            <div class="rxn-form">
                <label class="field-row" style="border:0;padding:0">
                    <span class="field-label">HOURS OF SLEEP</span>
                    <input type="number" id="rxn-sleep" class="hw-input" min="0" max="24" step="0.5" value="${esc(rx.sleepHours)}">
                </label>
                <label class="field-row" style="border:0;padding:0">
                    <span class="field-label">MOOD / ALERTNESS (1-5)</span>
                    <select id="rxn-mood" class="hw-select">
                        ${[1, 2, 3, 4, 5].map(v => `<option value="${v}" ${Number(rx.moodScore) === v ? "selected" : ""}>${v} - ${["Very low", "Low", "Moderate", "Good", "Optimal"][v - 1]}</option>`).join("")}
                    </select>
                </label>
            </div>
            <div class="rxn-actions">
                <button type="button" class="hw-btn" id="rxn-start">${running ? "RESTART TEST" : "START TEST (6 ATTEMPTS)"}</button>
                <button type="button" class="hw-btn" id="rxn-submit" ${submitDisabled}>${rx.submitting ? "SENDING..." : "SUBMIT CHECK-IN"}</button>
            </div>
            ${resultHtml}
        </div>`;
}

function htmlRoutinesAndPrivacy(I) {
    const c = I.coach;
    const badgesHtml = c.badges.length
        ? `<div class="badge-row">${c.badges.map(b => `<span class="badge-chip">★ ${esc(String(b).toUpperCase())}</span>`).join("")}</div>`
        : `<p class="module-note" style="margin:4px 0">Complete routines or check-ins to unlock participation badges.</p>`;

    const routinesHtml = c.routines.length
        ? `<div class="routine-list">${c.routines.map(r => {
            const isDue = Boolean(r.due);
            const active = r.active !== false;
            return `
                <div class="routine-item ${isDue ? "is-due" : ""}">
                    <div class="routine-copy">
                        <b>${esc(r.title || r.id)} ${isDue ? "· DUE" : (active ? "· UP TO DATE" : "· INACTIVE")}</b>
                        <small>${esc(r.description || "")} (Completed: ${r.completed_count ?? 0})</small>
                    </div>
                    <button type="button" class="hw-btn" data-complete-routine="${esc(r.id)}" ${active ? "" : "disabled"}>COMPLETE</button>
                </div>`;
        }).join("")}</div>`
        : emptyPanel("Loading routines from /api/v1/routines...");

    const share = I.privacy.shareBehavioral;
    const privacyLabel = share
        ? "Share summary in SBAR report"
        : "On-board only (default)";

    return `
        <div class="module-section-title"><span>ROUTINES AND PARTICIPATION</span><span>${c.points} PTS · STREAK ${c.streak}</span></div>
        <div class="coach-panel">
            <div class="coach-summary">
                <span>POINTS: ${c.points}</span>
                <span>STREAK: ${c.streak}</span>
                <span>RX BASELINE: ${c.reactionBaselineMs !== null ? `${c.reactionBaselineMs} ms` : "CALIBRATING"}</span>
            </div>
            <p class="module-note" style="margin:0 0 6px">${esc(c.scoringPolicy)} (${esc(c.demoTimeLabel)}).</p>
            ${badgesHtml}
            ${routinesHtml}
        </div>

        <div class="module-section-title"><span>BEHAVIORAL PRIVACY</span><span>POST /api/v1/privacy</span></div>
        <div class="privacy-panel">
            <label class="toggle-row">
                <span>Share summary in SBAR report</span>
                <input type="checkbox" class="hw-switch" data-privacy-toggle="1" ${share ? "checked" : ""}>
            </label>
            <div class="privacy-state">Current status: <b>${esc(privacyLabel)}</b></div>
            <p class="module-note" style="margin:4px 0 0">By default (off), sleep, mood and reaction times stay on board only.</p>
        </div>`;
}

function htmlWellbeing() {
    const W = wellbeingModel();
    const I = extractOnboardInsights();
    const insights = backend.cache.insights || [];

    const moods = [["good", "GOOD"], ["ok", "FAIR"], ["bad", "POOR"]].map(([id, label]) =>
        `<button type="button" class="hw-btn" data-mood="${id}" aria-pressed="${ui.mood === id}">${label}</button>`).join(" ");
    const bar = (value, max) => (isNum(value) ? Math.min(100, value / max * 100).toFixed(0) : "0");

    const insightCards = insights.length
        ? insights.slice(0, 6).map(i => {
            const sev = sevFromApi(i.risk_level);
            return `
                <div class="alert-card" ${sevStyle(sev)}>
                    <small>${SEV_LABEL[sev]} — ${esc(i.category).toUpperCase()}</small>
                    <h4>${esc(sanitizeNonClinical(i.description))}</h4>
                    <p><b>Recommendation:</b> ${esc(sanitizeNonClinical(i.recommendation))}</p>
                    <p><b>Generated:</b> ${esc(fmtDateTime(i.timestamp))}</p>
                </div>`;
        }).join("")
        : emptyPanel("The analysis engine has not published any insights yet.");

    return moduleHead("04 / WELLBEING", "Wellbeing and rest",
        `<span class="badge-status" ${sevStyle(W.scoreSev)}>${sevLabel(W.scoreSev)}</span>`) +
        `<p class="module-intro">Indicative tracking of habits, behavioral reaction check-in and participation routines. Missing signals show "--" and ${SEV_MISSING}.</p>

        <div class="wb-score" ${sevStyle(W.scoreSev)}>
            ${segVal(W.score !== null ? W.score : "--", "/ 100", "seg-lg")}
            <div class="wb-score-copy">
                <strong>OVERALL WELLBEING INDEX</strong>
                <small>Estimated stress: ${W.stress[0]} · Fatigue: ${W.fat[0]} · Day ${backend.cache.astronaut?.mission_day ?? "--"}</small>
                <div class="seg-bar"><div class="seg-fill" style="width:${W.score !== null ? W.score : 0}%"></div></div>
            </div>
        </div>

        ${htmlReactionGame()}

        ${htmlRoutinesAndPrivacy(I)}

        <div class="module-section-title"><span>HABITS AND RECOVERY</span><span>TELEMETRY</span></div>
        <div class="wb-list">

            <article class="wb-card" ${sevStyle(W.exerciseSev)}>
                <div class="wb-top">
                    <span class="wb-index">01</span>
                    <div class="wb-label"><b>PHYSICAL ACTIVITY</b><small>Daily exercise time</small></div>
                    <div class="wb-value">${segVal(W.exercise !== null ? W.exercise : "--", "MIN")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.exercise, 60)}%"></div></div>
                <div class="wb-foot"><span>GOAL: 60 MIN / DAY</span><span>${W.exercise !== null ? `${Math.round(W.exercise / 60 * 100)}% COMPLETED` : SEV_MISSING}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.sleepSev)}>
                <div class="wb-top">
                    <span class="wb-index">02</span>
                    <div class="wb-label"><b>SLEEP AND REST</b><small>Estimated hours</small></div>
                    <div class="wb-value">${segVal(W.sleep !== null ? W.sleep.toFixed(1) : "--", "H")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.sleep, 9)}%"></div></div>
                <div class="wb-foot"><span>GOAL: 7 - 9 HOURS</span><span>${W.sleepSev === null ? SEV_MISSING : (W.sleepSev === 0 ? "ADEQUATE REST" : "INSUFFICIENT REST")}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.hydSev)}>
                <div class="wb-top">
                    <span class="wb-index">03</span>
                    <div class="wb-label"><b>HYDRATION AND NUTRITION</b><small>Daily intake</small></div>
                    <div class="wb-value">${segVal(W.water !== null ? W.water.toFixed(1) : "--", "L")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.water, 3.4)}%"></div></div>
                <div class="wb-foot"><span>WATER · GOAL 3.0 L</span><span>NUTRITION: ${W.kcal !== null ? `${W.kcal.toLocaleString("en-US")} KCAL` : "--"}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.fat[1])}>
                <div class="wb-top">
                    <span class="wb-index">04</span>
                    <div class="wb-label"><b>FATIGUE AND RECOVERY</b><small>Reported fatigue level</small></div>
                    <div class="wb-value">${segVal(isNum(state.fat) ? r0(state.fat) : "--", "/100")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${isNum(state.fat) ? clamp(r0(state.fat), 0, 100) : 0}%"></div></div>
                <div class="wb-foot"><span>LEVEL: ${W.fat[0]}</span><span>${isNum(state.fat) ? (state.fat > 70 ? "PRIORITY RECOVERY" : state.fat >= 40 ? "RECOVERY IN PROGRESS" : "ADEQUATE RECOVERY") : SEV_MISSING}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.mood[1])}>
                <div class="wb-top">
                    <span class="wb-index">05</span>
                    <div class="wb-label"><b>QUICK SELF-REPORT</b><small>Reported mood</small></div>
                    <div class="wb-value"><span class="wb-mood">${W.mood[0]}</span></div>
                </div>
                <div class="wb-moods" role="group" aria-label="Report mood">${moods}</div>
                <div class="wb-foot"><span>PERCEIVED STRESS: ${W.stress[0]}</span><span>ON-BOARD ONLY</span></div>
            </article>

        </div>

        <div class="module-section-title"><span>ASSISTED ANALYSIS</span><span>GET /api/insights</span></div>
        ${insightCards}

        <p class="module-note">* Indicative hypothesis (simulated scenario). Points and streaks are for participation only; not a diagnosis.</p>`;
}

/* ---------- PROFILE ---------- */
function htmlProfile() {
    const a = backend.cache.astronaut;

    if (!a) {
        return moduleHead("05 / PROFILE", "Crew member profile",
            `<span class="badge-status" ${sevStyle(1)}>NO DATA</span>`) +
            emptyPanel("There are no crew members registered in /api/astronauts.") +
            `<p class="module-note">* The record is served from the database.</p>`;
    }

    const validSevs = Object.keys(METRIC_INFO).map(k => D[k]).filter(isNum);
    const anyAlert = validSevs.some(v => v > 0);
    const worst = validSevs.length ? Math.max(...validSevs) : null;
    const medicalStatus = worst === null ? SEV_MISSING : (anyAlert ? "UNDER OBSERVATION" : "FIT FOR EVA (SIM)");
    const restriction = worst === null ? "PARTIAL SIGNALS / NO READING" : (anyAlert ? "INDICATIVE REVIEW REQUIRED" : "NO SIMULATED RESTRICTIONS");
    const missionName = esc(String(a.mission || "").toUpperCase()) || "—";
    const day = String(a.mission_day ?? "—").padStart(3, "0");

    const section = (title, rows) => `
        <section class="info-section">
            <div class="info-section-head"><h4>${title}</h4></div>
            <dl class="info-list">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
        </section>`;

    return `
        <div class="profile-hero">
            <div class="profile-photo" role="img" aria-label="Simulated photograph of the crew member">
                <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M20 25c0-8 5-14 12-14s12 6 12 14v7H20z" fill="rgba(0,255,102,.08)"/>
                    <rect x="24" y="22" width="16" height="10" rx="5" fill="rgba(0,225,255,.12)" stroke="#00e1ff" stroke-opacity=".6"/>
                    <path d="M14 60c1.7-11 9-17 18-17s16.3 6 18 17"/>
                    <path d="M25 45l7 6 7-6"/>
                    <path d="M32 12v-5M27 9h10"/>
                </svg>
                <span>SIM PHOTO</span>
            </div>
            <div class="profile-id">
                <span class="module-kicker">05 / PROFILE · ${esc(a.code)}</span>
                <h3>${esc(String(a.name).toUpperCase())}</h3>
                <p>${esc(a.role)} · ${missionName} · D${day}</p>
                <span class="badge-status" ${sevStyle(worst)}>${medicalStatus}</span>
            </div>
        </div>

        ${section("PERSONAL INFORMATION", [
            ["Astronaut code", esc(a.code)],
            ["Full name", esc(String(a.name).toUpperCase())],
            ["Age", `${a.age} YEARS`],
            ["Blood type", esc(a.blood_type)],
            ["Height", `${a.height_cm} CM`],
            ["Weight", `${a.weight_kg} KG`],
            ["Crew identifier", `CREW-${esc(a.code)}`]
        ])}

        ${section("MISSION INFORMATION", [
            ["Mission name", missionName],
            ["Assigned role", esc(String(a.role).toUpperCase())],
            ["Current mission day", `D${day}`],
            ["Participation status", "ACTIVE"]
        ])}

        ${section("MEDICAL INFORMATION", [
            ["Recorded status", esc(String(a.status).toUpperCase())],
            ["Medical restrictions", restriction],
            ["Record source", "GET /api/astronauts/" + a.id]
        ])}

        <p class="module-note">* Record served from the database. It contains no real medical data.</p>`;
}

/* ---------- SETTINGS ---------- */
const ALERT_PRIORITIES = {
    critica: { label: "CRITICAL", detail: "Red alerts only. Reduces the notification load to a minimum." },
    alta:    { label: "HIGH",    detail: "Red and amber alerts. Recommended during EVA operations." },
    todas:   { label: "ALL",   detail: "Includes nominal notices and gradual trend changes." }
};
const ALERT_METHODS = {
    screen: "SCREEN",
    log:    "JOURNAL",
    haptic: "VIBRATION",
    earth:  "EARTH LINK"
};
const SYNC_MODES = {
    auto:   { label: "AUTOMATIC · NTP", detail: "Syncs the mission clock with the console reference." },
    manual: { label: "MANUAL",           detail: "The mission clock is adjusted only from the local panel." },
    earth:  { label: "VIA EARTH LINK", detail: "Takes the time from the control station at each contact window." }
};
const LINK_MODES = {
    nominal:      { label: "NOMINAL LINK",   short: "NOMINAL",      sev: 0, state: "STABLE",      band: "X BAND",  latency: "1.2 s",  window: "3 H",      detail: "Full telemetry and two-way voice with the control center." },
    reducido:     { label: "REDUCED LINK",  short: "REDUCED",     sev: 1, state: "DEGRADED",    band: "S BAND",  latency: "6.5 s",  window: "45 MIN",   detail: "Essential telemetry only. Voice is reserved for contingencies." },
    contingencia: { label: "CONTINGENCY",     short: "CONTINGENCY", sev: 2, state: "EMERGENCY",   band: "UHF",      latency: "VARIABLE", window: "ON DEMAND", detail: "Emergency channel with voice and minimal telemetry. Requires CMO confirmation." }
};

function htmlSettings() {
    const fxToggle = (id, label, on) =>
        `<label class="toggle-row"><span>${label}</span><input type="checkbox" class="hw-switch" data-fx="${id}" ${on ? "checked" : ""}></label>`;
    const alertToggle = (id, label, on) =>
        `<label class="toggle-row"><span>${label}</span><input type="checkbox" class="hw-switch" data-alert="${id}" ${on ? "checked" : ""}></label>`;
    const priorityBtn = (key, info) =>
        `<button type="button" class="tab-btn ${ui.alerts.priority === key ? "is-on" : ""}" data-alert-priority="${key}" aria-pressed="${ui.alerts.priority === key}">${info.label}</button>`;
    const methodBtn = (key, label) => {
        const on = Boolean(ui.alerts.methods[key]);
        return `<button type="button" class="tab-btn ${on ? "is-on" : ""}" data-alert-method="${key}" aria-pressed="${on}">${label}</button>`;
    };
    const missionField = (key, label, value, type = "text", attrs = "") => `
        <label class="field-row">
            <span class="field-label">${label}</span>
            <input class="hw-input" type="${type}" data-mission="${key}" value="${esc(value)}" ${attrs}>
        </label>`;
    const linkBtn = (key, info) =>
        `<button type="button" class="tab-btn ${ui.mission.link === key ? "is-on" : ""}" data-mission-link="${key}" aria-pressed="${ui.mission.link === key}">${info.short}</button>`;

    const priority = ALERT_PRIORITIES[ui.alerts.priority] || ALERT_PRIORITIES.alta;
    const activeMethods = Object.keys(ALERT_METHODS).filter(k => ui.alerts.methods[k]).map(k => ALERT_METHODS[k]);
    const methodText = activeMethods.length ? activeMethods.join(" · ") : "NONE";
    const alertSev = ui.alerts.enabled ? 0 : 1;
    const link = LINK_MODES[ui.mission.link] || LINK_MODES.nominal;
    const sync = SYNC_MODES[ui.mission.sync] || SYNC_MODES.auto;
    const duration = Math.max(1, Math.min(3650, Math.round(Number(ui.mission.duration) || 1)));
    const day = String(backend.cache.astronaut?.mission_day ?? 42).padStart(3, "0");

    const alertNote = ui.alerts.enabled
        ? `Priority <b>${priority.label}</b> · Methods: <b>${methodText}</b>.`
        : `Notifications <b>SUSPENDED</b>. The configuration is kept and can be re-enabled at any time.`;
    const methodNote = activeMethods.length
        ? `You will be notified via: <b>${methodText}</b>.`
        : `No active methods: alerts will not be shown or recorded.`;

    return moduleHead("06 / SETTINGS", "System configuration",
        `<span class="badge-status" ${sevStyle(0)}>LOCAL</span>`) +
        `<p class="module-intro">Adjust the alert behavior and the console's operating parameters. The simulated biometric data are read from the API; this configuration is local.</p>

        <div class="module-section-title"><span>ALERT SETTINGS</span><span>${ui.alerts.enabled ? "ACTIVE" : "SUSPENDED"}</span></div>
        <div class="settings-panel">
            ${alertToggle("enabled", "Enable notifications", ui.alerts.enabled)}
            ${alertToggle("sound", "Alert sounds", ui.alerts.sound)}
            <div class="settings-label">NOTIFICATION PRIORITY</div>
            <div class="tab-row" role="group" aria-label="Notification priority">
                ${Object.keys(ALERT_PRIORITIES).map(k => priorityBtn(k, ALERT_PRIORITIES[k])).join("")}
            </div>
            <p class="settings-hint">${priority.detail}</p>
            <div class="settings-label">NOTIFICATION METHODS</div>
            <div class="method-grid" role="group" aria-label="Notification methods">
                ${Object.keys(ALERT_METHODS).map(k => methodBtn(k, ALERT_METHODS[k])).join("")}
            </div>
            <p class="settings-hint">${methodNote}</p>
            <div class="settings-status" ${sevStyle(alertSev)}>
                <span class="status-dot"></span>
                <span>${alertNote}</span>
            </div>
        </div>

        <div class="module-section-title"><span>MISSION SETTINGS</span><span>D${day} / ${duration} DAYS</span></div>
        <div class="settings-panel">
            ${missionField("name", "MISSION NAME", ui.mission.name, "text", 'autocomplete="off" spellcheck="false"')}
            ${missionField("id", "MISSION IDENTIFIER", ui.mission.id, "text", 'autocomplete="off" spellcheck="false"')}
            ${missionField("duration", "PLANNED DURATION (DAYS)", ui.mission.duration, "number", 'min="1" max="3650" step="1"')}
            <label class="field-row">
                <span class="field-label">TIME SYNCHRONIZATION</span>
                <select class="hw-select" data-mission="sync">
                    ${Object.keys(SYNC_MODES).map(k => `<option value="${k}" ${ui.mission.sync === k ? "selected" : ""}>${SYNC_MODES[k].label}</option>`).join("")}
                </select>
            </label>
            <p class="settings-hint">${sync.detail}</p>
            <div class="settings-readout">
                <span>CURRENT DAY / DURATION</span>
                <span class="seg-readout"><span class="seg seg-sm">${day}</span><span class="seg-unit">/ <span data-duration-out>${String(duration).padStart(3, "0")}</span> D</span></span>
            </div>
        </div>

        <div class="module-section-title"><span>EARTH LINK</span><span>${link.state}</span></div>
        <div class="tab-row" role="group" aria-label="Earth link settings">
            ${Object.keys(LINK_MODES).map(k => linkBtn(k, LINK_MODES[k])).join("")}
        </div>
        <div class="link-status" ${sevStyle(link.sev)}>
            <div class="link-status-head">
                <span class="status-dot"></span>
                <b>${link.label}</b>
                <span class="badge-status" ${sevStyle(link.sev)}>${link.state}</span>
            </div>
            <p>${link.detail}</p>
            <div class="link-meta"><span>${link.band}</span><span>LATENCY ${link.latency}</span><span>WINDOW ${link.window}</span></div>
        </div>

        <div class="module-section-title"><span>SCREEN EFFECTS</span><span>VISUAL</span></div>
        ${fxToggle("scan", "Scan lines", ui.fx.scan)}
        ${fxToggle("glow", "Neon glow", ui.fx.glow)}
        ${fxToggle("flicker", "CRT flicker", ui.fx.flicker)}

        <div class="module-section-title"><span>SYSTEM</span><span>v1.4.0</span></div>
        <div class="window-data">
            <div>VERSION: <strong>v1.4.0-API</strong></div>
            <div>STORAGE: <strong>SQLite · astra_health.db</strong></div>
            <div>TELEMETRY: <strong>REST + WebSocket</strong></div>
            <div>ACTIVE SCENARIO: <strong>${esc(String(state.scenario || "NO DATA").toUpperCase())}</strong></div>
        </div>
        <p class="module-note">* Local console configuration. The simulated indicators come from the API.</p>`;
}

const MODULES = {
    monitoring: { title: "BIOMETRIC MONITORING CENTER", html: htmlMonitoring, live: true },
    history:    { title: "HISTORY AND BASELINE",         html: htmlHistory,    live: false },
    alerts:     { title: "ALERTS AND JOURNAL",             html: htmlAlerts,     live: true },
    wellbeing:  { title: "WELLBEING AND REST",           html: htmlWellbeing,  live: true },
    profile:    { title: "CREW MEMBER PROFILE",          html: htmlProfile,    live: true },
    settings:   { title: "SYSTEM CONFIGURATION",      html: htmlSettings,   live: false }
};
