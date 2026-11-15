/* =========================================================
   ASTRA HEALTH · NOTIFICACIONES EMERGENTES
   Avisos flotantes en la esquina superior derecha + señal sonora.
   Se disparan desde trackAlerts() (app.js) cuando una métrica
   empeora. Respetan la configuración del módulo Ajustes:
   notificaciones activas, sonido, prioridad y método "pantalla".
   ========================================================= */
"use strict";

(() => {
    const STACK_ID = "toast-stack";
    const MAX_VISIBLE = 4;
    const AUTO_DISMISS = { 1: 6500, 2: 9500 };   // ms según severidad
    const RATE_LIMIT_MS = 8000;                   // evita repetir la misma alerta

    const lastNotified = {};
    let lastSoundAt = 0;
    let stack = null;

    /* ---------- SONIDO DESDE ARCHIVO ---------- */
    // Ruta relativa a index.html: funciona tanto en "/" como en "/ui/".
    const ALERT_SOUND_SRC = new URL("sounds/sound_alert.mp3", document.baseURI).href;
    const ALERT_VOLUME = 0.8;                     // de 0 a 1
    const ALERT_REPEATS = 2;                      // cuántas veces suena
    const SOUND_GAP_MS = 250;                     // evita duplicar el sonido en una misma ráfaga

    const alertAudio = new Audio(ALERT_SOUND_SRC);
    alertAudio.preload = "auto";
    alertAudio.volume = ALERT_VOLUME;
    alertAudio.load();

    let repeatsLeft = 0;
    alertAudio.addEventListener("ended", () => {
        if (repeatsLeft > 0) {
            repeatsLeft--;
            alertAudio.currentTime = 0;
            try { alertAudio.play().catch(() => fallbackBeep()); } catch (_) { fallbackBeep(); }
        }
    });
    alertAudio.addEventListener("error", () => {
        console.warn("No se pudo cargar el audio de alerta:", ALERT_SOUND_SRC);
    });

    /* ---------- RESPALDO: pitido sintetizado ---------- */
    // Si el MP3 no carga (ruta/servidor) o el navegador bloquea la reproducción,
    // generamos un pitido con Web Audio para que la alerta siempre sea audible.
    let audioCtx = null;
    function getAudioCtx() {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        if (!audioCtx) audioCtx = new Ctx();
        if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
        return audioCtx;
    }

    function fallbackBeep(sev) {
        const ctx = getAudioCtx();
        if (!ctx) return;
        const t0 = ctx.currentTime;
        const freq = sev >= 2 ? 880 : 660;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "square";
        osc.frequency.setValueAtTime(freq, t0);
        osc.frequency.setValueAtTime(freq * 1.5, t0 + 0.12);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.12, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.32);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t0);
        osc.stop(t0 + 0.34);
    }

    /* ---------- 1. CONTENEDOR ---------- */
    function getStack() {
        if (stack && stack.isConnected) return stack;
        stack = document.createElement("div");
        stack.id = STACK_ID;
        stack.className = "toast-stack";
        document.body.appendChild(stack);
        return stack;
    }

    let audioUnlocked = false;
    function unlockAudio() {
        if (audioUnlocked) return;
        audioUnlocked = true;
        getAudioCtx();               // crea/reanuda el contexto dentro del gesto del usuario
        alertAudio.muted = true;
        let p;
        try { p = alertAudio.play(); } catch (_) { p = null; }
        if (!p || typeof p.then !== "function") {
            alertAudio.muted = false;
            return;
        }
        p.then(() => { alertAudio.pause(); alertAudio.currentTime = 0; alertAudio.muted = false; })
            .catch(() => { audioUnlocked = false; alertAudio.muted = false; });
    }
    document.addEventListener("pointerdown", unlockAudio, { passive: true });
    document.addEventListener("keydown", unlockAudio);

    function playAlertSound(sev) {
        if (!ui.alerts.sound) return;
        const now = performance.now();
        if (now - lastSoundAt < SOUND_GAP_MS) return;
        lastSoundAt = now;

        repeatsLeft = Math.max(0, ALERT_REPEATS - 1);
        try { alertAudio.currentTime = 0; } catch (_) { /* aún sin metadatos */ }
        let p;
        try { p = alertAudio.play(); } catch (_) { p = null; }
        if (!p || typeof p.then !== "function") {
            fallbackBeep(sev);
            return;
        }
        p.catch(err => {
            console.warn("Audio bloqueado o no encontrado, usando pitido de respaldo:", err);
            audioUnlocked = false;   // se reintenta en la próxima interacción
            fallbackBeep(sev);
        });
    }

    /* ---------- 3. AVISO FLOTANTE ---------- */
    function dismiss(node, immediate) {
        if (!node || node.dataset.closing) return;
        node.dataset.closing = "1";
        clearTimeout(node._dismissTimer);
        if (immediate) { node.remove(); return; }
        node.classList.add("is-leaving");
        node.addEventListener("animationend", () => node.remove(), { once: true });
        setTimeout(() => node.remove(), 420);   // respaldo si no hay animación
    }

    function buildToast(key, sev) {
        const info = METRIC_INFO[key];
        const ms = AUTO_DISMISS[sev] || AUTO_DISMISS[1];

        const node = document.createElement("article");
        node.className = "toast";
        node.dataset.status = SEV_KEY[sev] || "warn";
        node.setAttribute("role", sev >= 2 ? "alert" : "status");
        node.setAttribute("aria-atomic", "true");

        const head = document.createElement("div");
        head.className = "toast-head";
        const badge = document.createElement("span");
        badge.className = "toast-sev";
        const dot = document.createElement("i");
        dot.className = "toast-dot";
        dot.setAttribute("aria-hidden", "true");
        badge.append(dot, document.createTextNode(SEV_LABEL[sev]));
        const time = document.createElement("time");
        time.className = "toast-time";
        time.textContent = nowTime();
        head.append(badge, time);

        const title = document.createElement("h4");
        title.className = "toast-title";
        title.textContent = info ? info.label : String(key).toUpperCase();

        const value = document.createElement("p");
        value.className = "toast-value";
        value.textContent = info ? info.fmt() : "";

        const cause = document.createElement("p");
        cause.className = "toast-cause";
        cause.textContent = info ? info.cause() : "";

        const close = document.createElement("button");
        close.type = "button";
        close.className = "toast-close";
        close.setAttribute("aria-label", "Cerrar notificación");
        close.textContent = "✕";
        close.addEventListener("click", () => dismiss(node));

        const timer = document.createElement("span");
        timer.className = "toast-timer";
        timer.setAttribute("aria-hidden", "true");
        timer.style.animationDuration = ms + "ms";

        node.append(head, title, value, cause, close, timer);
        node._dismissTimer = setTimeout(() => dismiss(node), ms);
        return node;
    }

    /* ---------- 4. API ---------- */
    function notifyAlert(key, sev) {
        if (!ui.alerts.enabled || sev < 1) return;
        if (ui.alerts.priority === "critica" && sev < 2) return;   // solo rojas

        // Misma métrica sin empeorar dentro de la ventana: no repetir.
        const now = Date.now();
        const prev = lastNotified[key];
        if (prev && now - prev.at < RATE_LIMIT_MS && sev <= prev.sev) return;
        lastNotified[key] = { sev, at: now };

        playAlertSound(sev);
        if (!ui.alerts.methods.screen) return;   // método "pantalla" desactivado

        const root = getStack();
        while (root.children.length >= MAX_VISIBLE) dismiss(root.firstElementChild, true);
        root.appendChild(buildToast(key, sev));
    }

    window.notifyAlert = notifyAlert;
})();
