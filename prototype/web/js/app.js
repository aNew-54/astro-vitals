/* =========================================================
   ASTRA HEALTH · APLICACIÓN
   El estado (model.js) se rellena desde la API (api.js).
   render() solo pinta lo que llega por REST + WebSocket.
   ========================================================= */
"use strict";

(() => {
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

    const consoleEl = $("#console");
    const workspace = $("#console-workspace");
    const drawer = $("#module-drawer");
    const drawerTitle = $("#drawer-title");
    const drawerContent = $("#drawer-content");
    const closeBtn = $("#close-drawer");
    const moduleButtons = $$(".module-button");
    const standby = $("#standby");
    const ticker = $(".ticker");
    const tickerTrack = $("#ticker-track");
    const cards = {};
    $$("[data-metric]").forEach(n => { cards[n.dataset.metric] = n; });

    let powered = true;
    let shaded = false;
    const bootTime = Date.now();

    /* ---------- 1. SEVERIDAD CON LATCH (sube al instante, baja tras 2 lecturas) ---------- */
    const pending = {};
    function latchSeverity(S) {
        Object.keys(S).forEach(k => {
            const next = S[k];
            if (next === null || next === undefined) {
                D[k] = null;
                pending[k] = 0;
                return;
            }
            if (!isNum(D[k])) {
                D[k] = next;
                pending[k] = 0;
                return;
            }
            if (next >= D[k]) { D[k] = next; pending[k] = 0; return; }
            pending[k] = (pending[k] || 0) + 1;
            if (pending[k] >= 2) { D[k] = next; pending[k] = 0; }
        });
    }

    const logged = {};
    function trackAlerts() {
        Object.keys(METRIC_INFO).forEach(k => {
            const prev = logged[k];
            const cur = D[k];
            if (cur === prev) return;
            const info = METRIC_INFO[k];
            if (!isNum(cur)) {
                if (isNum(prev)) logEvent(1, `${info.label}: ${SEV_MISSING}`);
                logged[k] = null;
                return;
            }
            const prevNum = isNum(prev) ? prev : 0;
            if (cur > prevNum) {
                logEvent(cur, `${info.label} ${info.fmt()} → ${SEV_LABEL[cur]}`);
                if (typeof notifyAlert === "function") notifyAlert(k, cur);
            } else if (cur === 0 && prevNum > 0) {
                logEvent(0, `${info.label} back to NOMINAL`);
            } else if (cur < prevNum) {
                logEvent(cur, `${info.label} drops to ${SEV_LABEL[cur]}`);
            }
            logged[k] = cur;
        });
    }

    /* ---------- 2. TARJETAS DE MÉTRICAS ---------- */
    const CARD_DEF = {
        spo2: { val: () => isNum(state.spo2) ? r1(state.spo2).toFixed(1) : "--", bar: () => isNum(state.spo2) ? pct(state.spo2, 80, 100) : 0 },
        temp: { val: () => isNum(state.temp) ? r1(state.temp).toFixed(1) : "--", bar: () => isNum(state.temp) ? pct(state.temp, 34, 41) : 0 },
        rr:   { val: () => isNum(state.rr)   ? String(r0(state.rr))      : "--", bar: () => isNum(state.rr)   ? pct(state.rr, 0, 40) : 0 },
        co2:  { val: () => isNum(state.co2)  ? r1(state.co2).toFixed(1)  : "--", bar: () => isNum(state.co2)  ? pct(state.co2, 0, 8) : 0 },
        hyd:  { val: () => isNum(state.hyd)  ? String(r0(state.hyd))     : "--", bar: () => isNum(state.hyd)  ? clamp(state.hyd, 0, 100) : 0 },
        dose: { val: () => isNum(state.dose) ? (state.dose < 10 ? state.dose.toFixed(2) : String(r0(state.dose))) : "--", bar: () => isNum(state.dose) ? pct(state.dose, 0, 500) : 0 }
    };

    function setSev(node, sev) {
        if (!node) return;
        if (!isNum(sev)) {
            node.dataset.status = "warn";
            const badge = $("[data-badge]", node);
            if (badge) badge.textContent = SEV_MISSING;
            return;
        }
        node.dataset.status = SEV_KEY[sev] || "warn";
        const badge = $("[data-badge]", node);
        if (badge) badge.textContent = SEV_LABEL[sev] || SEV_MISSING;
    }

    // Los dígitos fantasma deben tener la misma longitud y separadores que el valor visible.
    function syncLcdGhosts() {
        $$(".lcd").forEach(lcd => {
            const val = $(".lcd-val", lcd);
            const ghost = $(".lcd-ghost", lcd);
            if (!val || !ghost || !val.textContent) return;
            ghost.textContent = val.textContent.trim().replace(/\d/g, "8");
        });
    }

    const hrHist = [];
    const sysHist = [];
    const sparkBars = [];
    (function buildSparkline() {
        const box = $("#bp-spark");
        for (let i = 0; i < 12; i++) { const s = document.createElement("span"); box.appendChild(s); sparkBars.push(s); }
    })();

    function renderMetrics() {
        // Frecuencia cardíaca + medidor segmentado
        const hrOk = isNum(state.hr);
        const hrValEl = $("#hr-value");
        if (hrValEl) hrValEl.textContent = hrOk ? String(r0(state.hr)) : "--";
        const frac = hrOk ? clamp((state.hr - 40) / 100, 0, 1) : 0;
        const hrGaugeEl = $("#hr-gauge-circle");
        if (hrGaugeEl) hrGaugeEl.style.strokeDashoffset = String(100 - frac * 100);
        setSev(cards.hr, hrOk ? D.hr : null);

        if (hrOk) {
            hrHist.push(state.hr);
            if (hrHist.length > 1800) hrHist.shift();
        }
        const hrAvgEl = $("#hr-avg");
        if (hrAvgEl) {
            if (hrHist.length) {
                const avg = hrHist.reduce((a, b) => a + b, 0) / hrHist.length;
                hrAvgEl.textContent = `SESSION AVG: ${r0(avg)} BPM`;
            } else {
                hrAvgEl.textContent = "SESSION AVG: -- BPM";
            }
        }

        // Presión arterial + tendencia
        const bpOk = isNum(state.sys) && isNum(state.dia);
        const bpSysEl = $("#bp-sys");
        const bpDiaEl = $("#bp-dia");
        if (bpSysEl) bpSysEl.textContent = isNum(state.sys) ? String(r0(state.sys)) : "--";
        if (bpDiaEl) bpDiaEl.textContent = isNum(state.dia) ? String(r0(state.dia)) : "--";
        setSev(cards.bp, bpOk ? D.bp : null);
        if (isNum(state.sys)) {
            sysHist.push(state.sys);
            if (sysHist.length > 12) sysHist.shift();
        }
        sparkBars.forEach((s, i) => {
            const v = sysHist[i - (12 - sysHist.length)];
            s.style.height = !isNum(v) ? "0%" : Math.max(8, pct(v, 90, 160)) + "%";
        });

        // Resto de tarjetas
        Object.keys(CARD_DEF).forEach(k => {
            const c = cards[k];
            const ok = isNum(state[k]);
            $("[data-lcd]", c).textContent = CARD_DEF[k].val();
            $("[data-bar]", c).style.width = (ok ? CARD_DEF[k].bar() : 0).toFixed(1) + "%";
            setSev(c, ok ? D[k] : null);
        });

        // Etiqueta del ECG
        const ecgState = $("#ecg-state");
        if (ecgState) {
            if (!hrOk || !isNum(D.hr)) {
                ecgState.textContent = "● NO SIGNAL";
                ecgState.className = "amber-text";
            } else if (D.hr === 0) {
                ecgState.textContent = "● STABLE SIGNAL";
                ecgState.className = "green-text";
            } else {
                ecgState.textContent = state.hr > 100 ? "● HIGH RATE" : "● LOW RATE";
                ecgState.className = D.hr === 2 ? "red-text" : "amber-text";
            }
        }

        syncLcdGhosts();
        renderHrTrend();
        renderEcgSignal();
    }

    /* Evolución de la FC con las últimas lecturas persistidas (sin generar datos). */
    function renderHrTrend() {
        const line = $("#hr-trend-line");
        const area = $("#hr-trend-area");
        const dot = $("#hr-trend-dot");
        if (!line || !area || !dot) return;

        const rows = Array.isArray(backend.cache.history) ? backend.cache.history : [];
        const values = rows
            .map(m => (m && isNum(m.hr) ? m.hr : null))
            .filter(isNum)
            .slice(-12);

        // La última lectura en vivo sustituye al último punto del historial.
        if (isNum(state.hr)) {
            if (values.length === 0) values.push(state.hr);
            else values[values.length - 1] = state.hr;
        }

        if (values.length === 0) {
            line.setAttribute("points", "");
            area.setAttribute("points", "");
            dot.setAttribute("visibility", "hidden");
            $("#hr-trend-min").textContent = "MIN —";
            $("#hr-trend-max").textContent = "MAX —";
            return;
        }

        const min = Math.min(...values);
        const max = Math.max(...values);
        $("#hr-trend-min").textContent = `MIN ${r0(min)}`;
        $("#hr-trend-max").textContent = `MAX ${r0(max)}`;

        if (values.length < 2) {
            line.setAttribute("points", "");
            area.setAttribute("points", "");
            dot.setAttribute("visibility", "hidden");
            return;
        }

        const lo = min - 4, hi = max + 4, span = hi - lo || 1;
        const W = 200, H = 48, pad = 4;
        const pts = values.map((v, i) => {
            const x = (i / (values.length - 1)) * W;
            const y = pad + (1 - (v - lo) / span) * (H - pad * 2);
            return [x, y];
        });
        const d = pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
        line.setAttribute("points", d);
        area.setAttribute("points", `0,${H} ${d} ${W},${H}`);

        const last = pts[pts.length - 1];
        dot.setAttribute("visibility", "visible");
        dot.setAttribute("cx", last[0].toFixed(1));
        dot.setAttribute("cy", last[1].toFixed(1));
    }

    /* Calidad de señal ECG derivada del estado actual (indicador visual). */
    function renderEcgSignal() {
        const box = $("#ecg-signal");
        const text = $("#ecg-signal-text");
        if (!box || !text) return;

        const bars = $$(".signal-bars i", box);

        if (!state.ready || !isNum(state.hr)) {
            box.dataset.status = "warn";
            box.title = "ECG signal quality: no signal";
            text.textContent = SEV_MISSING;
            bars.forEach(bar => bar.classList.remove("is-on"));
            return;
        }

        const spo2Sev = isNum(D.spo2) ? D.spo2 : 0;
        const evaLoad = isNum(state.evaLoad) ? state.evaLoad : 0;
        const noise = spo2Sev * 0.35 + evaLoad / 100 * 0.5;
        const hrPenalty = D.hr === 2 ? 1 : D.hr === 1 ? 0.4 : 0;
        const level = clamp(Math.round(5 - noise * 4 - hrPenalty), 1, 5);
        box.dataset.status = level >= 4 ? "ok" : level >= 3 ? "warn" : "alert";
        box.title = `ECG signal quality: ${["", "critical", "weak", "regular", "good", "optimal"][level]}`;
        text.textContent = ["", "CRITICAL", "WEAK", "REGULAR", "GOOD", "OPTIMAL"][level];
        bars.forEach((bar, i) => bar.classList.toggle("is-on", i < level));
    }

    /* ---------- 3. ESTADO GLOBAL, MISIÓN Y ORIGEN ---------- */
    const CONSOLE_KEYS = ["hr", "bp", "spo2", "temp", "rr", "co2", "hyd", "dose"];
    let tickerKey = "";
    function renderGlobal() {
        const keys = CONSOLE_KEYS;
        const validKeys = keys.filter(k => isNum(D[k]));
        const missingKeys = keys.filter(k => !isNum(D[k]));
        const active = validKeys.filter(k => D[k] > 0);
        const maxSev = active.length ? Math.max(...active.map(k => D[k])) : 0;
        const g = $("#global-status");
        if (g) {
            if (!validKeys.length) {
                g.textContent = `● ${SEV_MISSING}`;
                g.className = "amber-text";
            } else if (maxSev === 2) {
                g.textContent = `■ ALERT · ${active.length} PARAMETERS`;
                g.className = "red-text";
            } else if (maxSev === 1) {
                g.textContent = `▲ WARNING · ${active.length} PARAMETERS`;
                g.className = "amber-text";
            } else if (missingKeys.length) {
                g.textContent = `● PARTIAL · ${missingKeys.length} NO SIGNAL`;
                g.className = "amber-text";
            } else {
                g.textContent = "● VITALS NOMINAL";
                g.className = "green-text";
            }
        }

        const badge = $("#alert-count");
        if (badge) {
            badge.hidden = active.length === 0;
            badge.textContent = active.length;
            badge.classList.toggle("is-alert", maxSev === 2);
        }

        const key = active.map(k => `${k}:${D[k]}`).join(",") + "|" + missingKeys.join(",");
        if (key !== tickerKey) {
            tickerKey = key;
            const headParts = active.map(k => `${METRIC_INFO[k].label} ${METRIC_INFO[k].fmt()} [${SEV_LABEL[D[k]]}]`);
            if (missingKeys.length) headParts.push(`${missingKeys.length} PARAMETERS ${SEV_MISSING}`);
            const head = headParts.length ? headParts.join(" *** ") : "NOMINAL VITALS";
            tickerTrack.textContent = `*** ${head} *** ONBOARD TELEMETRY — EDGE ENGINE + SQLITE (REST + WS) *** NON-CLINICAL USE *** `;
            ticker.dataset.status = (!validKeys.length || (maxSev === 0 && missingKeys.length))
                ? "warn"
                : SEV_KEY[maxSev];
        }

        renderRadio();
    }

    /* Estado del enlace mostrado junto al espectro: solo refleja la conexión real. */
    function renderRadio() {
        const stateEl = $("#radio-state");
        if (!stateEl) return;

        const connected = backend.isConnected;
        const ready = state.ready;
        const sev = connected && ready ? 0 : ready ? 1 : connected ? 1 : 2;

        stateEl.textContent = connected && ready
            ? "● LINK ACTIVE"
            : connected
                ? "● WAITING FOR DATA"
                : ready
                    ? "● REST MODE"
                    : "● NO LINK";
        stateEl.className = ["green-text", "amber-text", "red-text"][sev];

        const band = $("#radio-band");
        if (band) band.textContent = connected ? "CHANNEL: WEBSOCKET" : ready ? "CHANNEL: REST" : "CHANNEL: NO CONNECTION";

        const traffic = $("#radio-traffic");
        if (traffic) traffic.textContent = connected ? "LIVE TELEMETRY" : ready ? "LAST REST READ" : "NO TRAFFIC";

        const carrier = $("#radio-carrier");
        if (carrier) carrier.textContent = "REST + WEBSOCKET";

        const ts = parseTs(state.timestamp);
        const age = ts ? Math.max(0, Math.floor((Date.now() - ts.getTime()) / 1000)) : null;
        const ageText = age === null
            ? "NO READING"
            : age < 60
                ? `READING AGE ${age}s`
                : age < 3600
                    ? `READING AGE ${Math.floor(age / 60)} min`
                    : `READING AGE ${Math.floor(age / 3600)} h`;

        const latency = $("#radio-latency");
        if (latency) latency.textContent = ageText;

        const link = $("#link-latency");
        if (link) {
            link.textContent = connected
                ? (age === null ? "ACTIVE · WS" : `ACTIVE · ${age}s`)
                : ready
                    ? "LAST REST READ"
                    : "NO LINK";
        }
    }

    function renderMission() {
        const a = backend.cache.astronaut;
        const crew = $("#mission-crew");
        const role = $("#mission-role");
        const mission = $("#mission-name");
        const day = $("#mission-day");
        const source = $("#data-source");

        if (a) {
            if (crew) crew.textContent = (a.code || "NO DATA").toUpperCase();
            if (role) role.textContent = (a.role || "NO DATA").toUpperCase();
            if (mission) mission.textContent = (a.mission || "NO DATA").toUpperCase();
            if (day) day.textContent = `D${String(a.mission_day ?? 0).padStart(3, "0")}`;
        }

        if (source) {
            source.textContent = (state.source || "NO DATA").toUpperCase();
        }
    }

    function normalizeEnvId(rawEnv) {
        if (!rawEnv) return "";
        if (typeof rawEnv === "object") return String(rawEnv.id || rawEnv.name || "");
        return String(rawEnv);
    }

    function setControlFeedback(msg, isError = false) {
        const el = $("#control-status-text");
        if (!el) return;
        el.textContent = msg;
        el.classList.toggle("amber-text", isError);
    }

    /* Controles interactivos conectados a /api/control y /api/v1/ack. */
    function renderSource() {
        const ctrl = (backend.cache.control && typeof backend.cache.control === "object")
            ? backend.cache.control
            : {};
        const onb = (backend.cache.onboard && typeof backend.cache.onboard === "object")
            ? backend.cache.onboard
            : {};
        const activeScn = String(ctrl.scenario || state.scenario || "");

        $$(".scn-btn").forEach(b => {
            const s = b.dataset.scenario;
            const on = Boolean(activeScn) && (s === activeScn || (s === "solar_event" && activeScn === "solar"));
            b.classList.toggle("is-on", on);
            b.setAttribute("aria-pressed", String(on));
            b.disabled = false;
        });

        const envSelect = $("#env-select");
        const envId = normalizeEnvId(ctrl.environment ?? onb.environment);
        if (envSelect) {
            if (envId) {
                const match = Array.from(envSelect.options).find(
                    o => o.value === envId || envId.toLowerCase().includes(o.value)
                );
                if (match) envSelect.value = match.value;
            }
            envSelect.disabled = false;
        }

        const sheltered = Boolean(ctrl.shelter ?? ctrl.shelter_active ?? onb.shelter_active);
        const btnShelter = $("#btn-shelter");
        if (btnShelter) {
            btnShelter.classList.toggle("is-on", sheltered);
            btnShelter.setAttribute("aria-pressed", String(sheltered));
            btnShelter.textContent = sheltered ? "SHELTER: ACTIVE" : "SHELTER";
            btnShelter.disabled = false;
        }

        const btnAck = $("#btn-ack");
        if (btnAck) {
            const acked = Boolean(onb.acknowledged ?? onb.alert_acknowledged);
            btnAck.classList.toggle("is-on", acked);
            btnAck.disabled = false;
        }

        const srcBadge = $("#control-source-badge");
        if (srcBadge) {
            srcBadge.textContent = activeScn === "bidmc"
                ? "GATEWAY · REAL BIDMC"
                : "GATEWAY · /api/control";
        }

        const slider = $("#eva-slider");
        const out = $("#eva-value");
        const load = isNum(state.evaLoad) ? state.evaLoad : null;
        if (slider) {
            slider.value = String(load ?? 0);
            slider.disabled = true;
        }
        if (out) out.textContent = load === null ? "--" : String(r0(load));

        if (ctrl.error) {
            setControlFeedback(`GATEWAY WARNING: ${ctrl.error}`, true);
        } else if (activeScn || envId || backend.cache.control) {
            const parts = [
                ctrl.paused ? "PAUSED" : "TRANSMITTING",
                `SCENARIO: ${(activeScn || "--").toUpperCase()}`,
                `ENVIRONMENT: ${(envId || "--").toUpperCase()}`
            ];
            if (sheltered) parts.push("SHELTER ACTIVE");
            if (isNum(ctrl.remaining_samples)) parts.push(`SAMPLES LEFT: ${ctrl.remaining_samples}`);
            setControlFeedback(parts.join(" · "), false);
        } else {
            setControlFeedback("Controls ready · Select a scenario or environment.", false);
        }

        syncLcdGhosts();
    }

    function renderOnboardSummary() {
        if (typeof extractOnboardInsights !== "function") return;
        const I = extractOnboardInsights();

        const modeBadge = $("#ai-mode-badge");
        if (modeBadge) {
            modeBadge.textContent = I.privacy.shareBehavioral ? "SHARE IN SBAR" : "ONBOARD ONLY";
        }

        const hypCard = $("#ai-hypothesis-card");
        if (hypCard) {
            hypCard.dataset.status = I.hasOnboard ? sevStatusKey(I.levelSev) : "warn";
        }

        const hypEl = $("#ai-hypothesis");
        if (hypEl) hypEl.textContent = I.hypothesis;

        const hypMeta = $("#ai-hypothesis-meta");
        if (hypMeta) {
            hypMeta.textContent = I.nextStep
                || (I.assessmentMethod ? `Method: ${I.assessmentMethod}` : "Indicative hypothesis (simulated scenario) · No clinical validity");
        }

        const fcEl = $("#ai-forecast");
        if (fcEl) {
            fcEl.textContent = I.forecast.valueBpm !== null
                ? `${r0(I.forecast.valueBpm)} BPM`
                : "-- BPM";
        }

        const fcMethod = $("#ai-forecast-method");
        if (fcMethod) {
            fcMethod.textContent = I.forecast.persistenceBpm !== null
                ? `${I.forecast.method} (pers.: ${r0(I.forecast.persistenceBpm)} BPM)`
                : (I.forecast.reason || `Method: ${I.forecast.method}`);
        }

        const co2El = $("#ai-co2-eta");
        if (co2El) {
            if (I.projections.co2EtaMin !== null) {
                co2El.textContent = `ETA ~${I.projections.co2EtaMin.toFixed(1)} min`;
            } else if (I.co2Sensitivity.slope !== null) {
                co2El.textContent = `+${I.co2Sensitivity.slope.toFixed(2)} rpm/mmHg`;
            } else {
                co2El.textContent = "--";
            }
        }

        const co2Detail = $("#ai-co2-eta-detail");
        if (co2Detail) {
            if (I.co2Sensitivity.slope !== null) {
                const r2Txt = I.co2Sensitivity.r2 !== null ? I.co2Sensitivity.r2.toFixed(2) : "--";
                const etaTxt = I.projections.co2EtaMin !== null ? ` · ETA ${I.projections.co2EtaMin.toFixed(1)} min` : "";
                co2Detail.textContent = `Sens.: +${I.co2Sensitivity.slope.toFixed(2)} (r²=${r2Txt})${etaTxt}`;
            } else {
                co2Detail.textContent = I.co2Sensitivity.reason || I.projections.co2EtaReason || "No calibrated slope";
            }
        }

        const coachEl = $("#ai-coach-stats");
        if (coachEl) {
            coachEl.textContent = `${I.coach.points} PTS · STREAK ${I.coach.streak}`;
        }

        const coachDetail = $("#ai-coach-detail");
        if (coachDetail) {
            const dueCount = I.coach.routines.filter(r => r.due).length;
            coachDetail.textContent = dueCount > 0
                ? `${dueCount} routine(s) pending · Participation only`
                : "Routines up to date · Participation only";
        }
    }

    /* ---------- 4. ESCÁNER CORPORAL ---------- */
    let selectedZone = null;
    let autoMode = true;
    const zoneNodes = $$(".zone");
    const labelNodes = $$(".zone-label");

    function renderBody() {
        const Z = computeZones(D);
        zoneNodes.forEach(n => { n.dataset.status = sevStatusKey(Z[n.dataset.zone].sev); });
        labelNodes.forEach(n => {
            const z = Z[n.dataset.zone];
            n.dataset.status = sevStatusKey(z.sev);
            $(".zl-state", n).textContent = sevLabel(z.sev);
        });
        $("#body-stage").dataset.rad = isNum(D.dose) ? SEV_KEY[D.dose] : "warn";

        const zoneKeys = Object.keys(Z);
        const flagged = zoneKeys.filter(id => isNum(Z[id].sev) && Z[id].sev > 0).length;
        const missing = zoneKeys.filter(id => !isNum(Z[id].sev)).length;
        $("#body-summary").textContent = flagged
            ? `${flagged} ZONE${flagged > 1 ? "S" : ""} UNDER OBSERVATION`
            : missing === zoneKeys.length
                ? SEV_MISSING
                : missing > 0
                    ? "PARTIAL READING"
                    : "NO ANOMALIES";

        const worst = worstZone(Z);
        const id = autoMode ? (worst ? worst.id : null) : selectedZone;
        const manual = Boolean(!autoMode && id);
        zoneNodes.forEach(n => {
            const on = n.dataset.zone === id;
            n.classList.toggle("is-selected", on);
            n.setAttribute("aria-pressed", String(manual && on));
        });
        labelNodes.forEach(n => n.classList.toggle("is-selected", n.dataset.zone === id));
        $("#body-svg").classList.toggle("has-selection", manual);
        $("#zone-reset").hidden = !manual;

        const stageZone = $("#stage-zone");
        if (stageZone) {
            stageZone.dataset.status = id ? sevStatusKey(Z[id].sev) : "ok";
            stageZone.textContent = !id
                ? "GENERAL VIEW"
                : autoMode
                    ? `AUTO · ${ZONES[id].name}`
                    : `${ZONES[id].code} · ${ZONES[id].name}`;
        }

        $("#zone-auto").setAttribute("aria-pressed", String(autoMode));
        renderReadout(id ? Z[id] : null, Z);
    }

    function renderReadout(z, Z = null) {
        const box = $("#zone-readout");
        const list = $("#zr-list");
        if (!z) {
            const allMissing = Z && Object.keys(Z).every(id => !isNum(Z[id].sev));
            box.dataset.status = allMissing ? "warn" : "ok";
            $("#zr-title").textContent = allMissing ? "SCAN ON STANDBY" : "CONTINUOUS SCAN";
            $("#zr-badge").textContent = allMissing ? SEV_MISSING : "NOMINAL";
            list.innerHTML = "";
            $("#zr-nasa").textContent = "The 7 zones group the reference spaceflight risks. With delayed communications, the crew monitors early changes onboard.";
            $("#zr-cause").textContent = allMissing ? "No reading available from the current source." : "No findings.";
            $("#zr-action").textContent = allMissing
                ? "Check the telemetry source or select an active scenario."
                : "Keep up the monitoring routine and exercise countermeasures. Tap a zone to see its detail.";
            return;
        }
        const info = ZONES[z.id];
        box.dataset.status = sevStatusKey(z.sev);
        $("#zr-title").textContent = `${info.code} ${info.name}`;
        $("#zr-badge").textContent = sevLabel(z.sev);

        const items = z.items.slice();
        if (z.viaRadiation) items.push({ k: "dose", sev: D.dose });
        list.innerHTML = items.map(i =>
            `<li ${sevStyle(i.sev)}><span>${METRIC_INFO[i.k].label}</span><b>${METRIC_INFO[i.k].fmt()}</b><i>${sevLabel(i.sev)}</i></li>`).join("");

        if (!isNum(z.sev)) {
            $("#zr-nasa").textContent = info.nasa;
            $("#zr-cause").textContent = "No reading available from the current source.";
            $("#zr-action").textContent = "Check the sensors and telemetry link for this zone.";
        } else if (z.sev === 0) {
            $("#zr-nasa").textContent = info.nasa;
            $("#zr-cause").textContent = "No findings: this zone's parameters are within range.";
            $("#zr-action").textContent = "Keep up the monitoring routine and exercise countermeasures.";
        } else {
            const m = METRIC_INFO[z.primary];
            $("#zr-nasa").textContent = z.viaRadiation ? RADIATION_NASA : info.nasa;
            $("#zr-cause").textContent = m.cause();
            $("#zr-action").textContent = m.action();
        }
    }

    function selectZone(id) {
        selectedZone = id;
        autoMode = false;
        renderBody();
    }

    $("#body-svg").addEventListener("click", e => {
        const n = e.target.closest("[data-zone]");
        if (n) selectZone(n.dataset.zone);
    });
    $("#body-svg").addEventListener("keydown", e => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const n = e.target.closest(".zone");
        if (!n) return;
        e.preventDefault();
        selectZone(n.dataset.zone);
    });
    $("#zone-auto").addEventListener("click", () => { autoMode = true; renderBody(); });
    $("#zone-reset").addEventListener("click", () => {
        autoMode = true;
        renderBody();
        $("#zone-auto").focus({ preventScroll: true });
    });

    /* Único listener de la bitácora: envía a la API y relee desde la BD */
    let logTimer = null;
    $("#zone-log").addEventListener("click", async e => {
        const btn = e.currentTarget;
        if (btn.disabled) return;

        if (!state.ready) {
            btn.textContent = "NO TELEMETRY";
            clearTimeout(logTimer);
            logTimer = setTimeout(() => { btn.textContent = "LOG ENTRY"; }, 2500);
            return;
        }

        const Z = computeZones(D);
        const id = autoMode ? (worstZone(Z) || {}).id : selectedZone;
        const zoneName = id ? ZONES[id].name : "General System";

        btn.disabled = true;
        btn.textContent = "TRANSMITTING...";

        let label = "LOGGED ✓";

        try {
            const result = await backend.saveZoneLog({
                zone: zoneName,
                action: $("#zr-action").textContent
            });
            label = result ? "LOGGED ✓" : "NETWORK FAILURE";
            if (result) refreshDrawer(true);
        } catch (err) {
            label = "NETWORK FAILURE";
        }

        btn.textContent = label;
        logTimer = setTimeout(() => {
            btn.textContent = "LOG ENTRY";
            btn.disabled = false;
        }, 3000);
    });

    /* ---------- 5. ESTADO SIN DATOS ---------- */
    function renderIdle() {
        const g = $("#global-status");
        if (g) { g.textContent = "● WAITING FOR TELEMETRY"; g.className = "amber-text"; }

        const badge = $("#alert-count");
        if (badge) badge.hidden = true;

        const hrValEl = $("#hr-value");
        if (hrValEl) hrValEl.textContent = "--";
        const hrGaugeEl = $("#hr-gauge-circle");
        if (hrGaugeEl) hrGaugeEl.style.strokeDashoffset = "100";
        const hrAvgEl = $("#hr-avg");
        if (hrAvgEl) hrAvgEl.textContent = "SESSION AVG: -- BPM";

        const bpSysEl = $("#bp-sys");
        const bpDiaEl = $("#bp-dia");
        if (bpSysEl) bpSysEl.textContent = "--";
        if (bpDiaEl) bpDiaEl.textContent = "--";
        sparkBars.forEach(s => { s.style.height = "0%"; });

        Object.keys(CARD_DEF).forEach(k => {
            const c = cards[k];
            if (!c) return;
            const lcd = $("[data-lcd]", c);
            const bar = $("[data-bar]", c);
            if (lcd) lcd.textContent = "--";
            if (bar) bar.style.width = "0.0%";
        });

        $$("[data-badge]").forEach(b => { b.textContent = SEV_MISSING; });
        $$("[data-metric]").forEach(n => { n.dataset.status = "warn"; });

        const summary = $("#body-summary");
        if (summary) summary.textContent = SEV_MISSING;

        const ecg = $("#ecg-state");
        if (ecg) { ecg.textContent = `● ${SEV_MISSING}`; ecg.className = "amber-text"; }

        $("#zr-title").textContent = "NO TELEMETRY";
        $("#zr-badge").textContent = SEV_MISSING;
        $("#zr-list").innerHTML = "";
        $("#zr-nasa").textContent = "Waiting for the first measurement in the onboard database.";
        $("#zr-cause").textContent = "—";
        $("#zr-action").textContent = "—";

        syncLcdGhosts();
        renderHrTrend();
        renderEcgSignal();
        renderRadio();
        renderMission();
        renderSource();
        renderOnboardSummary();
        refreshDrawer(false);
    }

    /* ---------- 6. RENDER GENERAL ---------- */
    function render() {
        if (!state.ready) { renderIdle(); return; }

        latchSeverity(evaluate());
        trackAlerts();
        renderMetrics();
        renderGlobal();
        renderMission();
        renderSource();
        renderOnboardSummary();
        renderBody();
        refreshDrawer(false);
    }

    let lastFallbackPoll = 0;
    function tick() {
        if (!powered) return;
        render();
        if (!backend.isConnected && Date.now() - lastFallbackPoll >= 2000) {
            lastFallbackPoll = Date.now();
            Promise.allSettled([backend.loadLatest(), backend.getOnboardState()]).then(() => {
                if (powered) render();
            });
        }
    }

    /* ---------- 7. CAJÓN DE MÓDULOS ---------- */
    let activeModule = null;
    let lastTrigger = null;

    function clearRxnTimer() {
        if (ui.rxn.timerId) {
            clearTimeout(ui.rxn.timerId);
            ui.rxn.timerId = null;
        }
    }

    function resetRxnIfRunning() {
        if (["waiting", "go", "false_start", "between"].includes(ui.rxn.phase)) {
            clearRxnTimer();
            ui.rxn.phase = "idle";
        }
    }

    function syncRxnDom(customPadText = null) {
        const rx = ui.rxn;
        const pad = $("#rxn-pad", drawerContent);
        const startBtn = $("#rxn-start", drawerContent);
        const submitBtn = $("#rxn-submit", drawerContent);
        const med = medianReactionMs(rx.times);

        const elTrial = $("#rxn-stat-trial", drawerContent);
        const elMed = $("#rxn-stat-med", drawerContent);
        const elFalse = $("#rxn-stat-false", drawerContent);
        const elLapses = $("#rxn-stat-lapses", drawerContent);
        if (elTrial) elTrial.textContent = `${rx.trial} / ${rx.totalTrials}`;
        if (elMed) elMed.textContent = med !== null ? `${med} ms` : "-- ms";
        if (elFalse) elFalse.textContent = String(rx.falseStarts);
        if (elLapses) elLapses.textContent = String(rx.lapses);

        if (pad) {
            const clsMap = {
                waiting: "is-waiting",
                go: "is-go",
                false_start: "is-false",
                done: "is-done"
            };
            const textMap = {
                idle: "PRESS «START TEST» TO BEGIN (6 TRIALS)",
                waiting: "WAIT FOR THE GREEN SIGNAL...",
                go: "NOW! TAP HERE",
                false_start: "FALSE START — WAITING...",
                between: "RECORDED — NEXT TRIAL...",
                done: `COMPLETED · MEDIAN ${med ?? "--"} ms`
            };
            pad.className = `rxn-pad ${clsMap[rx.phase] || ""}`.trim();
            pad.disabled = rx.phase === "idle" || rx.phase === "done" || rx.phase === "between";
            pad.textContent = customPadText || textMap[rx.phase] || textMap.idle;
        }

        const running = ["waiting", "go", "false_start", "between"].includes(rx.phase);
        if (startBtn) startBtn.textContent = running ? "RESTART TEST" : "START TEST (6 TRIALS)";
        if (submitBtn) submitBtn.disabled = rx.times.length === 0 || rx.phase !== "done" || rx.submitting;
    }

    function startRxnWait() {
        clearRxnTimer();
        ui.rxn.phase = "waiting";
        syncRxnDom();
        const delayMs = 1000 + Math.random() * 2500;
        ui.rxn.timerId = setTimeout(() => {
            ui.rxn.timerId = null;
            if (ui.rxn.phase !== "waiting") return;
            ui.rxn.phase = "go";
            ui.rxn.goAt = performance.now();
            syncRxnDom();
        }, delayMs);
    }

    function startRxnGame() {
        clearRxnTimer();
        ui.rxn.trial = 1;
        ui.rxn.times = [];
        ui.rxn.falseStarts = 0;
        ui.rxn.lapses = 0;
        ui.rxn.goAt = 0;
        ui.rxn.lastResult = null;
        ui.rxn.error = null;
        ui.rxn.submitting = false;
        startRxnWait();
    }

    function handleRxnPadClick() {
        if (ui.rxn.phase === "waiting") {
            clearRxnTimer();
            ui.rxn.falseStarts += 1;
            ui.rxn.phase = "false_start";
            syncRxnDom();
            ui.rxn.timerId = setTimeout(() => {
                ui.rxn.timerId = null;
                startRxnWait();
            }, 900);
            return;
        }
        if (ui.rxn.phase === "go") {
            const elapsed = Math.max(1, Math.round(performance.now() - ui.rxn.goAt));
            ui.rxn.times.push(elapsed);
            if (elapsed > 500) ui.rxn.lapses += 1;

            if (ui.rxn.times.length >= ui.rxn.totalTrials) {
                ui.rxn.phase = "done";
                renderDrawer();
            } else {
                ui.rxn.phase = "between";
                ui.rxn.trial = ui.rxn.times.length + 1;
                syncRxnDom(`${elapsed} ms — NEXT...`);
                ui.rxn.timerId = setTimeout(() => {
                    ui.rxn.timerId = null;
                    startRxnWait();
                }, 550);
            }
        }
    }

    function renderDrawer() {
        drawerContent.innerHTML = MODULES[activeModule].html();
    }

    function refreshDrawer(force) {
        if (!activeModule || !workspace.classList.contains("drawer-open")) return;
        const rxnRunning = activeModule === "wellbeing"
            && ["waiting", "go", "false_start", "between"].includes(ui.rxn.phase);
        if (rxnRunning) return;
        if (!MODULES[activeModule].live && !force) return;
        if (!force && drawerContent.contains(document.activeElement)) return; // no robar el foco
        if (force && drawerContent.contains(document.activeElement)
            && ["INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
        const scrollTop = drawerContent.scrollTop;
        renderDrawer();
        drawerContent.scrollTop = scrollTop;
    }

    function openModule(id, trigger) {
        if (!MODULES[id]) return;
        if (activeModule === id && workspace.classList.contains("drawer-open")) { closeDrawer(); return; }
        resetRxnIfRunning();
        activeModule = id;
        lastTrigger = trigger || null;
        drawerTitle.textContent = MODULES[id].title;
        renderDrawer();
        workspace.classList.add("drawer-open");
        drawer.setAttribute("aria-hidden", "false");
        moduleButtons.forEach(b => {
            const on = b.dataset.module === id;
            b.classList.toggle("is-active", on);
            b.setAttribute("aria-pressed", String(on));
        });
        closeBtn.focus({ preventScroll: true });
    }

    function closeDrawer() {
        resetRxnIfRunning();
        workspace.classList.remove("drawer-open");
        drawer.setAttribute("aria-hidden", "true");
        activeModule = null;
        moduleButtons.forEach(b => { b.classList.remove("is-active"); b.setAttribute("aria-pressed", "false"); });
        if (lastTrigger) lastTrigger.focus({ preventScroll: true });
    }

    moduleButtons.forEach(b => b.addEventListener("click", () => openModule(b.dataset.module, b)));
    closeBtn.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", e => {
        if (e.key !== "Escape") return;
        if (workspace.classList.contains("drawer-open")) { closeDrawer(); return; }
        const tag = (e.target && e.target.tagName || "").toLowerCase();
        if (/^(input|textarea|select)$/.test(tag)) return;
        if (!autoMode) { autoMode = true; renderBody(); }
    });

    const controlPanel = $("#control-panel");
    if (controlPanel) {
        controlPanel.addEventListener("click", e => {
            const scnBtn = e.target.closest(".scn-btn");
            if (scnBtn) {
                const scenario = scnBtn.dataset.scenario;
                setControlFeedback(`Applying scenario ${scenario.toUpperCase()}...`, false);
                backend.setControl({ scenario })
                    .then(() => backend.refresh())
                    .then(() => {
                        logEvent(0, `SCENARIO: ${scenario.toUpperCase()}`);
                        render();
                        refreshDrawer(true);
                    })
                    .catch(err => setControlFeedback(`Gateway error: ${err.message}`, true));
                return;
            }

            if (e.target.closest("#btn-shelter")) {
                const ctrl = backend.cache.control || {};
                const cur = Boolean(ctrl.shelter ?? ctrl.shelter_active ?? backend.cache.onboard?.shelter_active);
                const nextShelter = !cur;
                setControlFeedback(nextShelter ? "Activating shelter..." : "Deactivating shelter...", false);
                backend.setControl({ shelter: nextShelter })
                    .then(() => backend.refresh())
                    .then(() => {
                        logEvent(0, nextShelter ? "SIMULATED SHELTER ACTIVATED" : "SIMULATED SHELTER DEACTIVATED");
                        render();
                        refreshDrawer(true);
                    })
                    .catch(err => setControlFeedback(`Shelter error: ${err.message}`, true));
                return;
            }

            if (e.target.closest("#btn-ack")) {
                const ackBtn = $("#btn-ack");
                if (ackBtn) ackBtn.disabled = true;
                backend.acknowledgeOnboard()
                    .then(() => backend.getOnboardState())
                    .then(() => {
                        logEvent(0, "ONBOARD ALERT ACKNOWLEDGED (ACK)");
                        render();
                        refreshDrawer(true);
                    })
                    .catch(err => setControlFeedback(`ACK error: ${err.message}`, true))
                    .finally(() => { if (ackBtn) ackBtn.disabled = false; });
            }
        });
    }

    const envSelectEl = $("#env-select");
    if (envSelectEl) {
        envSelectEl.addEventListener("change", () => {
            const env = envSelectEl.value;
            setControlFeedback(`Switching environment to ${env.toUpperCase()}...`, false);
            backend.setEnvironment(env)
                .then(() => backend.refresh())
                .then(() => {
                    logEvent(0, `ENVIRONMENT: ${env.toUpperCase()}`);
                    render();
                    refreshDrawer(true);
                })
                .catch(err => setControlFeedback(`Environment error: ${err.message}`, true));
        });
    }

    function rerenderKeepFocus(selector) {
        const scrollTop = drawerContent.scrollTop;
        renderDrawer();
        drawerContent.scrollTop = scrollTop;
        const again = $(selector, drawerContent);
        if (again) again.focus({ preventScroll: true });
    }

    drawerContent.addEventListener("click", e => {
        const b = e.target.closest("button");
        if (!b) return;

        if (b.id === "rxn-start") { startRxnGame(); return; }
        if (b.id === "rxn-pad") { handleRxnPadClick(); return; }
        if (b.id === "rxn-submit") {
            if (ui.rxn.times.length === 0 || ui.rxn.phase !== "done" || ui.rxn.submitting) return;
            const sleepEl = $("#rxn-sleep", drawerContent);
            const moodEl = $("#rxn-mood", drawerContent);
            if (sleepEl) {
                const s = Number(sleepEl.value);
                if (Number.isFinite(s)) ui.rxn.sleepHours = clamp(s, 0, 24);
            }
            if (moodEl) {
                const m = Math.round(Number(moodEl.value));
                if (Number.isFinite(m)) ui.rxn.moodScore = clamp(m, 1, 5);
            }
            ui.rxn.submitting = true;
            ui.rxn.error = null;
            renderDrawer();
            backend.submitCheckin({
                reaction_ms: ui.rxn.times.slice(),
                false_starts: ui.rxn.falseStarts,
                lapses: ui.rxn.lapses,
                sleep_hours: ui.rxn.sleepHours,
                mood: ui.rxn.moodScore,
                source: "declared"
            })
                .then(res => {
                    ui.rxn.submitting = false;
                    if (!res) {
                        ui.rxn.error = "No response from /api/v1/checkin.";
                    } else {
                        ui.rxn.lastResult = res;
                        logEvent(0, "BEHAVIORAL CHECK-IN RECORDED");
                    }
                    return Promise.allSettled([backend.getOnboardState(), backend.getRoutines()]);
                })
                .catch(err => {
                    ui.rxn.submitting = false;
                    ui.rxn.error = err?.message || "Error submitting check-in.";
                })
                .finally(() => { render(); refreshDrawer(true); });
            return;
        }

        if (b.dataset.completeRoutine) {
            const rid = b.dataset.completeRoutine;
            b.disabled = true;
            backend.completeRoutine(rid)
                .then(() => Promise.allSettled([backend.getRoutines(), backend.getOnboardState()]))
                .then(() => {
                    logEvent(0, `ROUTINE COMPLETED: ${rid}`);
                    render();
                    refreshDrawer(true);
                })
                .catch(() => { b.disabled = false; });
            return;
        }

        if (b.dataset.ackOnboard) {
            b.disabled = true;
            backend.acknowledgeOnboard()
                .then(() => backend.getOnboardState())
                .then(() => {
                    logEvent(0, "ONBOARD ALERT ACKNOWLEDGED (ACK)");
                    render();
                    refreshDrawer(true);
                })
                .catch(() => { b.disabled = false; });
            return;
        }

        if (b.id === "btn-view-report") {
            ui.reportOpen = true;
            ui.reportLoading = true;
            ui.reportError = null;
            rerenderKeepFocus("#btn-view-report");
            backend.getReport()
                .then(rep => {
                    ui.reportLoading = false;
                    if (!rep) ui.reportError = "Could not load /api/v1/report.";
                    refreshDrawer(true);
                })
                .catch(err => {
                    ui.reportLoading = false;
                    ui.reportError = err?.message || "Error loading SBAR report.";
                    refreshDrawer(true);
                });
            return;
        }

        if (b.id === "btn-download-report") {
            b.disabled = true;
            (backend.cache.report ? Promise.resolve(backend.cache.report) : backend.getReport())
                .then(rep => {
                    if (!rep) throw new Error("SBAR report unavailable.");
                    const md = formatSbarMarkdown(rep);
                    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "astro-vitals-sbar.md";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                    logEvent(0, "SBAR REPORT DOWNLOADED (.MD)");
                })
                .catch(err => {
                    ui.reportOpen = true;
                    ui.reportError = err?.message || "Error downloading SBAR report.";
                    refreshDrawer(true);
                })
                .finally(() => { b.disabled = false; });
            return;
        }

        if (b.dataset.ackAlert) {
            b.disabled = true;
            backend.acknowledgeAlert(Number(b.dataset.ackAlert))
                .then(() => Promise.allSettled([backend.loadAlerts(), backend.loadLogs()]))
                .then(() => refreshDrawer(true))
                .catch(() => { b.disabled = false; });
            return;
        }

        if (b.dataset.histRange) { ui.histRange = b.dataset.histRange; rerenderKeepFocus(`[data-hist-range="${ui.histRange}"]`); }
        else if (b.dataset.histMetric) { ui.histMetric = b.dataset.histMetric; rerenderKeepFocus(`[data-hist-metric="${ui.histMetric}"]`); }
        else if (b.dataset.mood) {
            ui.mood = b.dataset.mood;
            logEvent(ui.mood === "bad" ? 1 : 0, `SELF-REPORT: mood ${{ good: "GOOD", ok: "FAIR", bad: "POOR" }[ui.mood]}`);
            rerenderKeepFocus(`[data-mood="${ui.mood}"]`);
        }
        else if (b.dataset.alertPriority) {
            ui.alerts.priority = b.dataset.alertPriority;
            logEvent(ui.alerts.priority === "critica" ? 1 : 0, `ALERT CONFIG: priority ${ALERT_PRIORITIES[ui.alerts.priority].label}`);
            rerenderKeepFocus(`[data-alert-priority="${ui.alerts.priority}"]`);
        }
        else if (b.dataset.alertMethod) {
            const key = b.dataset.alertMethod;
            ui.alerts.methods[key] = !ui.alerts.methods[key];
            rerenderKeepFocus(`[data-alert-method="${key}"]`);
        }
        else if (b.dataset.missionLink) {
            ui.mission.link = b.dataset.missionLink;
            const link = LINK_MODES[ui.mission.link];
            logEvent(link.sev, `EARTH LINK: mode ${link.label}`);
            rerenderKeepFocus(`[data-mission-link="${ui.mission.link}"]`);
        }
    });

    function applyFx() {
        document.body.classList.toggle("fx-no-scan", !ui.fx.scan);
        document.body.classList.toggle("fx-no-glow", !ui.fx.glow);
        document.body.classList.toggle("fx-flicker", ui.fx.flicker);
    }
    drawerContent.addEventListener("change", e => {
        const t = e.target;
        if (t.dataset && t.dataset.privacyToggle) {
            const share = Boolean(t.checked);
            t.disabled = true;
            backend.setPrivacy(share)
                .then(() => backend.getOnboardState())
                .then(() => {
                    logEvent(0, share ? "PRIVACY: SUMMARY IN SBAR" : "PRIVACY: ONBOARD ONLY");
                    render();
                    rerenderKeepFocus("[data-privacy-toggle]");
                })
                .catch(() => { t.disabled = false; });
            return;
        }
        if (t.id === "rxn-sleep") {
            const s = Number(t.value);
            if (Number.isFinite(s)) ui.rxn.sleepHours = clamp(s, 0, 24);
            return;
        }
        if (t.id === "rxn-mood") {
            const m = Math.round(Number(t.value));
            if (Number.isFinite(m)) ui.rxn.moodScore = clamp(m, 1, 5);
            return;
        }
        if (t.dataset && t.dataset.fx) { ui.fx[t.dataset.fx] = t.checked; applyFx(); return; }
        if (t.dataset && t.dataset.alert) {
            ui.alerts[t.dataset.alert] = t.checked;
            if (t.dataset.alert === "enabled") {
                logEvent(t.checked ? 0 : 1, `ALERT CONFIG: notifications ${t.checked ? "ENABLED" : "SUSPENDED"}`);
                rerenderKeepFocus(`[data-alert="enabled"]`);
            }
            return;
        }
        if (t.dataset && t.dataset.mission) {
            const field = t.dataset.mission;
            if (field === "duration") {
                const v = Math.max(1, Math.min(3650, Math.round(Number(t.value) || 1)));
                ui.mission.duration = v;
                t.value = String(v);
                const out = $("[data-duration-out]", drawerContent);
                if (out) out.textContent = String(v).padStart(3, "0");
            } else if (field === "sync") {
                ui.mission.sync = t.value;
                rerenderKeepFocus(`[data-mission="sync"]`);
            } else {
                const val = t.value.trim();
                if (field === "name") ui.mission.name = val || "ARTEMIS-SIM";
                else if (field === "id") ui.mission.id = val || "AST-MSN-042";
                else ui.mission[field] = val;
                t.value = ui.mission[field];
            }
        }
    });

    drawerContent.addEventListener("input", e => {
        const t = e.target;
        if (t.id === "rxn-sleep") {
            const s = Number(t.value);
            if (Number.isFinite(s)) ui.rxn.sleepHours = clamp(s, 0, 24);
            return;
        }
        if (!t.dataset || !t.dataset.mission) return;
        const field = t.dataset.mission;
        ui.mission[field] = t.value;
        if (field === "duration") {
            const out = $("[data-duration-out]", drawerContent);
            if (out) {
                const v = Math.max(0, Math.min(3650, Math.round(Number(t.value) || 0)));
                out.textContent = String(v).padStart(3, "0");
            }
        }
    });

    /* ---------- 8. VENTANA: STANDBY / CONTRAER ---------- */
    function setPower(on) {
        powered = on;
        standby.hidden = on;
        consoleEl.classList.toggle("is-off", !on);
        const btn = $("#btn-power");
        btn.setAttribute("aria-pressed", String(!on));
        const label = $("#pwr-label");
        label.textContent = on ? "PWR ONLINE" : "STANDBY";
        label.className = on ? "green-text" : "amber-text";
        logEvent(0, on ? "DISPLAYS ON" : "DISPLAYS IN STANDBY");
    }
    function setShade(on) {
        shaded = on;
        consoleEl.classList.toggle("is-shaded", on);
        $("#btn-shade").setAttribute("aria-pressed", String(on));
    }
    $("#btn-power").addEventListener("click", () => setPower(!powered));
    $("#btn-shade").addEventListener("click", () => setShade(!shaded));
    $("#titlebar").addEventListener("dblclick", e => { if (!e.target.closest(".win-buttons")) setShade(!shaded); });

    /* ---------- 9. RELOJES ---------- */
    const pad = n => String(n).padStart(2, "0");
    function tickClocks() {
        $("#system-clock").textContent = nowTime();

        const s = Math.floor((Date.now() - bootTime) / 1000);
        const day = String(backend.cache.astronaut?.mission_day ?? 42).padStart(3, "0");
        $("#met-clock").textContent = `${day}:${pad(Math.floor(s / 3600) % 24)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;

        const el = $("#last-sync-time");
        const ts = parseTs(state.timestamp);

        if (!ts) {
            el.textContent = "NO DATA";
            return;
        }

        const age = Math.max(0, Math.floor((Date.now() - ts.getTime()) / 1000));
        el.textContent = age < 60
            ? `${age}s AGO`
            : age < 3600
                ? `${Math.floor(age / 60)} min AGO`
                : `${Math.floor(age / 3600)} h AGO`;
    }

    /* ---------- 10. ARRANQUE ---------- */
    logEvent(0, "SYSTEM STARTED — CONNECTING TO API");

    let lastOnboardSync = 0;
    backend.onTelemetry = () => {
        if (!powered) return;
        render();
        const now = Date.now();
        if (now - lastOnboardSync >= 3000) {
            lastOnboardSync = now;
            backend.getOnboardState()
                .then(() => { if (powered) renderOnboardSummary(); })
                .catch(() => {});
        }
    };

    applyFx();
    render();
    tickClocks();

    setInterval(tick, 1000);
    setInterval(tickClocks, 1000);

    // Refresco periódico de historial, alertas, bitácora, insights y estado a bordo.
    setInterval(() => {
        backend.refresh().then(() => {
            if (powered) render();
            refreshDrawer(true);
        });
    }, 15000);

    // Carga inicial por REST y después telemetría por WebSocket.
    backend.bootstrap()
        .then(() => { render(); refreshDrawer(true); })
        .catch(error => console.error("Error en la carga inicial:", error));

    backend.connectTelemetry();

    startCanvases($("#ecg-canvas"), $("#radio-canvas"), () => ({
        running: powered && !shaded && state.ready,
        hr: isNum(state.hr) ? state.hr : null,
        color: isNum(D.hr) ? (["#00ff66", "#ffb000", "#ff3b3b"][D.hr] || "#00ff66") : "#ffb000",
        noise: (isNum(D.spo2) ? D.spo2 : 0) * 0.3 + (isNum(state.evaLoad) ? state.evaLoad : 0) / 100 * 0.5,
        level: isNum(state.hr)
            ? clamp(0.25 + (state.hr - 60) / 120 * 0.4 + (isNum(state.evaLoad) ? state.evaLoad : 0) / 100 * 0.3, 0.2, 0.95)
            : 0.2,
        link: backend.isConnected ? (state.ready ? 0 : 1) : 2
    }));
})();