// Genesis dashboard. All server/model text is rendered with textContent (never innerHTML).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const STEPS = ["generating", "validating", "building", "repairing", "verifying"];
  const STAGE_LABEL = { queued: "Queued", generating: "Designing", validating: "Checking", building: "Compiling",
    repairing: "Repairing", verifying: "Verifying", succeeded: "Ready", failed: "Failed" };
  const CATEGORY = { calculator: "Calculator", habit_tracker: "Habit tracker", flashcards: "Flashcards",
    workout_tracker: "Workout", todo_list: "To-do" };
  const HEX = /^#[0-9a-fA-F]{6}$/;
  let currentId = null, pollTimer = null, lastLogLen = -1, lastStage = null;

  const el = (tag, props = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else n.setAttribute(k, v);
    }
    for (const c of children) if (c) n.append(c);
    return n;
  };

  async function api(path, opts = {}) {
    const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const ct = res.headers.get("content-type") || "";
    const body = ct.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) throw new Error((body && body.detail) || `Request failed (${res.status})`);
    return body;
  }

  function paintTile(node, name, color, building) {
    node.textContent = name ? name.trim().charAt(0).toUpperCase() : "✦";
    if (color && HEX.test(color)) node.style.setProperty("--tc", color); else node.style.removeProperty("--tc");
    node.classList.toggle("building", !!building);
  }

  function relTime(iso) {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
    return new Date(iso).toLocaleDateString();
  }

  // ---------- studio health ----------
  async function loadHealth() {
    const pill = $("envPill");
    try {
      const h = await api("/api/health");
      pill.className = "pill " + (h.ready ? "ok" : "bad");
      $("envText").textContent = h.ready ? `Studio ready · ${h.gemini_model}` : "Setup needed";
      const ul = el("ul");
      for (const c of h.checks) {
        const body = el("div", {}, el("strong", { text: c.name + " " }), el("span", { class: "muted", text: c.detail }));
        if (c.fix) body.append(el("div", { class: "fix", text: "Fix: " + c.fix }));
        ul.append(el("li", {}, el("span", { class: c.ok ? "ok" : "no", text: c.ok ? "✓" : "✕" }), body));
      }
      ul.append(el("li", {}, el("span", { class: h.gemini_model ? "ok" : "no", text: h.gemini_model ? "✓" : "✕" }),
        el("div", {}, el("strong", { text: "Gemini model " }), el("span", { class: "muted", text: h.gemini_model || h.gemini_error || "not configured" }))));
      $("envPanel").replaceChildren(ul);
      if (!h.ready) { $("envPanel").hidden = false; pill.setAttribute("aria-expanded", "true"); }
    } catch {
      pill.className = "pill bad";
      $("envText").textContent = "Studio unreachable";
    }
  }
  $("envPill").addEventListener("click", () => {
    const p = $("envPanel");
    p.hidden = !p.hidden;
    $("envPill").setAttribute("aria-expanded", String(!p.hidden));
  });

  // ---------- composer ----------
  const prompt = $("prompt");
  const updateCount = () => { $("charCount").textContent = `${prompt.value.length} / 4000`; };
  prompt.addEventListener("input", updateCount);
  prompt.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("buildForm").requestSubmit(); });
  document.querySelectorAll(".chip").forEach((c) =>
    c.addEventListener("click", () => { prompt.value = c.dataset.example; updateCount(); prompt.focus(); }));

  $("buildForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const err = $("formError");
    err.hidden = true;
    const text = prompt.value.trim();
    const appName = $("appName").value.trim();
    if (text.length < 10) { err.textContent = "Describe your app in a sentence or two."; err.hidden = false; return; }
    const btn = $("generateBtn");
    btn.disabled = true; btn.classList.add("loading");
    try {
      const job = await api("/api/builds", { method: "POST", body: JSON.stringify({ prompt: text, app_name: appName || null }) });
      prompt.value = ""; $("appName").value = ""; updateCount();
      selectBuild(job.id);
      loadHistory();
    } catch (e) {
      err.textContent = e.message; err.hidden = false;
    } finally {
      btn.disabled = false; btn.classList.remove("loading");
    }
  });

  // ---------- build view ----------
  function selectBuild(id) {
    currentId = id; lastLogLen = -1; lastStage = null;
    $("log").replaceChildren();
    $("buildCard").hidden = false;
    document.querySelectorAll(".app-card").forEach((b) => b.classList.toggle("selected", b.dataset.id === id));
    clearTimeout(pollTimer);
    poll();
    $("buildCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function poll() {
    if (!currentId) return;
    const id = currentId;
    try {
      const [job, log] = await Promise.all([api(`/api/builds/${id}`), api(`/api/builds/${id}/log`)]);
      if (id !== currentId) return;
      renderJob(job);
      renderLog(log);
      if (job.stage !== lastStage) { lastStage = job.stage; loadHistory(); }
      if (job.status !== "succeeded" && job.status !== "failed") pollTimer = setTimeout(poll, 1500);
    } catch (e) {
      $("buildMessage").textContent = "Lost contact with the studio: " + e.message;
      pollTimer = setTimeout(poll, 4000);
    }
  }

  function renderJob(j) {
    const done = j.status === "succeeded" || j.status === "failed";
    const card = $("buildCard");
    if (j.primary_color && HEX.test(j.primary_color)) card.style.setProperty("--tc", j.primary_color); else card.style.removeProperty("--tc");
    paintTile($("buildTile"), j.app_name, j.primary_color, !done);
    $("buildId").textContent = [CATEGORY[j.category], j.package_id, relTime(j.created_at)].filter(Boolean).join("  ·  ");
    $("buildTitle").textContent = j.app_name || "Imagining your app…";
    $("buildDesc").textContent = j.description || j.prompt;
    const badge = $("statusBadge");
    badge.textContent = STAGE_LABEL[j.status === "running" ? j.stage : j.status] || j.status;
    badge.className = "badge " + (j.status === "queued" ? "" : j.status);
    $("buildMessage").textContent = j.message || "";

    const bar = $("progressBar");
    bar.style.width = (j.progress || 0) + "%";
    bar.className = "bar" + (!done ? " indeterminate" : "") + (j.status === "failed" ? " failed" : "");
    document.querySelector(".progress").setAttribute("aria-valuenow", String(j.progress || 0));

    const attempts = j.attempts || [];
    const repaired = attempts.length > 1 || j.stage === "repairing";
    const idx = STEPS.indexOf(j.stage);
    const failedAt = attempts.length === 0 ? (j.app_name ? 1 : 0) : attempts.length > 1 ? 3 : 2;
    document.querySelectorAll("#stepper li").forEach((li, i) => {
      const skip = li.dataset.step === "repairing" && !repaired;
      let cls = "";
      if (j.status === "succeeded") cls = skip ? "skipped" : "done";
      else if (j.status === "failed") cls = i === failedAt ? "failed" : i < failedAt ? (skip ? "skipped" : "done") : "";
      else if (idx >= 0) cls = i < idx ? (skip ? "skipped" : "done") : i === idx ? "active" : "";
      li.className = cls;
    });

    const ok = j.status === "succeeded" && j.apk;
    $("resultBox").hidden = !ok;
    const dl = $("downloadBtn");
    if (ok) {
      $("apkName").textContent = j.apk.filename;
      $("apkMeta").textContent = `${(j.apk.size / 1048576).toFixed(1)} MB · verified build · ${j.apk.package}`;
      dl.href = `/api/builds/${j.id}/apk`;
      dl.setAttribute("aria-disabled", "false");
      dl.setAttribute("download", j.apk.filename);
      $("apkChecks").replaceChildren(...(j.apk.checks || []).map((c) => el("li", { text: c })));
    } else {
      dl.href = "#"; dl.setAttribute("aria-disabled", "true"); dl.removeAttribute("download");
    }

    $("errorBox").hidden = j.status !== "failed";
    $("errorText").textContent = j.error || "";

    $("featuresBox").hidden = !(j.features && j.features.length);
    $("featuresList").replaceChildren(...(j.features || []).map((f) => el("li", { text: f })));

    $("attemptsBox").hidden = attempts.length === 0;
    $("attemptsList").replaceChildren(...attempts.map((a) => {
      const passed = a.exit_code === 0 && !a.timed_out;
      const head = el("div", { class: "a-head" },
        el("span", { text: a.kind === "initial" ? "First build" : `After repair #${a.n - 1}` }),
        el("span", { class: passed ? "a-ok" : "a-bad",
          text: passed ? `passed · ${Math.round(a.seconds)}s` : a.timed_out ? "timed out" : `${a.errors.length} error${a.errors.length === 1 ? "" : "s"}` }));
      return el("li", {}, head,
        a.errors && a.errors.length ? el("div", { class: "a-body", text: a.errors.slice(0, 3).join("\n") }) : null,
        a.patch ? el("div", { class: "a-fix", text: "Fix: " + a.patch.explanation }) : null);
    }));
    $("fullLogLink").href = `/api/builds/${j.id}/log?full=true`;
  }

  function renderLog(text) {
    if (text.length === lastLogLen) return;
    lastLogLen = text.length;
    const frag = document.createDocumentFragment();
    for (const line of text.split("\n")) {
      let cls = "";
      if (/^\[.*\] (== FAILED|!!)|^e: |FAILURE:|BUILD FAILED/.test(line)) cls = "l-err";
      else if (/✓|BUILD SUCCESSFUL|== SUCCESS/.test(line)) cls = "l-ok";
      else if (/^\[.*\] ==/.test(line)) cls = "l-head";
      frag.append(el("span", cls ? { class: cls, text: line + "\n" } : { text: line + "\n" }));
    }
    const box = $("log");
    box.replaceChildren(frag);
    if ($("autoscroll").checked) box.scrollTop = box.scrollHeight;
  }

  // ---------- library ----------
  async function loadHistory() {
    try {
      const jobs = await api("/api/builds");
      const ready = jobs.filter((j) => j.status === "succeeded").length;
      $("libraryMeta").textContent = jobs.length ? `${ready} ready to install · ${jobs.length} total` : "";
      $("historyEmpty").hidden = jobs.length > 0;
      $("historyList").replaceChildren(...jobs.map((j) => {
        const done = j.status === "succeeded" || j.status === "failed";
        const tile = el("div", { class: "tile" });
        paintTile(tile, j.app_name, j.primary_color, !done);
        const badge = el("span", { class: "badge " + (j.status === "queued" ? "" : j.status),
          text: STAGE_LABEL[j.status === "running" ? j.stage : j.status] || j.status });
        const btn = el("button", { class: "app-card" + (j.id === currentId ? " selected" : ""), type: "button" },
          el("div", { class: "top" }, tile, badge),
          el("div", { class: "name", text: j.app_name || "Untitled app" }),
          el("div", { class: "sub", text: [CATEGORY[j.category], relTime(j.created_at)].filter(Boolean).join(" · ") }),
          el("div", { class: "desc", text: j.description || j.prompt }));
        btn.dataset.id = j.id;
        btn.addEventListener("click", () => selectBuild(j.id));
        return el("li", {}, btn);
      }));
      if (!currentId) {
        const active = jobs.find((j) => j.status === "running" || j.status === "queued");
        if (active) selectBuild(active.id);
      }
    } catch { /* surfaced by the studio pill */ }
  }
  $("refreshHistory").addEventListener("click", (e) => {
    const b = e.currentTarget;
    b.classList.remove("spin"); void b.offsetWidth; b.classList.add("spin");
    loadHistory();
  });

  // ---------- phone pairing ----------
  const svgData = (svg) => "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  $("phoneBtn").addEventListener("click", async () => {
    const d = $("phoneDialog");
    try {
      const p = await api("/api/pairing");
      const on = p.lan_enabled && p.urls.length > 0;
      $("phoneOn").hidden = !on;
      $("phoneOff").hidden = on;
      if (on) {
        $("pairUrl").textContent = p.urls[0].replace("http://", "");
        $("pairCode").textContent = p.access_code;
        $("getUrl").textContent = p.urls[0] + "/get";
        $("pairQr").src = svgData(p.qr_svg);
        $("getQr").src = svgData(p.get_qr_svg);
        $("noPhoneApk").hidden = p.phone_app_available;
      }
    } catch {
      $("phoneOn").hidden = true; $("phoneOff").hidden = false;
    }
    d.showModal();
  });
  $("phoneDialog").addEventListener("click", (e) => {
    if (e.target.matches("[data-close]") || e.target === e.currentTarget) e.currentTarget.close();
  });

  loadHealth();
  loadHistory();
  updateCount();
})();
