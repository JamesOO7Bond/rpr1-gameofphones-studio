/* RPR1. Game of Phones – Studio-Dashboard (Browser-Teil) */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = {
    dot: $("status-dot"), label: $("status-label"), hint: $("status-hint"),
    timer: $("timer"), name: $("name"), ort: $("ort"),
    start: $("btn-start"), startText: $("btn-start-text"),
    mute: $("btn-mute"), muteText: $("btn-mute-text"), micOn: $("icon-mic-on"), micOff: $("icon-mic-off"),
    end: $("btn-end"), message: $("message"), rounds: $("rounds"),
    inputDev: $("input-device"), outputDev: $("output-device"),
    go: $("btn-go"), goText: $("btn-go-text"),
    badgeNet: $("badge-net"), badgeNetText: $("badge-net-text"),
    footerVersion: $("footer-version"), footerConn: $("footer-conn"),
  };

  let conversation = null;
  let conversationId = null;
  let planned = [];
  let muted = false;          // manuell über den Stumm-Knopf
  let agentSpeaking = false;
  let autoMuted = false;      // automatisch, weil die KI spricht
  const noInterrupt = $("no-interrupt");
  try { noInterrupt.checked = localStorage.getItem("gop.noInterrupt") !== "0"; } catch (e) { noInterrupt.checked = true; }
  let timerHandle = null;
  let startedAt = 0;
  let mock = false;

  // Startbefehl der KI, identisch zum gesprochenen Befehl. Der Knopf „Runde starten“
  // schickt ihn als Text und umgeht damit die Turn-Erkennung der Sprache.
  const START_COMMAND = "Hey Siri, starte das RPR1 Game of Phones.";
  const GO_TIMEOUT_MS = 10000;
  let roundStarted = false;   // KI hat zu sprechen begonnen (per Knopf oder per Zuruf)
  let goTimer = null;

  // ----- Hilfen ----------------------------------------------------------
  function setStatus(kind, label, hint) {
    el.dot.className = "dot-status" + (kind ? " " + kind : "");
    el.label.textContent = label;
    el.hint.textContent = hint;
  }
  function showMessage(text, info) {
    if (!text) { el.message.classList.add("hidden"); el.message.textContent = ""; return; }
    el.message.textContent = text;
    el.message.classList.toggle("info", !!info);
    el.message.classList.remove("hidden");
  }
  function fmt(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }
  function startTimer() {
    startedAt = Date.now();
    el.timer.textContent = "00:00";
    timerHandle = setInterval(() => {
      el.timer.textContent = fmt(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
  }
  function stopTimer() { if (timerHandle) clearInterval(timerHandle); timerHandle = null; }
  function setMuteUi(isMuted) {
    muted = isMuted;
    el.mute.setAttribute("aria-pressed", isMuted ? "true" : "false");
    el.muteText.textContent = isMuted ? "Mikro an" : "Stumm";
    el.micOn.classList.toggle("hidden", isMuted);
    el.micOff.classList.toggle("hidden", !isMuted);
  }
  function setLiveUi(live) {
    el.start.disabled = live;
    el.start.classList.remove("busy");
    el.startText.textContent = "Start";
    el.mute.disabled = !live;
    el.end.disabled = !live;
    el.name.disabled = live;
    el.ort.disabled = live;
    setGoUi(live ? "ready" : "off");
  }
  // Knopf „Runde starten“: off (nicht verbunden) | ready | sending | running (KI spricht, Runde läuft)
  function setGoUi(state) {
    el.go.disabled = state !== "ready";
    el.go.classList.toggle("busy", state === "sending");
    el.go.classList.toggle("running", state === "running");
    el.goText.textContent = state === "sending" ? "Sende …" : state === "running" ? "Runde läuft" : "Runde starten";
  }
  function clearGoTimer() { if (goTimer) clearTimeout(goTimer); goTimer = null; }
  function startRound() {
    if (!conversation || roundStarted || el.go.disabled) return;
    showMessage("");
    setGoUi("sending");
    try {
      conversation.sendUserMessage(START_COMMAND);
    } catch (e) {
      setGoUi("ready");
      showMessage("Startbefehl konnte nicht gesendet werden: " + e.message + ". Alternativ den Befehl sprechen.");
      return;
    }
    // Reagiert die KI nicht, den Knopf wieder freigeben (kein stilles Hängen)
    clearGoTimer();
    goTimer = setTimeout(() => {
      goTimer = null;
      if (conversation && !roundStarted) {
        setGoUi("ready");
        showMessage("Die KI hat noch nicht geantwortet. Noch einmal drücken oder den Befehl sprechen.", true);
      }
    }, GO_TIMEOUT_MS);
  }
  // Wird bei jedem Moduswechsel der KI aufgerufen. Das erste Sprechen = Runde gestartet,
  // egal ob per Knopf oder per Zuruf. Danach ist der Knopf gesperrt (kein zweiter Startbefehl mitten in der Runde).
  function handleMode(mode) {
    agentSpeaking = mode === "speaking";
    if (agentSpeaking && !roundStarted) {
      roundStarted = true;
      clearGoTimer();
      setGoUi("running");
      showMessage("");
    }
    applyMic();
  }
  async function api(path, body) {
    const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    const res = await fetch(path, opts);
    if (res.status === 401) { window.location.href = "/login"; throw new Error("Zugangscode fehlt"); }
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || j.fehler || detail; } catch (e) { /* leer */ }
      throw new Error(detail);
    }
    return res.json();
  }

  // ----- Zustand laden ---------------------------------------------------
  function renderRounds(rounds) {
    if (!rounds || !rounds.length) { el.rounds.innerHTML = '<div class="muted">Noch keine Runden.</div>'; return; }
    el.rounds.innerHTML = "";
    for (const r of rounds) {
      const d = new Date(r.start_time * 1000);
      const time = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
      const day = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
      const who = [r.kandidat_name, r.kandidat_ort].filter(Boolean).join(", ") || "Kandidat unbekannt";
      const parts = [r.kategorie, r.loesung, r.region].filter(Boolean);
      let result = "";
      if (r.ergebnis) {
        const ok = /richtig/i.test(r.ergebnis);
        result = '<span class="' + (ok ? "ok" : "fail") + '">' + escapeHtml(r.ergebnis) + "</span>";
      } else if (r.status === "offen") {
        result = '<span class="muted">läuft / Auswertung ausstehend</span>';
      } else if (r.status === "ohne_analyse") {
        result = '<span class="muted">ohne Auswertung</span>';
      }
      const row = document.createElement("div");
      row.className = "round";
      row.innerHTML = '<span class="time" title="' + day + '">' + time + "</span>" +
        '<span><span class="who">' + escapeHtml(who) + "</span> " +
        '<span class="what">' + escapeHtml(parts.join(" · ")) + (parts.length ? " · " : "") + "</span>" + result + "</span>";
      el.rounds.appendChild(row);
    }
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function loadState() {
    try {
      const s = await api("/api/state");
      if (s.pool && !s.pool.fragen) showMessage("Fragenpool nicht geladen: " + (s.pool.fehler || "unbekannt") + ". Die KI nutzt dann ihre Wissensbasis.", true);
      renderRounds(s.rounds);
      el.footerVersion.textContent = "Studio-Dashboard " + s.version;
      el.footerConn.textContent = "Verbindung: " + s.connection_type + (s.code ? " · Zugangscode aktiv" : "");
      if (s.ip_filter) {
        el.badgeNet.classList.remove("warn");
        el.badgeNetText.textContent = "Nur ATSW-Netz";
      } else {
        el.badgeNet.classList.add("warn");
        el.badgeNetText.textContent = "IP-Sperre aus";
      }
    } catch (err) {
      showMessage("Zustand konnte nicht geladen werden: " + err.message);
    }
  }

  // ----- Audiogeräte -----------------------------------------------------
  async function loadDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      fillDevices(el.inputDev, devices.filter((d) => d.kind === "audioinput"), localStorage.getItem("gop.input") || "");
      fillDevices(el.outputDev, devices.filter((d) => d.kind === "audiooutput"), localStorage.getItem("gop.output") || "");
    } catch (e) { /* ohne Berechtigung keine Namen, egal */ }
  }
  function fillDevices(select, list, chosen) {
    select.innerHTML = "";
    const def = document.createElement("option");
    def.value = ""; def.textContent = "Standard des Browsers";
    select.appendChild(def);
    for (const d of list) {
      const o = document.createElement("option");
      o.value = d.deviceId; o.textContent = d.label || ("Gerät " + (select.options.length));
      select.appendChild(o);
    }
    select.value = chosen;
    if (select.value !== chosen) select.value = "";
  }
  el.inputDev.addEventListener("change", () => { try { localStorage.setItem("gop.input", el.inputDev.value); } catch (e) { /* leer */ } });
  el.outputDev.addEventListener("change", () => { try { localStorage.setItem("gop.output", el.outputDev.value); } catch (e) { /* leer */ } });
  $("refresh-devices").addEventListener("click", async () => {
    try { await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { /* abgelehnt */ }
    loadDevices();
  });

  // ----- Runde starten ---------------------------------------------------
  async function start() {
    showMessage("");
    el.start.disabled = true;
    el.start.classList.add("busy");
    el.startText.textContent = "Verbinde …";
    setStatus("busy", "Verbinde", "Signierte Sitzung wird geholt, Mikrofon wird geöffnet.");
    try {
      // Mikrofon im Klick öffnen, damit der Browser nicht blockt
      try { await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { throw new Error("Kein Mikrofonzugriff im Browser."); }
      const body = { name: el.name.value, ort: el.ort.value };
      const s = await api("/api/session", body);
      planned = s.planned || [];
      mock = !!s.mock;
      if (mock) {
        conversationId = "mock-" + Date.now();
        conversation = {
          setMicMuted: () => {},
          sendUserMessage: (text) => {
            window.__mockSent = (window.__mockSent || []).concat([text]);
            if (window.__mockNoReply) return;   // Test: KI antwortet nicht
            setTimeout(() => handleMode("speaking"), 400);
            setTimeout(() => handleMode("listening"), 2500);
          },
          endSession: async () => { onDisconnected({ reason: "user" }); },
        };
        await api("/api/rounds/register", { conversation_id: conversationId, planned: planned, name: el.name.value, ort: el.ort.value });
        onConnected();
        return;
      }
      if (!window.ElevenLabsClient || !window.ElevenLabsClient.Conversation) throw new Error("ElevenLabs-Bibliothek nicht geladen.");
      const opts = {
        connectionType: s.connection_type,
        dynamicVariables: s.dynamic_variables,
        onConnect: ({ conversationId: id }) => {
          conversationId = id;
          api("/api/rounds/register", { conversation_id: id, planned: planned, name: el.name.value, ort: el.ort.value }).catch(() => {});
          onConnected();
        },
        onDisconnect: (details) => onDisconnected(details),
        onError: (message) => showMessage("Fehler der Verbindung: " + message),
        onModeChange: ({ mode }) => handleMode(mode),
      };
      if (s.signed_url) opts.signedUrl = s.signed_url;
      if (s.conversation_token) opts.conversationToken = s.conversation_token;
      const inputId = el.inputDev.value, outputId = el.outputDev.value;
      if (inputId) opts.inputDeviceId = inputId;
      if (outputId) opts.outputDeviceId = outputId;
      conversation = await window.ElevenLabsClient.Conversation.startSession(opts);
    } catch (err) {
      conversation = null;
      setLiveUi(false);
      setStatus("", "Bereit", "KI ist nicht verbunden. Start drücken, wenn der Kandidat in der Leitung ist.");
      showMessage("Start fehlgeschlagen: " + err.message);
    }
  }

  function onConnected() {
    agentSpeaking = false;
    autoMuted = false;
    roundStarted = false;
    clearGoTimer();
    setMuteUi(false);
    setLiveUi(true);
    startTimer();
    setStatus("live", "Live · KI hört zu", "Verbunden. Off air den Kandidaten ansagen, dann „Runde starten“ drücken.");
    loadDevices();
  }

  async function onDisconnected(details) {
    stopTimer();
    const id = conversationId;
    conversation = null;
    roundStarted = false;
    clearGoTimer();
    setLiveUi(false);
    setMuteUi(false);
    const reason = details && details.reason ? details.reason : "";
    if (reason === "error") showMessage("Verbindung abgebrochen: " + (details.message || "unbekannter Fehler"));
    setStatus("busy", "Auswertung", "Gespräch beendet. Die Datenerfassung von ElevenLabs wird geholt …");
    if (id) {
      try { await api("/api/rounds/" + encodeURIComponent(id) + "/sync", {}); }
      catch (err) { showMessage("Auswertung noch nicht da: " + err.message, true); }
    }
    conversationId = null;
    setStatus("", "Bereit", "KI ist nicht verbunden. Start drücken, wenn der Kandidat in der Leitung ist.");
    el.timer.textContent = "00:00";
    await loadState();
  }

  // Mikro zur KI: zu, wenn manuell stumm ODER (Unterbrechungen aus UND KI spricht)
  function applyMic() {
    if (!conversation) return;
    const auto = noInterrupt.checked && agentSpeaking;
    const shouldMute = muted || auto;
    try { conversation.setMicMuted(shouldMute); } catch (e) { showMessage("Mikro schalten fehlgeschlagen: " + e.message); return; }
    autoMuted = auto && !muted;
    if (muted) setStatus("muted", "Mikro stumm", "Die KI hört gerade nichts. Zum Weiterspielen Mikro an.");
    else if (agentSpeaking && autoMuted) setStatus("live", "Live · KI spricht", "Mikro automatisch zu, Zwischenrufe unterbrechen nicht.");
    else if (agentSpeaking) setStatus("live", "Live · KI spricht", "Die KI redet gerade und lässt sich unterbrechen.");
    else setStatus("live", "Live · KI hört zu", "Verbunden mit dem Studio-Agenten.");
  }

  function toggleMute() {
    if (!conversation) return;
    setMuteUi(!muted);
    applyMic();
  }

  async function end() {
    if (!conversation) return;
    el.end.disabled = true;
    try { await conversation.endSession(); }
    catch (e) { showMessage("Beenden fehlgeschlagen: " + e.message); el.end.disabled = false; }
  }

  // ----- Verdrahtung -----------------------------------------------------
  el.start.addEventListener("click", start);
  el.go.addEventListener("click", startRound);
  el.mute.addEventListener("click", toggleMute);
  noInterrupt.addEventListener("change", () => {
    try { localStorage.setItem("gop.noInterrupt", noInterrupt.checked ? "1" : "0"); } catch (e) { /* leer */ }
    applyMic();
  });
  el.end.addEventListener("click", end);
  $("clear-candidate").addEventListener("click", () => { el.name.value = ""; el.ort.value = ""; });
  window.addEventListener("beforeunload", (e) => { if (conversation) { e.preventDefault(); e.returnValue = ""; } });

  setMuteUi(false);
  setLiveUi(false);
  loadState();
  loadDevices();
  setInterval(() => { if (!conversation) loadState(); }, 60000);
})();
