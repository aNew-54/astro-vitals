/* =========================================================
   ASTRA HEALTH · MÓDULOS DEL CAJÓN
   Genera el HTML de cada módulo a partir de:
     · state / D        → telemetría y severidad en vivo
     · backend.cache    → astronauta, historial, alertas,
                          bitácora e insights (API + SQLite)
   ========================================================= */
"use strict";

const D = {};                       // severidad mostrada por métrica (0/1/2 o null)
const eventLog = [];                // log local de la consola (no se publica)
const ui = {
    mood: null,                     // autoinforme de ánimo: good | ok | bad
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
    .replace(/\[IA\s*PREDICTION\]\s*:?\s*/gi, "Hipótesis orientativa (escenario simulado): ")
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
    const levelText = levelRaw === "alert" ? "ALERTA" : levelRaw === "watch" ? "PRECAUCIÓN" : levelRaw === "normal" ? "NOMINAL" : "EN OBSERVACIÓN";

    const patternObj = (ob.pattern && typeof ob.pattern === "object")
        ? ob.pattern
        : (ml.pattern && typeof ml.pattern === "object"
            ? ml.pattern
            : (assessment.pattern && typeof assessment.pattern === "object" ? assessment.pattern : null));

    const rawHypothesis = assessment.hypothesis
        || patternObj?.hypothesis_text
        || assessment.title
        || "Esperando telemetría y evaluación a bordo";
    const hypothesis = sanitizeNonClinical(rawHypothesis);

    const evidence = Array.isArray(assessment.evidence)
        ? assessment.evidence.map(e => sanitizeNonClinical(e)).filter(Boolean)
        : [];
    const nextStep = assessment.next_step ? sanitizeNonClinical(assessment.next_step) : null;
    const assessmentMethod = assessment.method ? sanitizeNonClinical(assessment.method) : null;

    // Pronóstico FC +60 s (ML vs persistencia)
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
        fObj?.method || fObj?.model_version || assessment.forecast_method || proj.forecast_method || "En espera"
    );
    const forecastStatus = fObj?.status || (forecastBpm !== null ? "available" : "unavailable");
    const forecastReason = fObj?.reason ? sanitizeNonClinical(fObj.reason) : null;

    // Sensibilidad CO2
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

    // Proyecciones: ETA CO2 y dosis con/sin refugio
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

    // Evento externo DONKI
    const ext = (ob.external_event && typeof ob.external_event === "object") ? ob.external_event : null;

    // Coach / Rutinas
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
        || "Puntos otorgados únicamente por participación, nunca por resultados fisiológicos o velocidad.";
    const demoTimeLabel = cObj.demo_time_label || rObj.demo_time_label || "Intervalo de demostración";
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
    return new Date().toLocaleTimeString("es-PE", { hour12: false });
}

function logEvent(sev, text) {
    eventLog.unshift({ time: nowTime(), sev, text });
    if (eventLog.length > 40) eventLog.pop();
}

const sevFromApi = level => level === "critical" ? 2 : level === "warning" ? 1 : 0;

function fmtDateTime(value) {
    const date = parseTs(value);
    return date
        ? date.toLocaleString("es-PE", { hour12: false })
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

/* ---------- HISTORIAL (mediciones de la API) ---------- */
const HIST_RANGES = {
    "24h": { ms: 24 * 3600 * 1000, label: "24 H" },
    "7d":  { ms: 7 * 24 * 3600 * 1000, label: "7 DÍAS" },
    "42d": { ms: 42 * 24 * 3600 * 1000, label: "MISIÓN" }
};

const HIST_METRICS = {
    hr:   { label: "FRECUENCIA CARDÍACA", short: "FC",   unit: "BPM", lo: 50,   hi: 110, dec: 0, sev: v => RULES.hr(Math.round(v)) },
    spo2: { label: "SATURACIÓN SpO₂",     short: "SpO₂", unit: "%",   lo: 90,   hi: 100, dec: 1, sev: v => RULES.spo2(Math.round(v * 10) / 10) },
    temp: { label: "TEMPERATURA",         short: "TEMP", unit: "°C",  lo: 35.5, hi: 38,  dec: 1, sev: v => RULES.temp(Math.round(v * 10) / 10) }
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
        <div class="module-section-title"><span>RANGO TEMPORAL</span><span>${HIST_RANGES[ui.histRange].label}</span></div>
        <div class="tab-row" role="group" aria-label="Rango temporal">${rangeTabs}</div>

        <div class="module-section-title"><span>PARÁMETRO</span><span>${data.length} MUESTRAS</span></div>
        <div class="tab-row" role="group" aria-label="Parámetro">${metricTabs}</div>`;

    if (shown.length === 0) {
        return moduleHead("02 / HISTORIAL", "Historial y línea base",
            `<span class="badge-status" ${sevStyle(1)}>SIN DATOS</span>`) +
            `<p class="module-intro">Evolución de tus parámetros según las mediciones persistidas en SQLite.</p>` +
            tabs +
            emptyPanel("No hay mediciones de este parámetro en el periodo seleccionado. Cambia el rango o registra nuevas mediciones.") +
            `<p class="module-note">* Historial servido por GET /api/measurements.</p>`;
    }

    const min = Math.min(...shown), max = Math.max(...shown);
    const avg = shown.reduce((a, b) => a + b, 0) / shown.length;
    const current = shown[shown.length - 1];
    const curSev = M.sev(current);
    const f = v => v.toFixed(M.dec);

    const bars = shown.map((v, i) => {
        const h = Math.max(4, pct(v, M.lo, M.hi));
        const last = i === shown.length - 1;
        return `<div class="hist-bar ${last ? "now" : ""}" style="height:${h.toFixed(1)}%;--c:${sevColor(M.sev(v))}" title="${last ? "Ahora" : "Muestra " + (i + 1)}: ${f(v)} ${M.unit}"></div>`;
    }).join("");

    const baseBottom = pct(avg, M.lo, M.hi);

    const stats = [["MÍNIMO", min], ["PROMEDIO", avg], ["MÁXIMO", max], ["ACTUAL", current]]
        .map(([label, v], i) => `
            <div class="stat-card" ${i === 3 ? sevStyle(curSev) : ""}>
                <span class="stat-label">${label}</span>
                ${segVal(f(v), M.unit, "seg-sm")}
            </div>`).join("");

    const delta = current - avg;
    const stable = Math.abs(delta) < (max - min) * 0.1;
    const trendLabel = stable ? "TENDENCIA ESTABLE" : delta > 0 ? "TENDENCIA AL ALZA" : "TENDENCIA A LA BAJA";
    const trendText = stable
        ? `La lectura actual se mantiene cerca del promedio del periodo (${f(avg)} ${M.unit}).`
        : `La lectura actual está ${Math.abs(delta).toFixed(M.dec)} ${M.unit} ${delta > 0 ? "por encima" : "por debajo"} del promedio del periodo.`;

    return moduleHead("02 / HISTORIAL", "Historial y línea base",
        `<span class="badge-status" ${sevStyle(curSev)}>${SEV_LABEL[curSev]}</span>`) +
        `<p class="module-intro">Evolución de tus parámetros según las mediciones persistidas en SQLite. La línea punteada marca el promedio del periodo.</p>` +
        tabs +
        `<div class="stat-grid">${stats}</div>

        <div class="monitor-panel" style="padding:8px">
            <div class="monitor-header"><span>${M.label}</span><span class="blue-text">● PROMEDIO ${f(avg)} ${M.unit}</span></div>
            <div class="hist-chart">${bars}<div class="hist-base" style="bottom:calc(${baseBottom.toFixed(1)}% * .945)"></div></div>
            <div class="chart-legend"><span><i></i> LECTURA ACTUAL</span><span><i class="lg-base"></i> PROMEDIO DEL PERIODO</span></div>
        </div>

        <div class="trend-note" ${sevStyle(curSev)}>
            <b>${trendLabel}</b>
            <span>${trendText}</span>
        </div>
        <p class="module-note">* Últimas ${shown.length} de ${data.length} mediciones del periodo. Fuente: GET /api/measurements.</p>`;
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
        "# Informe de Episodio (SBAR)",
        "",
        "## 1. Situación",
        `- Nivel: ${sit.level ?? "--"}`,
        `- Título: ${sanitizeNonClinical(sit.title || "--")}`,
        `- Marca de tiempo: ${sit.timestamp ?? "--"}`,
        "",
        "## 2. Antecedentes",
        `- Actividad: ${ant.activity ?? "--"}`,
        `- Dosis acumulada (μSv): ${ant.dose_total_usv ?? "--"}`,
        "",
        "## 3. Evaluación",
        `- Hipótesis orientativa (escenario simulado): ${sanitizeNonClinical(ev.hypothesis || "--")}`,
        "",
        "## 4. Recomendación",
        `- Siguiente paso (ilustrativo): ${sanitizeNonClinical(rec.next_step || "--")}`
    ].join("\n");
}

function htmlOnboardAndReportBlock() {
    const I = extractOnboardInsights();
    const report = backend.cache.report;

    const forecastStr = I.forecast.valueBpm !== null
        ? `${r0(I.forecast.valueBpm)} BPM`
        : "-- BPM";
    const persistStr = I.forecast.persistenceBpm !== null
        ? ` (persistencia: ${r0(I.forecast.persistenceBpm)} BPM)`
        : "";
    const forecastDetail = `${I.forecast.method}${I.forecast.reason ? ` · ${I.forecast.reason}` : ""}`;

    let sensText = "Calibrando sensibilidad al CO₂ (requiere variación suficiente y r² ≥ 0.6).";
    if (I.co2Sensitivity.slope !== null) {
        const r2Part = I.co2Sensitivity.r2 !== null ? ` · r² = ${I.co2Sensitivity.r2.toFixed(2)}` : "";
        const thrPart = I.co2Sensitivity.thresholdMmhg !== null
            ? ` · Umbral personal estimado: ${I.co2Sensitivity.thresholdMmhg.toFixed(2)} mmHg`
            : "";
        sensText = `Pendiente: +${I.co2Sensitivity.slope.toFixed(2)} rpm/mmHg${r2Part}${thrPart}`;
    } else if (I.co2Sensitivity.reason) {
        sensText = I.co2Sensitivity.reason;
    }

    const etaText = I.projections.co2EtaMin !== null
        ? `ETA al límite de CO₂: ~${I.projections.co2EtaMin.toFixed(1)} min${I.projections.co2EtaAssumption ? ` (${I.projections.co2EtaAssumption})` : ""}`
        : (I.projections.co2EtaReason || "ETA CO₂: sin tendencia alcista proyectable.");

    let radProjText = "Proyección de dosis: sin tasa activa o esperando datos.";
    if (I.projections.doseWithoutShelter !== null || I.projections.doseWithShelter !== null) {
        const horizon = I.projections.doseHorizonH !== null ? ` en ${I.projections.doseHorizonH} h` : "";
        const wo = I.projections.doseWithoutShelter !== null ? `${I.projections.doseWithoutShelter.toFixed(1)} µSv` : "--";
        const wi = I.projections.doseWithShelter !== null ? `${I.projections.doseWithShelter.toFixed(1)} µSv` : "--";
        radProjText = `Dosis proyectada${horizon}: sin refugio ${wo} · con refugio ${wi}`;
    }
    const doseAccText = I.projections.doseTotal !== null
        ? `Dosis acumulada: ${I.projections.doseTotal.toFixed(2)} µSv${I.projections.doseComplete === false ? " (cobertura incompleta)" : ""}`
        : "Dosis acumulada: sin lectura completa";

    const extHtml = I.externalEvent
        ? `<div class="onboard-card" ${sevStyle(1)}>
            <small>EVENTO EXTERNO NASA DONKI · ${esc(String(I.externalEvent.phase || "ACTIVO").toUpperCase())}</small>
            <h4>${esc(sanitizeNonClinical(I.externalEvent.title || I.externalEvent.event_id || "Evento solar histórico"))}</h4>
            <p>${esc(sanitizeNonClinical(I.externalEvent.summary || I.externalEvent.note || "Contexto histórico de tormenta solar en línea de tiempo de demostración."))}</p>
            ${I.externalEvent.start_time ? `<p><b>Fecha histórica:</b> ${esc(I.externalEvent.start_time)}</p>` : ""}
           </div>`
        : "";

    const reportMd = report ? formatSbarMarkdown(report) : "";
    const reportPreview = (ui.reportOpen && report)
        ? `<div class="sbar-preview"><pre>${esc(reportMd)}</pre></div>`
        : "";

    return `
        <div class="module-section-title"><span>EVALUACIÓN A BORDO E HIPÓTESIS ORIENTATIVA</span><span>/api/v1/state</span></div>
        <div class="onboard-card" ${sevStyle(I.levelSev)}>
            <small>HIPÓTESIS ORIENTATIVA (ESCENARIO SIMULADO) · ${esc(I.levelText)}</small>
            <h4>${esc(I.hypothesis)}</h4>
            ${I.patternText ? `<p><b>Patrón simulado:</b> ${esc(I.patternText)}${I.patternReason ? ` (${esc(I.patternReason)})` : ""}</p>` : ""}
            ${I.evidence.length ? `<ul>${I.evidence.slice(0, 4).map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}
            ${I.nextStep ? `<p style="margin-top:6px"><b>Revisión sugerida:</b> ${esc(I.nextStep)}</p>` : ""}
            ${I.assessmentMethod ? `<p><small>${esc(I.assessmentMethod)}</small></p>` : ""}
        </div>

        <div class="onboard-card" ${sevStyle(I.forecast.valueBpm !== null ? 0 : null)}>
            <small>PRONÓSTICO FC +60 s · ML VS PERSISTENCIA</small>
            <h4>${esc(forecastStr)}${esc(persistStr)}</h4>
            <p>${esc(forecastDetail)}</p>
        </div>

        <div class="onboard-card" ${sevStyle(I.co2Sensitivity.slope !== null ? 0 : null)}>
            <small>SENSIBILIDAD CO₂ Y PROYECCIONES (ETA / REFUGIO)</small>
            <p>${esc(sensText)}</p>
            <p>${esc(etaText)}</p>
            <p>${esc(radProjText)}</p>
            <p>${esc(doseAccText)}</p>
        </div>

        ${extHtml}

        <div class="module-section-title"><span>INFORME DE EPISODIO SBAR</span><span>${I.privacy.shareBehavioral ? "CON CONDUCTUAL" : "SOLO A BORDO"}</span></div>
        <div class="sbar-actions">
            <button type="button" class="hw-btn" id="btn-view-report">${ui.reportLoading ? "CARGANDO..." : (ui.reportOpen ? "ACTUALIZAR VISTA SBAR" : "CARGAR VISTA SBAR")}</button>
            <button type="button" class="hw-btn" id="btn-download-report">DESCARGAR SBAR (.MD)</button>
        </div>
        ${ui.reportError ? `<p class="module-note" style="color:var(--amber-glow)">${esc(ui.reportError)}</p>` : ""}
        ${reportPreview}`;
}

/* ---------- MONITOREO ---------- */
function htmlMonitoring() {
    const groups = [
        ["SIGNOS VITALES", [
            ["hr", "FRECUENCIA CARDÍACA", "BPM", () => isNum(state.hr) ? r0(state.hr) : "--"],
            ["bp", "PRESIÓN ARTERIAL", "mmHg", () => (isNum(state.sys) && isNum(state.dia)) ? `${r0(state.sys)}/${r0(state.dia)}` : "--/--"],
            ["spo2", "SATURACIÓN SpO₂", "%", () => isNum(state.spo2) ? r1(state.spo2).toFixed(1) : "--"],
            ["temp", "TEMPERATURA CORPORAL", "°C", () => isNum(state.temp) ? r1(state.temp).toFixed(1) : "--"]
        ]],
        ["RESPIRACIÓN Y ENTORNO", [
            ["rr", "FRECUENCIA RESPIRATORIA", "rpm", () => isNum(state.rr) ? r0(state.rr) : "--"],
            ["co2", "ppCO₂ AMBIENTE", "mmHg", () => isNum(state.co2) ? r1(state.co2).toFixed(1) : "--"],
            ["dose", "TASA DE DOSIS", "µSv/h", () => isNum(state.dose) ? r0(state.dose) : "--"]
        ]],
        ["RECUPERACIÓN", [
            ["hyd", "HIDRATACIÓN", "%", () => isNum(state.hyd) ? r0(state.hyd) : "--"],
            ["fat", "FATIGA ACUMULADA", "/100", () => isNum(state.fat) ? r0(state.fat) : "--"],
            ["cm", "CONTRAMEDIDAS", "%", () => isNum(state.cm) ? r0(state.cm) : "--"]
        ]]
    ];

    const validSevs = Object.keys(METRIC_INFO).map(k => D[k]).filter(isNum);
    const worst = !state.ready ? null : (validSevs.length ? Math.max(...validSevs) : null);

    const body = state.ready
        ? groups.map(([title, rows]) => `
            <div class="module-section-title"><span>${title}</span><span>TELEMETRÍA</span></div>
            <div class="metric-list">
                ${rows.map(([k, label, unit, val]) => {
                    const sev = D[k];
                    return `
                        <div class="metric-line" ${sevStyle(sev)}>
                            <div class="ml-label">
                                <b>${label}</b>
                                <small>${sevLabel(sev)} · LECTURA #${state.measurementId ?? "--"}</small>
                            </div>
                            <div class="ml-value">${segVal(val(), unit)}</div>
                        </div>`;
                }).join("")}
            </div>`).join("")
        : emptyPanel("Todavía no hay telemetría en vivo. Los indicadores mostrarán valores al llegar la primera muestra.");

    return moduleHead("01 / MONITOREO", "Monitoreo en tiempo real",
        `<span class="badge-status" ${sevStyle(worst)}>${state.ready ? sevLabel(worst) : "SIN DATOS"}</span>`) +
        `<p class="module-intro">Indicadores fisiológicos y ambientales del tripulante. Los canales sin lectura muestran "--" y ${SEV_MISSING} sin sustituirse por cero.</p>` +
        body +
        htmlOnboardAndReportBlock() +
        `<p class="module-note">* Origen: ${esc(state.source || "--")} · ${esc(fmtDateTime(state.timestamp))}.</p>`;
}

/* ---------- ALERTAS Y BITÁCORA ---------- */
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
                    <p><b>Acción sugerida:</b> ${esc(METRIC_INFO[k].action())}</p>
                </div>`).join("")
            : (missingCount === Object.keys(METRIC_INFO).length
                ? emptyPanel("Todas las señales están en SIN SEÑAL (--). No se emiten falsas alarmas ni se evalúan como nominales.")
                : `<div class="alert-card" ${sevStyle(0)}><small>INFORMACIÓN</small><h4>SIN ALERTAS EN CANALES ACTIVOS</h4><p>${missingCount ? `${missingCount} canales sin lectura (--). ` : ""}Los canales activos están dentro del rango de demostración.</p></div>`))
        : emptyPanel("Sin telemetría: no se pueden evaluar alertas.");

    const dbCards = dbAlerts.length
        ? dbAlerts.map(a => {
            const sev = sevFromApi(a.severity);
            return `
                <div class="alert-card" ${sevStyle(sev)}>
                    <small>${SEV_LABEL[sev]} — ${esc(a.metric)}${a.zone ? " · " + esc(a.zone).toUpperCase() : ""}</small>
                    <h4>${esc(sanitizeNonClinical(a.message))}</h4>
                    <p>${esc(sanitizeNonClinical(a.suggested_action || "Sin acción sugerida registrada."))}</p>
                    <p><b>Registrada:</b> ${esc(fmtDateTime(a.created_at))} · ${a.acknowledged ? "RECONOCIDA" : "PENDIENTE"}</p>
                    ${a.acknowledged ? "" : `<button class="hw-btn" type="button" data-ack-alert="${a.id}">RECONOCER</button>`}
                </div>`;
        }).join("")
        : emptyPanel("No hay alertas registradas por la API.");

    const logItems = logs.length
        ? logs.slice(0, 14).map(l => `<li><time>${esc(fmtDateTime(l.timestamp))}</time>${esc(l.zone)} — ${esc(l.action || "Sin acción registrada")}</li>`).join("")
        : "<li>Sin registros en la bitácora.</li>";

    const worst = derived.length
        ? Math.max(...derived.map(k => D[k]))
        : (state.ready && missingCount === Object.keys(METRIC_INFO).length ? null : 0);

    const ackOnboardBtn = (I.levelRaw === "watch" || I.levelRaw === "alert")
        ? `<div style="margin-bottom:8px"><button class="hw-btn" type="button" data-ack-onboard="1">RECONOCER AVISO A BORDO (+5 PTS)</button></div>`
        : "";

    return moduleHead("03 / ALERTAS", "Alertas y bitácora",
        `<span class="badge-status" ${sevStyle(worst)}>${derived.length ? `${derived.length} ACTIVA${derived.length > 1 ? "S" : ""}` : (worst === null ? SEV_MISSING : "SIN ALERTAS")}</span>`) +
        `${ui.alerts.enabled ? "" : `<div class="settings-status" ${sevStyle(1)}><span class="status-dot"></span><span>Notificaciones <b>SUSPENDIDAS</b> desde Ajustes. Las alertas se siguen evaluando y registrando.</span></div>`}
        ${ackOnboardBtn}

        <div class="module-section-title"><span>ALERTAS DERIVADAS DE LA TELEMETRÍA</span><span>${derived.length}</span></div>
        ${derivedCards}

        ${htmlOnboardAndReportBlock()}

        <div class="module-section-title"><span>ALERTAS REGISTRADAS (API)</span><span>${dbAlerts.length}</span></div>
        ${dbCards}

        <div class="module-section-title"><span>BITÁCORA</span><span>GET /api/logs</span></div>
        <ul class="log-list">${logItems}</ul>
        <p class="module-note">* Sugerencias orientativas de demostración. No constituyen diagnóstico clínico.</p>`;
}

/* ---------- BIENESTAR ---------- */
function wellbeingModel() {
    const fatValid = isNum(state.fat);
    const hydValid = isNum(state.hyd);
    const cmValid = isNum(state.cm);
    const hrValid = isNum(state.hr);
    const co2Valid = isNum(state.co2);
    const evaValid = isNum(state.evaLoad);

    const fat = fatValid
        ? (state.fat > 70 ? ["ALTA", 2] : state.fat >= 40 ? ["MODERADA", 1] : ["BAJA", 0])
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
        : (stressScore < 25 ? ["BAJO", 0] : stressScore < 50 ? ["MODERADO", 1] : ["ALTO", 2]);

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

    const mood = { good: ["BIEN", 0], ok: ["REGULAR", 1], bad: ["MAL", 2] }[ui.mood] || ["SIN REPORTE", 0];

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
        idle: "PULSA «INICIAR TEST» PARA COMENZAR (6 INTENTOS)",
        waiting: "ESPERA LA SEÑAL VERDE...",
        go: "¡AHORA! PULSA AQUÍ",
        false_start: "SALIDA EN FALSO — ESPERANDO...",
        between: "REGISTRADO — SIGUIENTE INTENTO...",
        done: `COMPLETADO · MEDIANA ${med ?? "--"} ms`
    }[rx.phase] || "PULSA «INICIAR TEST»";

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
                <b>Check-in registrado (+${r.points_awarded ?? 15} pts por participación)</b>
                <p style="margin:4px 0 0">Mediana: <b>${r.median_ms ?? med ?? "--"} ms</b> · Línea base: ${r.baseline_ms ?? "--"} ms · Delta: ${deltaStr} · Lapsos: ${r.lapses ?? 0} · Salidas en falso: ${r.false_starts ?? 0}</p>
                <p style="margin:4px 0 0">${esc(sanitizeNonClinical(r.interpretation || "Hipótesis orientativa (escenario simulado): seguimiento conductual registrado."))}</p>
            </div>`;
    }

    return `
        <div class="module-section-title"><span>CHECK-IN CONDUCTUAL · MINIJUEGO DE REACCIÓN</span><span>POST /api/v1/checkin</span></div>
        <div class="rxn-panel">
            <p style="margin:0 0 6px;font-size:11px;color:var(--muted)">Prueba breve de vigilancia psicomotora (6 intentos con espera aleatoria 1.0–3.5 s). Medición orientativa en navegador; no es diagnóstico.</p>
            <div class="rxn-stats">
                <div>INTENTO<b id="rxn-stat-trial">${rx.trial} / ${rx.totalTrials}</b></div>
                <div>MEDIANA ACTUAL<b id="rxn-stat-med">${med !== null ? `${med} ms` : "-- ms"}</b></div>
                <div>SALIDAS EN FALSO<b id="rxn-stat-false">${rx.falseStarts}</b></div>
                <div>LAPSOS (&gt;500 ms)<b id="rxn-stat-lapses">${rx.lapses}</b></div>
            </div>
            <button type="button" class="rxn-pad ${padClass}" id="rxn-pad" ${padDisabled}>${phaseText}</button>
            <div class="rxn-form">
                <label class="field-row" style="border:0;padding:0">
                    <span class="field-label">HORAS DE SUEÑO</span>
                    <input type="number" id="rxn-sleep" class="hw-input" min="0" max="24" step="0.5" value="${esc(rx.sleepHours)}">
                </label>
                <label class="field-row" style="border:0;padding:0">
                    <span class="field-label">ÁNIMO / ALERTA (1-5)</span>
                    <select id="rxn-mood" class="hw-select">
                        ${[1, 2, 3, 4, 5].map(v => `<option value="${v}" ${Number(rx.moodScore) === v ? "selected" : ""}>${v} - ${["Muy bajo", "Bajo", "Moderado", "Bueno", "Óptimo"][v - 1]}</option>`).join("")}
                    </select>
                </label>
            </div>
            <div class="rxn-actions">
                <button type="button" class="hw-btn" id="rxn-start">${running ? "REINICIAR TEST" : "INICIAR TEST (6 INTENTOS)"}</button>
                <button type="button" class="hw-btn" id="rxn-submit" ${submitDisabled}>${rx.submitting ? "ENVIANDO..." : "ENVIAR CHECK-IN"}</button>
            </div>
            ${resultHtml}
        </div>`;
}

function htmlRoutinesAndPrivacy(I) {
    const c = I.coach;
    const badgesHtml = c.badges.length
        ? `<div class="badge-row">${c.badges.map(b => `<span class="badge-chip">★ ${esc(String(b).toUpperCase())}</span>`).join("")}</div>`
        : `<p class="module-note" style="margin:4px 0">Completa rutinas o check-ins para desbloquear insignias de participación.</p>`;

    const routinesHtml = c.routines.length
        ? `<div class="routine-list">${c.routines.map(r => {
            const isDue = Boolean(r.due);
            const active = r.active !== false;
            return `
                <div class="routine-item ${isDue ? "is-due" : ""}">
                    <div class="routine-copy">
                        <b>${esc(r.title || r.id)} ${isDue ? "· PENDIENTE" : (active ? "· AL DÍA" : "· INACTIVA")}</b>
                        <small>${esc(r.description || "")} (Completadas: ${r.completed_count ?? 0})</small>
                    </div>
                    <button type="button" class="hw-btn" data-complete-routine="${esc(r.id)}" ${active ? "" : "disabled"}>COMPLETAR</button>
                </div>`;
        }).join("")}</div>`
        : emptyPanel("Cargando rutinas de /api/v1/routines...");

    const share = I.privacy.shareBehavioral;
    const privacyLabel = share
        ? "Compartir resumen en informe SBAR"
        : "Solo a bordo (por defecto)";

    return `
        <div class="module-section-title"><span>RUTINAS Y PARTICIPACIÓN</span><span>${c.points} PTS · RACHA ${c.streak}</span></div>
        <div class="coach-panel">
            <div class="coach-summary">
                <span>PUNTOS: ${c.points}</span>
                <span>RACHA: ${c.streak}</span>
                <span>LÍNEA BASE RX: ${c.reactionBaselineMs !== null ? `${c.reactionBaselineMs} ms` : "CALIBRANDO"}</span>
            </div>
            <p class="module-note" style="margin:0 0 6px">${esc(c.scoringPolicy)} (${esc(c.demoTimeLabel)}).</p>
            ${badgesHtml}
            ${routinesHtml}
        </div>

        <div class="module-section-title"><span>PRIVACIDAD CONDUCTUAL</span><span>POST /api/v1/privacy</span></div>
        <div class="privacy-panel">
            <label class="toggle-row">
                <span>Compartir resumen en informe SBAR</span>
                <input type="checkbox" class="hw-switch" data-privacy-toggle="1" ${share ? "checked" : ""}>
            </label>
            <div class="privacy-state">Estado actual: <b>${esc(privacyLabel)}</b></div>
            <p class="module-note" style="margin:4px 0 0">Por defecto (desactivado), sueño, ánimo y tiempos de reacción permanecen solo a bordo.</p>
        </div>`;
}

function htmlWellbeing() {
    const W = wellbeingModel();
    const I = extractOnboardInsights();
    const insights = backend.cache.insights || [];

    const moods = [["good", "BIEN"], ["ok", "REGULAR"], ["bad", "MAL"]].map(([id, label]) =>
        `<button type="button" class="hw-btn" data-mood="${id}" aria-pressed="${ui.mood === id}">${label}</button>`).join(" ");
    const bar = (value, max) => (isNum(value) ? Math.min(100, value / max * 100).toFixed(0) : "0");

    const insightCards = insights.length
        ? insights.slice(0, 6).map(i => {
            const sev = sevFromApi(i.risk_level);
            return `
                <div class="alert-card" ${sevStyle(sev)}>
                    <small>${SEV_LABEL[sev]} — ${esc(i.category).toUpperCase()}</small>
                    <h4>${esc(sanitizeNonClinical(i.description))}</h4>
                    <p><b>Recomendación:</b> ${esc(sanitizeNonClinical(i.recommendation))}</p>
                    <p><b>Generado:</b> ${esc(fmtDateTime(i.timestamp))}</p>
                </div>`;
        }).join("")
        : emptyPanel("El motor de análisis todavía no ha publicado insights.");

    return moduleHead("04 / BIENESTAR", "Bienestar y descanso",
        `<span class="badge-status" ${sevStyle(W.scoreSev)}>${sevLabel(W.scoreSev)}</span>`) +
        `<p class="module-intro">Seguimiento orientativo de hábitos, check-in conductual de reacción y rutinas de participación. Las señales ausentes muestran "--" y ${SEV_MISSING}.</p>

        <div class="wb-score" ${sevStyle(W.scoreSev)}>
            ${segVal(W.score !== null ? W.score : "--", "/ 100", "seg-lg")}
            <div class="wb-score-copy">
                <strong>ÍNDICE GLOBAL DE BIENESTAR</strong>
                <small>Estrés estimado: ${W.stress[0]} · Fatiga: ${W.fat[0]} · Día ${backend.cache.astronaut?.mission_day ?? "--"}</small>
                <div class="seg-bar"><div class="seg-fill" style="width:${W.score !== null ? W.score : 0}%"></div></div>
            </div>
        </div>

        ${htmlReactionGame()}

        ${htmlRoutinesAndPrivacy(I)}

        <div class="module-section-title"><span>HÁBITOS Y RECUPERACIÓN</span><span>TELEMETRÍA</span></div>
        <div class="wb-list">

            <article class="wb-card" ${sevStyle(W.exerciseSev)}>
                <div class="wb-top">
                    <span class="wb-index">01</span>
                    <div class="wb-label"><b>ACTIVIDAD FÍSICA</b><small>Tiempo de ejercicio diario</small></div>
                    <div class="wb-value">${segVal(W.exercise !== null ? W.exercise : "--", "MIN")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.exercise, 60)}%"></div></div>
                <div class="wb-foot"><span>META: 60 MIN / DÍA</span><span>${W.exercise !== null ? `${Math.round(W.exercise / 60 * 100)}% CUMPLIDO` : SEV_MISSING}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.sleepSev)}>
                <div class="wb-top">
                    <span class="wb-index">02</span>
                    <div class="wb-label"><b>SUEÑO Y DESCANSO</b><small>Horas estimadas</small></div>
                    <div class="wb-value">${segVal(W.sleep !== null ? W.sleep.toFixed(1) : "--", "H")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.sleep, 9)}%"></div></div>
                <div class="wb-foot"><span>META: 7 - 9 HORAS</span><span>${W.sleepSev === null ? SEV_MISSING : (W.sleepSev === 0 ? "DESCANSO ADECUADO" : "DESCANSO INSUFICIENTE")}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.hydSev)}>
                <div class="wb-top">
                    <span class="wb-index">03</span>
                    <div class="wb-label"><b>HIDRATACIÓN Y NUTRICIÓN</b><small>Consumo diario</small></div>
                    <div class="wb-value">${segVal(W.water !== null ? W.water.toFixed(1) : "--", "L")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${bar(W.water, 3.4)}%"></div></div>
                <div class="wb-foot"><span>AGUA · META 3.0 L</span><span>NUTRICIÓN: ${W.kcal !== null ? `${W.kcal.toLocaleString("es-PE")} KCAL` : "--"}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.fat[1])}>
                <div class="wb-top">
                    <span class="wb-index">04</span>
                    <div class="wb-label"><b>FATIGA Y RECUPERACIÓN</b><small>Nivel de fatiga reportado</small></div>
                    <div class="wb-value">${segVal(isNum(state.fat) ? r0(state.fat) : "--", "/100")}</div>
                </div>
                <div class="seg-bar"><div class="seg-fill" style="width:${isNum(state.fat) ? clamp(r0(state.fat), 0, 100) : 0}%"></div></div>
                <div class="wb-foot"><span>NIVEL: ${W.fat[0]}</span><span>${isNum(state.fat) ? (state.fat > 70 ? "RECUPERACIÓN PRIORITARIA" : state.fat >= 40 ? "RECUPERACIÓN EN CURSO" : "RECUPERACIÓN ADECUADA") : SEV_MISSING}</span></div>
            </article>

            <article class="wb-card" ${sevStyle(W.mood[1])}>
                <div class="wb-top">
                    <span class="wb-index">05</span>
                    <div class="wb-label"><b>AUTOINFORME RÁPIDO</b><small>Estado de ánimo reportado</small></div>
                    <div class="wb-value"><span class="wb-mood">${W.mood[0]}</span></div>
                </div>
                <div class="wb-moods" role="group" aria-label="Reportar estado de ánimo">${moods}</div>
                <div class="wb-foot"><span>ESTRÉS PERCIBIDO: ${W.stress[0]}</span><span>SOLO A BORDO</span></div>
            </article>

        </div>

        <div class="module-section-title"><span>ANÁLISIS ASISTIDO</span><span>GET /api/insights</span></div>
        ${insightCards}

        <p class="module-note">* Hipótesis orientativa (escenario simulado). Puntos y rachas solo por participación; no constituye diagnóstico.</p>`;
}

/* ---------- PERFIL ---------- */
function htmlProfile() {
    const a = backend.cache.astronaut;

    if (!a) {
        return moduleHead("05 / PERFIL", "Perfil del tripulante",
            `<span class="badge-status" ${sevStyle(1)}>SIN DATOS</span>`) +
            emptyPanel("No hay tripulantes registrados en /api/astronauts.") +
            `<p class="module-note">* La ficha se sirve desde la base de datos.</p>`;
    }

    const validSevs = Object.keys(METRIC_INFO).map(k => D[k]).filter(isNum);
    const anyAlert = validSevs.some(v => v > 0);
    const worst = validSevs.length ? Math.max(...validSevs) : null;
    const medicalStatus = worst === null ? SEV_MISSING : (anyAlert ? "EN OBSERVACIÓN" : "APTO PARA EVA (SIM)");
    const restriction = worst === null ? "SEÑALES PARCIALES / SIN LECTURA" : (anyAlert ? "REVISIÓN ORIENTATIVA REQUERIDA" : "SIN RESTRICCIONES SIMULADAS");
    const missionName = esc(String(a.mission || "").toUpperCase()) || "—";
    const day = String(a.mission_day ?? "—").padStart(3, "0");

    const section = (title, rows) => `
        <section class="info-section">
            <div class="info-section-head"><h4>${title}</h4></div>
            <dl class="info-list">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
        </section>`;

    return `
        <div class="profile-hero">
            <div class="profile-photo" role="img" aria-label="Fotografía simulada del tripulante">
                <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M20 25c0-8 5-14 12-14s12 6 12 14v7H20z" fill="rgba(0,255,102,.08)"/>
                    <rect x="24" y="22" width="16" height="10" rx="5" fill="rgba(0,225,255,.12)" stroke="#00e1ff" stroke-opacity=".6"/>
                    <path d="M14 60c1.7-11 9-17 18-17s16.3 6 18 17"/>
                    <path d="M25 45l7 6 7-6"/>
                    <path d="M32 12v-5M27 9h10"/>
                </svg>
                <span>FOTO SIM</span>
            </div>
            <div class="profile-id">
                <span class="module-kicker">05 / PERFIL · ${esc(a.code)}</span>
                <h3>${esc(String(a.name).toUpperCase())}</h3>
                <p>${esc(a.role)} · ${missionName} · D${day}</p>
                <span class="badge-status" ${sevStyle(worst)}>${medicalStatus}</span>
            </div>
        </div>

        ${section("INFORMACIÓN PERSONAL", [
            ["Código de astronauta", esc(a.code)],
            ["Nombres y apellidos", esc(String(a.name).toUpperCase())],
            ["Edad", `${a.age} AÑOS`],
            ["Grupo sanguíneo", esc(a.blood_type)],
            ["Estatura", `${a.height_cm} CM`],
            ["Peso", `${a.weight_kg} KG`],
            ["Identificador de tripulación", `CREW-${esc(a.code)}`]
        ])}

        ${section("INFORMACIÓN DE MISIÓN", [
            ["Nombre de misión", missionName],
            ["Rol asignado", esc(String(a.role).toUpperCase())],
            ["Día actual de misión", `D${day}`],
            ["Estado de participación", "ACTIVA"]
        ])}

        ${section("INFORMACIÓN MÉDICA", [
            ["Estado registrado", esc(String(a.status).toUpperCase())],
            ["Restricciones médicas", restriction],
            ["Origen de la ficha", "GET /api/astronauts/" + a.id]
        ])}

        <p class="module-note">* Ficha servida desde la base de datos. No contiene datos médicos reales.</p>`;
}

/* ---------- AJUSTES ---------- */
const ALERT_PRIORITIES = {
    critica: { label: "CRÍTICA", detail: "Solo alertas rojas. Reduce la carga de avisos al mínimo." },
    alta:    { label: "ALTA",    detail: "Alertas rojas y ámbar. Recomendado durante operaciones EVA." },
    todas:   { label: "TODAS",   detail: "Incluye avisos nominales y cambios graduales de tendencia." }
};
const ALERT_METHODS = {
    screen: "PANTALLA",
    log:    "BITÁCORA",
    haptic: "VIBRACIÓN",
    earth:  "ENLACE TIERRA"
};
const SYNC_MODES = {
    auto:   { label: "AUTOMÁTICA · NTP", detail: "Sincroniza el reloj de misión con la referencia de la consola." },
    manual: { label: "MANUAL",           detail: "El reloj de misión se ajusta únicamente desde el panel local." },
    earth:  { label: "POR ENLACE TIERRA", detail: "Toma la hora de la estación de control en cada ventana de contacto." }
};
const LINK_MODES = {
    nominal:      { label: "ENLACE NOMINAL",   short: "NOMINAL",      sev: 0, state: "ESTABLE",      band: "BANDA X",  latency: "1.2 s",  window: "3 H",      detail: "Telemetría completa y voz bidireccional con el centro de control." },
    reducido:     { label: "ENLACE REDUCIDO",  short: "REDUCIDO",     sev: 1, state: "DEGRADADO",    band: "BANDA S",  latency: "6.5 s",  window: "45 MIN",   detail: "Solo telemetría esencial. La voz se reserva para contingencias." },
    contingencia: { label: "CONTINGENCIA",     short: "CONTINGENCIA", sev: 2, state: "EMERGENCIA",   band: "UHF",      latency: "VARIABLE", window: "BAJO DEMANDA", detail: "Canal de emergencia con voz y telemetría mínima. Requiere confirmación del CMO." }
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
    const methodText = activeMethods.length ? activeMethods.join(" · ") : "NINGUNO";
    const alertSev = ui.alerts.enabled ? 0 : 1;
    const link = LINK_MODES[ui.mission.link] || LINK_MODES.nominal;
    const sync = SYNC_MODES[ui.mission.sync] || SYNC_MODES.auto;
    const duration = Math.max(1, Math.min(3650, Math.round(Number(ui.mission.duration) || 1)));
    const day = String(backend.cache.astronaut?.mission_day ?? 42).padStart(3, "0");

    const alertNote = ui.alerts.enabled
        ? `Prioridad <b>${priority.label}</b> · Métodos: <b>${methodText}</b>.`
        : `Notificaciones <b>SUSPENDIDAS</b>. La configuración se conserva y puede reactivarse en cualquier momento.`;
    const methodNote = activeMethods.length
        ? `Se notificará por: <b>${methodText}</b>.`
        : `Sin métodos activos: las alertas no se mostrarán ni registrarán.`;

    return moduleHead("06 / AJUSTES", "Configuración del sistema",
        `<span class="badge-status" ${sevStyle(0)}>LOCAL</span>`) +
        `<p class="module-intro">Ajusta el comportamiento de las alertas y los parámetros operativos de la consola. Los datos biométricos simulados se leen de la API; esta configuración es local.</p>

        <div class="module-section-title"><span>CONFIGURACIÓN DE ALERTAS</span><span>${ui.alerts.enabled ? "ACTIVAS" : "SUSPENDIDAS"}</span></div>
        <div class="settings-panel">
            ${alertToggle("enabled", "Activar notificaciones", ui.alerts.enabled)}
            ${alertToggle("sound", "Sonidos de alerta", ui.alerts.sound)}
            <div class="settings-label">PRIORIDAD DE NOTIFICACIONES</div>
            <div class="tab-row" role="group" aria-label="Prioridad de notificaciones">
                ${Object.keys(ALERT_PRIORITIES).map(k => priorityBtn(k, ALERT_PRIORITIES[k])).join("")}
            </div>
            <p class="settings-hint">${priority.detail}</p>
            <div class="settings-label">MÉTODOS DE NOTIFICACIÓN</div>
            <div class="method-grid" role="group" aria-label="Métodos de notificación">
                ${Object.keys(ALERT_METHODS).map(k => methodBtn(k, ALERT_METHODS[k])).join("")}
            </div>
            <p class="settings-hint">${methodNote}</p>
            <div class="settings-status" ${sevStyle(alertSev)}>
                <span class="status-dot"></span>
                <span>${alertNote}</span>
            </div>
        </div>

        <div class="module-section-title"><span>CONFIGURACIÓN DE MISIÓN</span><span>D${day} / ${duration} DÍAS</span></div>
        <div class="settings-panel">
            ${missionField("name", "NOMBRE DE MISIÓN", ui.mission.name, "text", 'autocomplete="off" spellcheck="false"')}
            ${missionField("id", "IDENTIFICADOR DE MISIÓN", ui.mission.id, "text", 'autocomplete="off" spellcheck="false"')}
            ${missionField("duration", "DURACIÓN PREVISTA (DÍAS)", ui.mission.duration, "number", 'min="1" max="3650" step="1"')}
            <label class="field-row">
                <span class="field-label">SINCRONIZACIÓN HORARIA</span>
                <select class="hw-select" data-mission="sync">
                    ${Object.keys(SYNC_MODES).map(k => `<option value="${k}" ${ui.mission.sync === k ? "selected" : ""}>${SYNC_MODES[k].label}</option>`).join("")}
                </select>
            </label>
            <p class="settings-hint">${sync.detail}</p>
            <div class="settings-readout">
                <span>DÍA ACTUAL / DURACIÓN</span>
                <span class="seg-readout"><span class="seg seg-sm">${day}</span><span class="seg-unit">/ <span data-duration-out>${String(duration).padStart(3, "0")}</span> D</span></span>
            </div>
        </div>

        <div class="module-section-title"><span>ENLACE CON LA TIERRA</span><span>${link.state}</span></div>
        <div class="tab-row" role="group" aria-label="Configuración del enlace con la Tierra">
            ${Object.keys(LINK_MODES).map(k => linkBtn(k, LINK_MODES[k])).join("")}
        </div>
        <div class="link-status" ${sevStyle(link.sev)}>
            <div class="link-status-head">
                <span class="status-dot"></span>
                <b>${link.label}</b>
                <span class="badge-status" ${sevStyle(link.sev)}>${link.state}</span>
            </div>
            <p>${link.detail}</p>
            <div class="link-meta"><span>${link.band}</span><span>LATENCIA ${link.latency}</span><span>VENTANA ${link.window}</span></div>
        </div>

        <div class="module-section-title"><span>EFECTOS DE PANTALLA</span><span>VISUAL</span></div>
        ${fxToggle("scan", "Líneas de escaneo", ui.fx.scan)}
        ${fxToggle("glow", "Resplandor neón", ui.fx.glow)}
        ${fxToggle("flicker", "Parpadeo CRT", ui.fx.flicker)}

        <div class="module-section-title"><span>SISTEMA</span><span>v1.4.0</span></div>
        <div class="window-data">
            <div>VERSIÓN: <strong>v1.4.0-API</strong></div>
            <div>ALMACENAMIENTO: <strong>SQLite · astra_health.db</strong></div>
            <div>TELEMETRÍA: <strong>REST + WebSocket</strong></div>
            <div>ESCENARIO ACTIVO: <strong>${esc(String(state.scenario || "SIN DATOS").toUpperCase())}</strong></div>
        </div>
        <p class="module-note">* Configuración local de la consola. Los indicadores simulados provienen de la API.</p>`;
}

const MODULES = {
    monitoring: { title: "CENTRO DE MONITOREO BIOMÉTRICO", html: htmlMonitoring, live: true },
    history:    { title: "HISTORIAL Y LÍNEA BASE",         html: htmlHistory,    live: false },
    alerts:     { title: "ALERTAS Y BITÁCORA",             html: htmlAlerts,     live: true },
    wellbeing:  { title: "BIENESTAR Y DESCANSO",           html: htmlWellbeing,  live: true },
    profile:    { title: "PERFIL DEL TRIPULANTE",          html: htmlProfile,    live: true },
    settings:   { title: "CONFIGURACIÓN DEL SISTEMA",      html: htmlSettings,   live: false }
};
