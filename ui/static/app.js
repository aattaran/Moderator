(function () {
  "use strict";

  const STORAGE_KEY = "ugc-ui-last";
  const PLATFORM_ASPECT = {
    instagram: "9:16", tiktok: "9:16", youtube: "9:16",
    facebook: "16:9", x: "16:9",
  };
  const state = {
    products: [],
    selectedActor: null,
    selectedScene: null,
    eventSource: null,
    currentJobId: null,
    userScrolled: false,
  };

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${url} -> ${res.status}`);
    return res.json();
  }

  // ---------- Populators ----------

  function fillSelect(el, items, withRandom) {
    if (!el) return;
    el.innerHTML = "";
    if (withRandom) {
      const o = document.createElement("option");
      o.value = "random"; o.textContent = "Random"; o.selected = true;
      el.appendChild(o);
    }
    for (const item of items) {
      const o = document.createElement("option");
      if (typeof item === "string") { o.value = item; o.textContent = item; }
      else { o.value = item.key || item.value || item.id; o.textContent = item.name || item.label || o.value; }
      el.appendChild(o);
    }
  }

  function rebuildTopics() {
    const productKey = $("#product").value;
    const product = state.products.find((p) => p.key === productKey);
    const sel = $("#topic");
    const topicField = $("#topic-field");
    const customField = $("#custom-product-field");

    if (productKey === "custom") {
      // For custom product: hide topic dropdown, show description textarea
      if (topicField) topicField.hidden = true;
      if (customField) customField.hidden = false;
      sel.innerHTML = '<option value="custom">custom</option>';
      return;
    }

    if (topicField) topicField.hidden = false;
    if (customField) customField.hidden = true;
    sel.innerHTML = "";
    if (!product) return;
    for (const t of (product.topics || [])) {
      const o = document.createElement("option");
      o.value = typeof t === "string" ? t : t.key;
      o.textContent = typeof t === "string" ? t : (t.name || t.key);
      sel.appendChild(o);
    }
  }

  async function loadOptions() {
    const opts = await fetchJSON("/api/options");
    state.products = opts.products || [];
    fillSelect($("#product"), state.products);
    rebuildTopics();
    fillSelect($("#platform"), opts.platforms || []);
    fillSelect($("#style_key"), opts.styles || [], true);
    fillSelect($("#concept_key"), opts.concepts || [], true);
    fillSelect($("#visual_hook_key"), opts.visual_hooks || [], true);
    fillSelect($("#kling_model"), opts.kling_models || []);
  }

  // ---------- Asset grids ----------

  function makeCard(item, onClick) {
    const card = document.createElement("div");
    card.className = "asset-card";
    card.dataset.id = item.id;
    card.title = item.name || item.id;
    if (item.thumb_url) {
      const img = document.createElement("img");
      img.src = item.thumb_url; img.alt = item.name || item.id; img.loading = "lazy";
      card.appendChild(img);
    } else {
      const ph = document.createElement("span");
      ph.textContent = item.name || item.id;
      card.appendChild(ph);
    }
    if (item.photo_count != null) {
      const b = document.createElement("span");
      b.className = "badge"; b.textContent = item.photo_count + " pics";
      card.appendChild(b);
    }
    const lbl = document.createElement("span");
    lbl.className = "label"; lbl.textContent = item.name || item.id;
    card.appendChild(lbl);
    card.addEventListener("click", () => onClick(item.id));
    return card;
  }

  function renderActorGrid(actors) {
    const grid = $("#actor-grid");
    grid.innerHTML = "";
    if (!actors || !actors.length) {
      grid.innerHTML = '<div class="loading">No actors found.</div>';
      return;
    }
    for (const a of actors) grid.appendChild(makeCard(a, selectActor));
  }

  function renderSceneGrid(scenes) {
    const grid = $("#scene-grid");
    grid.innerHTML = "";
    state.selectedScene = null;
    $("#scene_id").value = "";
    if (!scenes || !scenes.length) {
      grid.innerHTML = '<div class="loading">No scenes for this aspect.</div>';
      return;
    }
    for (const s of scenes) grid.appendChild(makeCard(s, selectScene));
  }

  function selectActor(id) {
    state.selectedActor = id;
    $("#actor_id").value = id;
    $$("#actor-grid .asset-card").forEach((c) =>
      c.classList.toggle("selected", c.dataset.id === String(id)));
    $("#submit-btn").disabled = false;
  }

  function selectScene(id) {
    state.selectedScene = id;
    $("#scene_id").value = id;
    $$("#scene-grid .asset-card").forEach((c) =>
      c.classList.toggle("selected", c.dataset.id === String(id)));
  }

  async function loadActors() {
    try { renderActorGrid(await fetchJSON("/api/assets/actors")); }
    catch (e) { $("#actor-grid").innerHTML = '<div class="loading">Failed to load actors.</div>'; }
  }
  async function loadScenes(aspect) {
    try { renderSceneGrid(await fetchJSON("/api/assets/scenes?aspect=" + encodeURIComponent(aspect))); }
    catch (e) { $("#scene-grid").innerHTML = '<div class="loading">Failed to load scenes.</div>'; }
  }

  // ---------- Reactive ----------

  const getCurrentAspect = () => (document.querySelector('input[name="aspect"]:checked') || {}).value || "9:16";
  function setAspect(v) {
    const r = document.querySelector(`input[name="aspect"][value="${v}"]`);
    if (r) r.checked = true;
  }

  function showScenePanel() {
    const kind = (document.querySelector('input[name="scene_kind"]:checked') || {}).value || "image";
    $("#scene-panel-image").hidden = kind !== "image";
    $("#scene-panel-description").hidden = kind !== "description";
    $("#scene-panel-none").hidden = kind !== "none";
  }

  function updateSubmitLabel() {
    const btn = $("#submit-btn");
    if (!btn) return;
    let text;
    if ($("#dry_run").checked) text = "Generate preview (no Kling)";
    else if ($("#preview_gate").checked) text = "Generate angle \u2192 review";
    else text = "Generate full video";
    btn.textContent = text;
  }

  async function updateCost() {
    const payload = {
      clip_count: Number($("#clip_count").value) || 3,
      clip_duration: Number($("#clip_duration").value) || 8,
      resolution: $('input[name="resolution"]:checked').value,
    };
    try {
      const data = await fetchJSON("/api/cost-estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const el = $("#cost-estimate");
      if (data.breakdown_str) el.textContent = data.breakdown_str;
      else if (data.total != null) el.textContent = `Est. ~$${Number(data.total).toFixed(2)}`;
    } catch (e) { /* server may not implement yet */ }
  }

  // ---------- Persistence ----------

  function snapshotForm() {
    const data = {};
    for (const el of $("#run-form").elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") data[el.name] = el.checked;
      else if (el.type === "radio") { if (el.checked) data[el.name] = el.value; }
      else data[el.name] = el.value;
    }
    return data;
  }

  function hydrateForm() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    let data;
    try { data = JSON.parse(raw); } catch (e) { return; }
    const skip = new Set(["actor_id", "scene_id"]);
    for (const [key, val] of Object.entries(data)) {
      if (skip.has(key)) continue;
      const els = document.getElementsByName(key);
      if (!els.length) continue;
      const first = els[0];
      if (first.type === "checkbox") first.checked = !!val;
      else if (first.type === "radio") {
        for (const el of els) if (el.value === val) el.checked = true;
      } else first.value = val;
    }
    rebuildTopics();
    if (data.topic) { const t = $("#topic"); if (t) t.value = data.topic; }
  }

  // ---------- Wire ----------

  function wire() {
    $("#product").addEventListener("change", rebuildTopics);
    $("#platform").addEventListener("change", () => {
      const def = PLATFORM_ASPECT[$("#platform").value];
      if (def) { setAspect(def); loadScenes(def); }
      updateCost();
    });
    $$('input[name="aspect"]').forEach((r) => r.addEventListener("change", () => {
      loadScenes(getCurrentAspect()); updateCost();
    }));
    $$('input[name="scene_kind"]').forEach((r) => r.addEventListener("change", showScenePanel));
    $("#dry_run").addEventListener("change", updateSubmitLabel);
    $("#preview_gate").addEventListener("change", updateSubmitLabel);
    $("#cfg_scale").addEventListener("input", () => {
      $("#cfg_scale_val").textContent = Number($("#cfg_scale").value).toFixed(2);
    });
    $("#run-form").addEventListener("change", updateCost);
    $("#run-form").addEventListener("submit", onSubmit);
    $("#reset-btn").addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      location.reload();
    });
    const panel = $("#status-panel");
    if (panel) {
      panel.addEventListener("scroll", () => {
        const atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 6;
        state.userScrolled = !atBottom;
      });
    }
    const closeBtn = $("#status-close");
    if (closeBtn) closeBtn.addEventListener("click", hideStatusPanel);
    // Preview modal wiring (Phase 4)
    const mClose = $("#preview-close");
    const mAbort = $("#preview-abort");
    const mConfirm = $("#preview-confirm");
    if (mClose) mClose.addEventListener("click", () => abortRun(state.currentJobId));
    if (mAbort) mAbort.addEventListener("click", () => abortRun(state.currentJobId));
    if (mConfirm) mConfirm.addEventListener("click", () => confirmRun(state.currentJobId));
  }

  // ---------- Preview modal (Phase 4) ----------

  function showPreviewModal(data) {
    const modal = $("#preview-modal");
    if (!modal) return;
    const img = $("#preview-frame");
    if (img) {
      // Cache-bust so the modal gets the newly-written frame
      img.src = (data.frame_url || "") + "?t=" + Date.now();
    }
    const parts = [data.angle_style, data.angle_concept, data.angle_visual_hook]
      .filter(Boolean)
      .join(" \u00d7 ");
    const angleEl = $("#preview-angle");
    if (angleEl) angleEl.textContent = parts || "(unknown)";
    const clipsEl = $("#preview-clips");
    if (clipsEl) clipsEl.textContent = `${data.clip_count} \u00d7 ${data.clip_duration}s`;
    const costEl = $("#preview-cost");
    if (costEl) {
      const c = data.cost || {};
      costEl.textContent = c.breakdown_str || (c.total != null ? `Est. ~$${Number(c.total).toFixed(2)}` : "");
    }
    modal.hidden = false;
  }

  function hidePreviewModal() {
    const modal = $("#preview-modal");
    if (modal) modal.hidden = true;
  }

  async function confirmRun(jobId) {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(jobId)}/confirm`, { method: "POST" });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        appendLogLine({ ts: new Date().toISOString(), level: "ERROR", msg: `confirm failed: ${res.status} ${body}` });
        return;
      }
      hidePreviewModal();
      appendLogLine({ ts: new Date().toISOString(), level: "INFO", msg: "preview confirmed \u2014 running Kling" });
    } catch (err) {
      appendLogLine({ ts: new Date().toISOString(), level: "ERROR", msg: "confirm network error: " + err.message });
    }
  }

  async function abortRun(jobId) {
    if (!jobId) { hidePreviewModal(); return; }
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(jobId)}/abort`, { method: "POST" });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        appendLogLine({ ts: new Date().toISOString(), level: "ERROR", msg: `abort failed: ${res.status} ${body}` });
        return;
      }
      hidePreviewModal();
      appendLogLine({ ts: new Date().toISOString(), level: "WARN", msg: "aborted \u2014 no Kling spend" });
      const btn = $("#submit-btn");
      if (btn) btn.disabled = !state.selectedActor;
    } catch (err) {
      appendLogLine({ ts: new Date().toISOString(), level: "ERROR", msg: "abort network error: " + err.message });
    }
  }

  // ---------- Run submission + SSE streaming ----------

  function buildRunRequest() {
    const f = $("#run-form");
    const pick = (name) => {
      const el = f.elements[name];
      if (!el) return "";
      if (el.length && el[0] && el[0].type === "radio") {
        for (const r of el) if (r.checked) return r.value;
        return "";
      }
      return el.value;
    };
    const sceneKind = pick("scene_kind") || "image";
    const out = {
      product: pick("product"),
      topic: pick("topic"),
      platform: pick("platform"),
      actor_id: $("#actor_id").value,
      actor_gender: pick("actor_gender"),
      clip_count: Number($("#clip_count").value) || 3,
      clip_duration: Number($("#clip_duration").value) || 8,
      aspect_ratio: pick("aspect"),
      resolution: pick("resolution"),
      style_key: pick("style_key") || "random",
      concept_key: pick("concept_key") || "random",
      visual_hook_key: pick("visual_hook_key") || "random",
      dry_run: $("#dry_run").checked,
      preview_gate: $("#preview_gate").checked,
      kling_model: pick("kling_model") || "kling-v3",
      cfg_scale: Number($("#cfg_scale").value),
      sound: pick("sound") || "on",
      tts_voice: ($("#tts_voice").value || "").trim() || null,
      pose: pick("pose") || null,
      bottle_closeup: pick("bottle_closeup") || null,
      multi_shot: $("#multi_shot").checked,
      extend_clips: $("#extend_clips").checked,
      extra_prompt: ($("#extra_prompt").value || "").trim() || null,
      product_description: ($("#product_description").value || "").trim() || null,
      scene_id: null,
      scene_description: null,
    };
    if (sceneKind === "image") {
      out.scene_id = $("#scene_id").value || null;
    } else if (sceneKind === "description") {
      out.scene_description = ($("#scene_description").value || "").trim() || null;
    }
    return out;
  }

  function hideStatusPanel() {
    closeEventSource();
    hidePreviewModal();
    const panel = $("#status-panel");
    if (!panel) return;
    panel.hidden = true;
    const log = $("#status-log");
    if (log) log.textContent = "";
    const vp = $("#video-preview");
    if (vp) vp.innerHTML = "";
    state.userScrolled = false;
    const btn = $("#submit-btn");
    if (btn && state.selectedActor) btn.disabled = false;
  }

  function showStatusPanel() {
    const panel = $("#status-panel");
    if (!panel) return;
    panel.hidden = false;
    const log = $("#status-log");
    if (log) log.textContent = "";
    const vp = $("#video-preview");
    if (vp) vp.innerHTML = "";
    state.userScrolled = false;
  }

  function appendLogLine(item) {
    const log = $("#status-log");
    if (!log) return;
    const panel = $("#status-panel");
    const line = document.createElement("div");
    const level = (item.level || "INFO").toUpperCase();
    line.className = "log-line log-" + level.toLowerCase();
    let stamp = "";
    try {
      const d = new Date(item.ts);
      stamp = d.toTimeString().slice(0, 8);
    } catch (e) { stamp = ""; }
    line.textContent = `[${stamp}] ${level} ${item.msg || ""}`;
    log.appendChild(line);
    if (panel && !state.userScrolled) panel.scrollTop = panel.scrollHeight;
  }

  function closeEventSource() {
    if (state.eventSource) {
      try { state.eventSource.close(); } catch (e) {}
      state.eventSource = null;
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!state.selectedActor) { alert("Pick an actor first."); return; }
    const payload0 = buildRunRequest();
    if (payload0.product === "custom" && !payload0.product_description) {
      alert("Product description is required for custom product.");
      return;
    }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshotForm())); } catch (err) {}

    const payload = buildRunRequest();
    const btn = $("#submit-btn");
    btn.disabled = true;

    let res;
    try {
      res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      alert("Network error: " + err.message);
      btn.disabled = false;
      return;
    }

    if (res.status === 409) {
      let body = {};
      try { body = await res.json(); } catch (e) {}
      const current = (body.detail && body.detail.current) || "unknown";
      alert(`A run is already in progress: ${current}`);
      btn.disabled = false;
      return;
    }
    if (res.status === 422) {
      let body = {};
      try { body = await res.json(); } catch (e) {}
      alert("Invalid request:\n" + JSON.stringify(body.detail || body, null, 2));
      btn.disabled = false;
      return;
    }
    if (!res.ok) {
      alert(`Server error: ${res.status}`);
      btn.disabled = false;
      return;
    }

    const data = await res.json();
    const jobId = data.job_id;
    state.currentJobId = jobId;
    showStatusPanel();
    appendLogLine({ ts: new Date().toISOString(), level: "INFO", msg: `run started: ${jobId}` });

    const es = new EventSource(`/api/runs/${encodeURIComponent(jobId)}/events`);
    state.eventSource = es;

    es.addEventListener("log", (ev) => {
      try {
        const item = JSON.parse(ev.data);
        appendLogLine(item);
      } catch (err) { /* ignore */ }
    });
    es.addEventListener("preview_ready", (ev) => {
      try {
        const data = JSON.parse(ev.data);
        appendLogLine({ ts: data.ts || new Date().toISOString(), level: "INFO", msg: "preview ready \u2014 review before Kling spend" });
        showPreviewModal(data);
      } catch (err) { /* ignore */ }
    });
    es.addEventListener("heartbeat", () => { /* keep-alive */ });
    es.addEventListener("done", async (ev) => {
      appendLogLine({ ts: new Date().toISOString(), level: "INFO", msg: "Complete" });
      closeEventSource();
      btn.disabled = !state.selectedActor;
      // Phase 5: refresh history so the new row shows up immediately.
      try { loadHistory(); } catch (e) { /* non-fatal */ }
      if (!payload.dry_run) {
        try {
          const videoUrl = `/api/runs/${encodeURIComponent(jobId)}/video`;
          const probe = await fetch(videoUrl, { method: "GET" });
          if (probe.ok) {
            const vp = $("#video-preview");
            if (vp) {
              vp.innerHTML = "";
              const v = document.createElement("video");
              v.controls = true;
              v.src = videoUrl;
              vp.appendChild(v);
            }
          } else {
            appendLogLine({
              ts: new Date().toISOString(),
              level: "WARN",
              msg: `video not available (${probe.status})`,
            });
          }
        } catch (err) {
          appendLogLine({ ts: new Date().toISOString(), level: "ERROR", msg: "video fetch failed: " + err.message });
        }
      }
    });
    es.onerror = () => {
      appendLogLine({ ts: new Date().toISOString(), level: "WARN", msg: "SSE stream closed" });
      closeEventSource();
      btn.disabled = !state.selectedActor;
    };
  }

  // ---------- History panel (Phase 5) ----------

  function productKeyForTopic(topic) {
    if (!topic) return null;
    for (const p of state.products) {
      if ((p.topics || []).includes(topic)) return p.key;
    }
    return null;
  }

  function productNameForKey(key) {
    const p = state.products.find((x) => x.key === key);
    return p ? p.name : (key || "—");
  }

  function sinceToISO(val) {
    if (!val) return "";
    const now = Date.now();
    const map = { "24h": 24 * 3600e3, "7d": 7 * 86400e3, "30d": 30 * 86400e3 };
    const ms = map[val];
    if (!ms) return "";
    return new Date(now - ms).toISOString();
  }

  function hydrateFilterDropdowns() {
    const sel = $("#filter-product");
    if (!sel) return;
    // Keep "All" at the top; append product options once.
    if (sel.options.length > 1) return;
    for (const p of state.products) {
      const o = document.createElement("option");
      o.value = p.key; o.textContent = p.name || p.key;
      sel.appendChild(o);
    }
  }

  function fmtDate(ts) {
    if (!ts) return "—";
    try {
      // DB timestamps are local time (datetime.now().isoformat() — no tz suffix).
      // Replace space with T so the browser parses as local time, not UTC.
      const normalized = ts.includes("T") ? ts : ts.replace(" ", "T");
      const d = new Date(normalized);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString([], { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return ts; }
  }

  function parseAngle(row) {
    if (!row.angle_json) return {};
    try { return JSON.parse(row.angle_json) || {}; } catch (e) { return {}; }
  }

  function renderHistoryRow(row) {
    const tr = document.createElement("tr");
    const angle = parseAngle(row);
    const prodKey = productKeyForTopic(row.topic) || row.topic || "—";
    const prodName = productKeyForTopic(row.topic) ? productNameForKey(productKeyForTopic(row.topic)) : (row.topic || "—");
    const style = angle.style_name || "—";
    const concept = angle.concept || "—";
    const status = row.status || "—";

    const tdDate = document.createElement("td"); tdDate.textContent = fmtDate(row.started_at);
    const tdProd = document.createElement("td"); tdProd.textContent = prodName; tdProd.title = row.topic || "";
    const tdStyle = document.createElement("td"); tdStyle.textContent = style;
    const tdConcept = document.createElement("td"); tdConcept.textContent = concept;

    const tdStatus = document.createElement("td");
    const pill = document.createElement("span");
    pill.className = "status-pill status-" + String(status).replace(/[^a-z_]/gi, "_");
    pill.textContent = status;
    tdStatus.appendChild(pill);

    const tdAct = document.createElement("td");
    tdAct.className = "history-actions";

    const canPlay = status === "complete" && !!row.final_path;
    const playBtn = document.createElement("button");
    playBtn.type = "button";
    playBtn.className = "hist-btn hist-play";
    playBtn.textContent = "\u25B6 Play";
    playBtn.disabled = !canPlay;
    playBtn.addEventListener("click", () => openVideoModal(row.job_id));
    tdAct.appendChild(playBtn);

    const hasFrame = row.frame_status === "complete" || !!row.frame_path;
    const frameBtn = document.createElement("button");
    frameBtn.type = "button";
    frameBtn.className = "hist-btn hist-frame";
    frameBtn.textContent = "\uD83D\uDDBC Frame";
    frameBtn.disabled = !hasFrame;
    frameBtn.addEventListener("click", () => openFrameModal(row.job_id));
    tdAct.appendChild(frameBtn);

    const rerunBtn = document.createElement("button");
    rerunBtn.type = "button";
    rerunBtn.className = "hist-btn hist-rerun";
    rerunBtn.textContent = "\u21bb Re-run";
    rerunBtn.addEventListener("click", () => prefillFromRow(row));
    tdAct.appendChild(rerunBtn);

    if (status === "awaiting_confirmation") {
      const confirmBtn = document.createElement("button");
      confirmBtn.type = "button";
      confirmBtn.className = "hist-btn hist-confirm";
      confirmBtn.textContent = "\u2713 Confirm";
      confirmBtn.addEventListener("click", async () => {
        confirmBtn.disabled = true;
        await confirmRun(row.job_id);
        loadHistory();
      });
      tdAct.appendChild(confirmBtn);

      const abortBtn = document.createElement("button");
      abortBtn.type = "button";
      abortBtn.className = "hist-btn hist-abort";
      abortBtn.textContent = "\u2715 Abort";
      abortBtn.addEventListener("click", async () => {
        abortBtn.disabled = true;
        await abortRun(row.job_id);
        loadHistory();
      });
      tdAct.appendChild(abortBtn);
    }

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "hist-btn hist-del";
    delBtn.textContent = "\u{1F5D1} Delete";
    delBtn.addEventListener("click", () => deleteRow(row.job_id));
    tdAct.appendChild(delBtn);

    tr.appendChild(tdDate);
    tr.appendChild(tdProd);
    tr.appendChild(tdStyle);
    tr.appendChild(tdConcept);
    tr.appendChild(tdStatus);
    tr.appendChild(tdAct);
    return tr;
  }

  let _historyPollTimer = null;
  let _confirmAlertJobId = null;

  function _startHistoryPoll() {
    if (_historyPollTimer) return;
    _historyPollTimer = setInterval(async () => {
      await loadHistory();
    }, 4000);
  }

  function _stopHistoryPoll() {
    if (_historyPollTimer) { clearInterval(_historyPollTimer); _historyPollTimer = null; }
  }

  function _showConfirmAlert(jobId) {
    if (_confirmAlertJobId === jobId) return;
    _confirmAlertJobId = jobId;
    const alert = $("#confirm-alert");
    if (!alert) return;
    const confirmBtn = $("#alert-confirm-btn");
    const abortBtn = $("#alert-abort-btn");
    // Replace listeners by cloning
    if (confirmBtn) {
      const c = confirmBtn.cloneNode(true);
      c.addEventListener("click", async () => { c.disabled = true; await confirmRun(jobId); _hideConfirmAlert(); loadHistory(); });
      confirmBtn.replaceWith(c);
    }
    if (abortBtn) {
      const a = abortBtn.cloneNode(true);
      a.addEventListener("click", async () => { a.disabled = true; await abortRun(jobId); _hideConfirmAlert(); loadHistory(); });
      abortBtn.replaceWith(a);
    }
    alert.style.display = "flex";
    alert.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function _hideConfirmAlert() {
    _confirmAlertJobId = null;
    const alert = $("#confirm-alert");
    if (alert) alert.style.display = "none";
  }

  async function loadHistory() {
    const tbody = $("#history-rows");
    if (!tbody) return;
    // Always check all jobs for awaiting_confirmation regardless of current filter
    let allRows = [];
    try {
      allRows = await fetchJSON("/api/runs?limit=50") || [];
    } catch (e) { /* ignore */ }
    const awaitingJob = allRows.find(r => r.status === "awaiting_confirmation");
    if (awaitingJob) _showConfirmAlert(awaitingJob.job_id);
    else _hideConfirmAlert();

    const product = $("#filter-product").value;
    const status = $("#filter-status").value;
    const since = sinceToISO($("#filter-since").value);
    const qs = new URLSearchParams();
    if (product) qs.set("product", product);
    if (status) qs.set("status", status);
    if (since) qs.set("since", since);
    qs.set("limit", "50");
    try {
      const rows = await fetchJSON("/api/runs?" + qs.toString());
      tbody.innerHTML = "";
      if (!rows || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No runs yet</td></tr>';
        _stopHistoryPoll();
        return;
      }
      for (const row of rows) tbody.appendChild(renderHistoryRow(row));
      const hasActive = allRows.some(r => r.status === "running" || r.status === "awaiting_confirmation");
      if (hasActive) _startHistoryPoll(); else _stopHistoryPoll();
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Failed to load history</td></tr>';
    }
  }

  function openVideoModal(jobId) {
    const modal = $("#video-modal");
    const player = $("#video-modal-player");
    const frameImg = $("#video-modal-frame");
    const title = $("#video-modal-title");
    if (!modal || !player) return;
    if (frameImg) { frameImg.style.display = "none"; frameImg.removeAttribute("src"); }
    player.style.display = "";
    player.src = `/api/runs/${encodeURIComponent(jobId)}/video?t=${Date.now()}`;
    if (title) title.textContent = "Playback";
    modal.hidden = false;
    try { player.play(); } catch (e) {}
  }

  function openFrameModal(jobId) {
    const modal = $("#video-modal");
    const player = $("#video-modal-player");
    const frameImg = $("#video-modal-frame");
    const title = $("#video-modal-title");
    if (!modal || !frameImg) return;
    if (player) { try { player.pause(); } catch (e) {} player.removeAttribute("src"); player.style.display = "none"; }
    frameImg.src = `/api/runs/${encodeURIComponent(jobId)}/frame?t=${Date.now()}`;
    frameImg.style.display = "";
    if (title) title.textContent = "Start Frame";
    modal.hidden = false;
  }

  function closeVideoModal() {
    const modal = $("#video-modal");
    const player = $("#video-modal-player");
    const frameImg = $("#video-modal-frame");
    if (player) { try { player.pause(); } catch (e) {} player.removeAttribute("src"); player.load && player.load(); player.style.display = ""; }
    if (frameImg) { frameImg.removeAttribute("src"); frameImg.style.display = "none"; }
    if (modal) modal.hidden = true;
  }

  async function deleteRow(jobId) {
    if (!confirm("Delete this run and its files?")) return;
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        alert(`Delete failed: ${res.status} ${body}`);
        return;
      }
      await loadHistory();
    } catch (e) {
      alert("Network error: " + e.message);
    }
  }

  function prefillFromRow(row) {
    let params = {};
    if (row.run_params_json) {
      try { params = JSON.parse(row.run_params_json) || {}; } catch (e) { params = {}; }
    }
    if (!Object.keys(params).length) {
      alert("This run has no saved parameters to re-run.");
      return;
    }
    const form = $("#run-form");
    if (!form) return;

    // Special-cased fields the form doesn't use [name=] for.
    if (params.actor_id) {
      selectActor(params.actor_id);
    }
    // Scene kind toggle
    let sceneKind = "image";
    if (params.scene_description) sceneKind = "description";
    else if (!params.scene_id && !params.scene_description) sceneKind = "none";
    const sceneRadio = document.querySelector(`input[name="scene_kind"][value="${sceneKind}"]`);
    if (sceneRadio) { sceneRadio.checked = true; showScenePanel(); }

    // Walk remaining keys and set by [name]
    const skipKeys = new Set(["actor_id", "scene_kind"]);
    for (const [key, val] of Object.entries(params)) {
      if (skipKeys.has(key)) continue;
      if (val == null) continue;
      // Form field name may be `aspect` vs param `aspect_ratio`
      const fieldName = key === "aspect_ratio" ? "aspect" : key;
      const els = document.getElementsByName(fieldName);
      if (!els.length) continue;
      const first = els[0];
      if (first.type === "checkbox") {
        first.checked = !!val;
      } else if (first.type === "radio") {
        for (const el of els) if (String(el.value) === String(val)) el.checked = true;
      } else {
        first.value = val;
      }
    }

    // Topic depends on product; rebuild then set.
    if (params.product) {
      const prodSel = $("#product");
      if (prodSel) { prodSel.value = params.product; rebuildTopics(); }
    }
    if (params.topic) {
      const topSel = $("#topic");
      if (topSel) topSel.value = params.topic;
    }
    // Custom product: restore description textarea
    if (params.product_description) {
      const pd = $("#product_description");
      if (pd) pd.value = params.product_description;
    }
    // cfg_scale slider companion label
    if (params.cfg_scale != null) {
      const v = Number(params.cfg_scale);
      if (!Number.isNaN(v)) $("#cfg_scale_val").textContent = v.toFixed(2);
    }

    updateSubmitLabel();
    updateCost();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function wireHistory() {
    const refresh = $("#history-refresh");
    if (refresh) refresh.addEventListener("click", loadHistory);
    for (const id of ["filter-product", "filter-status", "filter-since"]) {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", loadHistory);
    }
    // Video modal close handlers (also reused by history Play button modal).
    for (const el of $$("[data-close-modal='video-modal']")) {
      el.addEventListener("click", closeVideoModal);
    }
  }

  // ---------- Boot ----------

  async function init() {
    wire();
    wireHistory();
    try { await loadOptions(); } catch (e) { console.error("loadOptions failed", e); }
    hydrateForm();
    hydrateFilterDropdowns();
    showScenePanel();
    updateSubmitLabel();
    $("#cfg_scale_val").textContent = Number($("#cfg_scale").value).toFixed(2);
    const platVal = $("#platform").value;
    if (platVal && PLATFORM_ASPECT[platVal] && !localStorage.getItem(STORAGE_KEY)) {
      setAspect(PLATFORM_ASPECT[platVal]);
    }
    await Promise.all([loadActors(), loadScenes(getCurrentAspect())]);
    updateCost();
    await loadHistory();
    _startHistoryPoll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
