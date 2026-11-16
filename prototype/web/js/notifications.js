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
    const SOUND_GAP_MS = 4000;                     // agrupa ráfagas de alertas

    const lastNotified = {};
    let lastSoundAt = 0;
    let stack = null;

    /* ---------- SONIDO DESDE ARCHIVO ---------- */
    const ALERT_SOUND_SRC = "/sounds/sound_alert.mp3";  // cambia el nombre si el tuyo es otro
    const ALERT_VOLUME = 0.8;                     // de 0 a 1
    const ALERT_REPEATS = 2;                      // cuántas veces suena

    const alertAudio = new Audio(ALERT_SOUND_SRC);
    alertAudio.preload = "auto";
    alertAudio.volume = ALERT_VOLUME;

    let repeatsLeft = 0;
    alertAudio.addEventListener("ended", () => {
        if (repeatsLeft > 0) {
            repeatsLeft--;
            alertAudio.currentTime = 0;
            alertAudio.play().catch(() => {});
        }
    });

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
        alertAudio.muted = true;
        alertAudio.play()
            .then(() => { alertAudio.pause(); alertAudio.currentTime = 0; alertAudio.muted = false; })
            .catch(() => { audioUnlocked = false; alertAudio.muted = false; });
    }
    document.addEventListener("pointerdown", unlockAudio, { passive: true });
    //document.addEventListener("keydown", unlockAudio);

    function playAlertSound(sev) {
        if (!ui.alerts.sound) return;
        const now = performance.now();
        if (now - lastSoundAt < SOUND_GAP_MS) return;

        repeatsLeft = ALERT_REPEATS - 1;
        alertAudio.currentTime = 0;
        alertAudio.play()
            .then(() => { lastSoundAt = now; })
            .catch(err => console.warn("Audio bloqueado o no encontrado:", err));
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
