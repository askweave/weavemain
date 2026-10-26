// Genesis Chat. All server text is rendered with textContent (never innerHTML).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const LINK_RE = /(https?:\/\/[^\s]+\/download\/[A-Za-z0-9_-]+|\/download\/[A-Za-z0-9_-]+)/;
  let lastId = 0, pollTimer = null, sending = false, build = null, signedIn = false;

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Genesis-Chat": "1" },
      ...opts,
    });
    let body = null;
    try { body = await res.json(); } catch { /* empty */ }
    if (!res.ok) {
      const err = new Error((body && body.detail) || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  const uuid = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const fmtTime = (s) => new Date(s * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  // ---------- views ----------
  function show(view) {
    signedIn = view === "chat";
    $("signin").hidden = view !== "signin";
    $("chat").hidden = $("composer").hidden = view !== "chat";
    $("menuBtn").hidden = view !== "chat";
    if (view !== "chat") $("projectChip").hidden = true;
  }

  function bubble(m) {
    const li = document.createElement("li");
    li.className = `msg ${m.from}`;
    const match = m.from === "genesis" ? m.text.match(LINK_RE) : null;
    if (match) {
      const [before, after] = [m.text.slice(0, match.index), m.text.slice(match.index + match[0].length)];
      li.append(before.trimEnd());
      const a = document.createElement("a");
      a.className = "dl";
      a.href = match[0];
      a.rel = "noopener";
      a.textContent = "⬇ Download APK";
      li.append(document.createElement("br"), a);
      if (after.trim()) li.append("\n" + after.trim());
    } else {
      li.textContent = m.text;
    }
    const t = document.createElement("time");
    t.textContent = fmtTime(m.at);
    li.append(t);
    return li;
  }

  function renderBuild(b) {
    build = b;
    const box = $("build");
    const live = b && (b.status === "queued" || b.status === "running");
    box.hidden = !live;
    if (!live) return;
    $("buildRef").textContent = b.ref;
    const label = b.status === "queued" ? "Waiting for a build slot…" : (b.label || "Working…");
    $("buildLabel").textContent = `${b.kind === "change" ? "Updating" : "Building"} ${b.project}: ${label}`;
    box.classList.toggle("indeterminate", b.progress == null);
    $("buildBar").style.width = b.progress == null ? "" : `${Math.max(4, b.progress)}%`;
  }

  function renderProjects(projects) {
    const active = projects.find((p) => p.active);
    const chip = $("projectChip");
    chip.hidden = !active;
    if (active) chip.textContent = `${active.number} · ${active.name}${active.ready ? "" : " (building)"}`;
  }

  // ---------- polling ----------
  async function poll() {
    clearTimeout(pollTimer);
    if (!signedIn) return;
    try {
      const s = await api(`/api/chat/state?after=${lastId}`);
      const log = $("log");
      const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
      for (const m of s.messages) {
        log.append(bubble(m));
        lastId = Math.max(lastId, m.id);
      }
      $("empty").hidden = log.children.length > 0;
      renderBuild(s.build);
      renderProjects(s.projects);
      if (s.messages.length && (atBottom || s.messages.some((m) => m.from === "me"))) window.scrollTo(0, document.body.scrollHeight);
    } catch (e) {
      if (e.status === 401) { show("signin"); return; }
    }
    const busy = build && (build.status === "queued" || build.status === "running");
    pollTimer = setTimeout(poll, document.hidden ? 15000 : busy ? 2000 : 5000);
  }

  // ---------- actions ----------
  async function send(text) {
    text = text.trim();
    if (!text || sending) return;
    sending = true;
    $("sendBtn").disabled = true;
    const id = uuid();
    try {
      // The same client id is reused on retry, so a flaky network can't start two builds.
      for (let i = 0; i < 3; i++) {
        try { await api("/api/chat/messages", { method: "POST", body: JSON.stringify({ text, client_id: id }) }); break; }
        catch (e) { if (e.status || i === 2) throw e; await new Promise((r) => setTimeout(r, 1000 * (i + 1))); }
      }
      $("text").value = "";
      autosize();
    } catch (e) {
      if (e.status === 401) show("signin");
      else alert(e.message);
    } finally {
      sending = false;
      $("sendBtn").disabled = false;
      poll();
    }
  }

  async function signIn(payload) {
    $("signinError").hidden = true;
    try {
      await api("/api/chat/session", { method: "POST", body: JSON.stringify(payload) });
      history.replaceState(null, "", "/chat");
      show("chat");
      lastId = 0;
      $("log").textContent = "";
      poll();
    } catch (e) {
      $("signinError").textContent = e.message;
      $("signinError").hidden = false;
    }
  }

  function autosize() {
    const t = $("text");
    t.style.height = "auto";
    t.style.height = `${Math.min(t.scrollHeight, 140)}px`;
  }

  // ---------- wiring ----------
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send($("text").value); });
  $("text").addEventListener("input", autosize);
  $("text").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && window.matchMedia("(pointer: fine)").matches) { e.preventDefault(); send($("text").value); }
  });
  document.querySelectorAll("[data-cmd]").forEach((b) => b.addEventListener("click", () => {
    $("menu").hidden = true;
    send(b.dataset.cmd);
  }));
  document.querySelectorAll(".idea").forEach((b) => b.addEventListener("click", () => { $("text").value = b.textContent; autosize(); $("text").focus(); }));
  $("menuBtn").addEventListener("click", (e) => { e.stopPropagation(); $("menu").hidden = !$("menu").hidden; });
  $("projectChip").addEventListener("click", () => send("PROJECTS"));
  document.addEventListener("click", (e) => { if (!$("menu").contains(e.target)) $("menu").hidden = true; });
  $("signOut").addEventListener("click", async () => {
    try { await api("/api/chat/logout", { method: "POST" }); } catch { /* ignore */ }
    show("signin");
  });
  $("codeForm").addEventListener("submit", (e) => { e.preventDefault(); signIn({ code: $("code").value }); });
  $("localBtn").addEventListener("click", () => signIn({ local: true }));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  // ---------- start ----------
  $("localBtn").hidden = !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const fromLink = new URLSearchParams(location.hash.slice(1)).get("code");
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/chat/sw.js", { scope: "/chat" }).catch(() => {});
  api("/api/chat/state?after=0&probe=1").then(() => { show("chat"); poll(); }).catch(() => {
    show("signin");
    if (fromLink) { $("code").value = fromLink; signIn({ code: fromLink }); }
  });
})();
