/* Hive Kiosk frontend: rotation engine, module renderers, alert overlay,
   hidden admin gate. Talks only to localhost. */
"use strict";

const $ = (s) => document.querySelector(s);
let CFG = null;
let MODULES = [];
let idx = -1, cycles = 0, dwellTimer = null;
let goesTimer = null;

const api = async (p) => (await fetch(p)).json();

/* ------------------------------------------------------------- clock ---- */
setInterval(() => {
  $("#clock").textContent = new Date().toLocaleTimeString("en-US",
    { hour: "2-digit", minute: "2-digit" });
}, 1000);

/* ---------------------------------------------------------- rotation ---- */
async function boot() {
  CFG = await api("/api/config");
  MODULES = CFG.display.modules.filter((m) => m.enabled);
  const dots = $("#dots");
  dots.innerHTML = MODULES.map(() => "<i></i>").join("");
  keySequenceListener(CFG.admin_key_sequence || "hivemind");
  setInterval(pollAlert, 60_000);
  pollAlert();
  next();
}

async function next() {
  clearTimeout(dwellTimer);
  clearInterval(goesTimer);
  idx = (idx + 1) % MODULES.length;
  if (idx === 0) cycles++;

  let mod = MODULES[idx];
  // occasionally swap showcase for its "how to post" promo screen
  const promo = mod.id === "showcase" &&
    CFG.display.showcase_promo_every_n_cycles &&
    cycles % CFG.display.showcase_promo_every_n_cycles === 0;

  const el = document.createElement("section");
  el.className = "module";
  try {
    await RENDER[promo ? "showcase_promo" : mod.id](el);
  } catch (e) {
    el.innerHTML = `<h2>${mod.id}</h2><p class="sub">no data yet — ${e}</p>`;
  }
  const stage = $("#stage");
  stage.appendChild(el);
  requestAnimationFrame(() => el.classList.add("active"));
  [...stage.children].slice(0, -1).forEach((old) => {
    old.classList.remove("active");
    setTimeout(() => old.remove(), CFG.display.transition_ms + 100);
  });

  $("#module-caption").textContent = CAPTIONS[promo ? "showcase_promo" : mod.id];
  [...$("#dots").children].forEach((d, i) => d.classList.toggle("on", i === idx));

  const dwell = (mod.dwell || CFG.display.rotation_seconds) * 1000;
  dwellTimer = setTimeout(next, dwell);
  // config may have been changed from the admin panel — re-pull each cycle
  if (idx === MODULES.length - 1) {
    const fresh = await api("/api/config");
    CFG = fresh;
    MODULES = fresh.display.modules.filter((m) => m.enabled);
  }
}

const CAPTIONS = {
  ai_news: "what the models are up to",
  world_news: "the world + the scoreboard",
  weather: "94103, from orbit",
  discord: "heard around the Hive",
  showcase: "made at Hive",
  showcase_promo: "put YOUR thing on this screen",
};

/* ---------------------------------------------------------- renderers --- */
const RENDER = {
  async ai_news(el) {
    const { data } = await api("/api/module/ai_news");
    const items = (data?.news || []).slice(0, 7).map((n) => `
      <div class="news-item"><div class="t">${esc(n.title)}</div>
        <div class="m">${esc(n.source)} · ${ago(n.ts)}</div></div>`).join("");
    const rows = (data?.leaderboard?.rows || []).map((r, i) => `
      <tr><td>${i + 1}</td><td>${esc(r.model)}</td>
          <td>${r.score ?? "—"}</td>
          <td>${r.open ? '<span class="badge-open">OPEN</span>' : ""}</td></tr>`).join("");
    el.innerHTML = `<h2>AI / LLM</h2><div class="sub">original reporting only</div>
      ${items}
      <div class="board"><table>
        <tr><th>#</th><th>Model — ${esc(data?.leaderboard?.source || "")}</th><th>Score</th><th></th></tr>
        ${rows}</table></div>`;
  },

  async world_news(el) {
    const [{ data: news }, { data: sp }] = await Promise.all(
      [api("/api/module/world_news"), api("/api/module/sports")]);
    const items = (news?.news || []).slice(0, 7).map((n) => `
      <div class="news-item"><div class="t">${esc(n.title)}</div>
        <div class="m">${esc(n.source)} · ${ago(n.ts)}</div></div>`).join("");
    const rows = (sp?.events || []).slice(0, 8).map((e) => `
      <div class="sport-row"><span class="lg">${esc(e.league)}</span>
        <span>${esc(e.name)}</span><span>${esc(e.score)}</span>
        <span>${esc(e.status)}</span></div>`).join("");
    el.innerHTML = `<h2>World</h2><div class="sub">AP · Reuters wire only</div>
      ${items}<h2 style="margin-top:26px">Scores</h2>${rows || "<p>no games today</p>"}`;
  },

  async weather(el) {
    const [{ data: wx }, { data: gs }] = await Promise.all(
      [api("/api/module/weather"), api("/api/module/goes")]);
    el.innerHTML = `<h2>SF Weather — 94103</h2>
      <div class="sub">next 48 h · weather.gov</div>
      <svg id="wx-chart" viewBox="0 0 1000 760"></svg>
      <div class="goes-grid">
        <div class="pane fd"><img id="g-fd"><span class="lbl">GOES-18 Full Disk</span></div>
        <div class="pane"><img id="g-conus"><span class="lbl">CONUS</span></div>
        <div class="pane"><img id="g-psw"><span class="lbl">Pacific SW</span></div>
      </div><div id="goes-ts"></div>`;
    drawWxChart(wx?.hours || []);
    runGoes(gs?.timeline || []);
  },

  async discord(el) {
    const { data } = await api("/api/module/discord");
    const cols = (data?.channels || []).map((c) => `
      <div class="dc-ch"><h3>#${esc(c.name)}</h3>
        ${(c.messages || []).map((m) => `
          <div class="dc-msg"><span class="a">${esc(m.author)}</span>
            ${esc(m.content) || (m.attachments ? "📎 attachment" : "…")}</div>`).join("")
        || `<div class="dc-msg">${esc(c.error || "quiet in here")}</div>`}
      </div>`).join("");
    el.innerHTML = `<h2>Hive Discord</h2>
      <div class="sub">live from the server</div><div class="dc-cols">${cols}</div>`;
  },

  async showcase(el) {
    const entries = await api("/api/showcase");
    if (!entries.length) return RENDER.showcase_promo(el);
    const pick = entries[Math.floor(Math.random() * entries.length)];
    // sandbox with NO tokens: no scripts, no navigation, no forms.
    el.innerHTML = `<h2>${esc(pick.title || pick.id)}</h2>
      <div class="sub">by ${esc(pick.author || pick.id)} · resident showcase</div>
      <iframe class="show-frame" sandbox="" src="${pick.url}"></iframe>`;
  },

  async showcase_promo(el) {
    el.innerHTML = `<div class="promo">
      <h2>Live at Hive? Put your startup on this screen.</h2>
      <div class="sub">no gatekeepers — merges are automatic</div>
      <pre>1. github.com/Snerk/weather_kiosk → Fork
2. add  content/residents/&lt;your-name&gt;/card.html
   (plus images; no &lt;script&gt; — it won't run anyway)
3. open a Pull Request
4. checks pass → auto-merged → on screen in ~15 min

full instructions: content/HOW_TO_POST.md</pre></div>`;
  },
};

/* --------------------------------------------------- weather SVG chart -- */
function drawWxChart(hours) {
  const svg = $("#wx-chart");
  if (!hours.length) { svg.outerHTML = "<p>waiting on weather.gov…</p>"; return; }
  const W = 1000, H = 760, L = 70, R = 70, T = 30, B = 60;
  const n = hours.length, x = (i) => L + (i * (W - L - R)) / (n - 1);
  const series = [
    { k: "temp_f", color: "#c8402e", label: "°F", axis: "left" },
    { k: "wind_mph", color: "#2e5ec8", label: "wind mph", axis: "right" },
    { k: "gust_mph", color: "#7a95d6", label: "gust mph", axis: "right", dash: true },
    { k: "rh", color: "#3d8f5f", label: "RH %", axis: "right", dash: true },
  ];
  const lo = {}, hi = {};
  for (const s of series) {
    const vals = hours.map((h) => h[s.k]).filter((v) => v != null);
    lo[s.axis] = Math.min(lo[s.axis] ?? 1e9, ...vals);
    hi[s.axis] = Math.max(hi[s.axis] ?? -1e9, ...vals);
  }
  const y = (v, axis) =>
    T + (H - T - B) * (1 - (v - lo[axis]) / Math.max(1, hi[axis] - lo[axis]));
  let out = "";
  // precip bars only where pop > 0
  hours.forEach((h, i) => {
    if (h.pop > 0) {
      const bh = ((H - T - B) * h.pop) / 100;
      out += `<rect x="${x(i) - 4}" y="${H - B - bh}" width="8" height="${bh}"
               fill="#2e5ec8" opacity="0.25"/>`;
    }
  });
  for (const s of series) {
    const pts = hours.map((h, i) => h[s.k] == null ? null
      : `${x(i)},${y(h[s.k], s.axis)}`).filter(Boolean).join(" ");
    out += `<polyline points="${pts}" fill="none" stroke="${s.color}"
             stroke-width="4" ${s.dash ? 'stroke-dasharray="9 7"' : ""}/>`;
  }
  // wind direction arrows every 6 h along the bottom
  hours.forEach((h, i) => {
    if (i % 6 === 0 && h.wind_dir != null) {
      out += `<g transform="translate(${x(i)},${H - B + 26}) rotate(${h.wind_dir + 180})">
        <path d="M0,-11 L6,9 L0,4 L-6,9 Z" fill="#17130e"/></g>`;
    }
  });
  // hour labels + dual-unit legend
  hours.forEach((h, i) => {
    if (i % 6 === 0) {
      const d = new Date(h.t);
      out += `<text x="${x(i)}" y="${H - 8}" font-size="19" text-anchor="middle"
              fill="#5d4a2c">${d.getHours()}:00</text>`;
    }
  });
  const t0 = hours[0];
  out += `<text x="${L}" y="20" font-size="21" fill="#17130e">
    now ${t0.temp_f ?? "–"}°F / ${t0.temp_c ?? "–"}°C ·
    wind ${t0.wind_mph ?? "–"} mph / ${t0.wind_kph ?? "–"} kph ·
    RH ${t0.rh ?? "–"}%</text>`;
  series.forEach((s, i) => {
    out += `<rect x="${L + i * 170}" y="${H - 34}" width="26" height="6" fill="${s.color}"/>
      <text x="${L + i * 170 + 34}" y="${H - 27}" font-size="19">${s.label}</text>`;
  });
  svg.innerHTML = out;
}

/* ------------------------------------------------------- GOES playback -- */
function runGoes(timeline) {
  if (!timeline.length) { $("#goes-ts").textContent = "downloading satellite frames…"; return; }
  let f = 0;
  goesTimer = setInterval(() => {
    const step = timeline[f];
    for (const id of ["fd", "conus", "psw"]) {
      if (step.frames[id]) $("#g-" + id).src = step.frames[id];
    }
    $("#goes-ts").textContent =
      new Date(step.ts).toLocaleString() + `  ·  frame ${f + 1}/${timeline.length}`;
    f = (f + 1) % timeline.length;
    if (f === 0) { clearInterval(goesTimer);          // hold last frame, restart
      setTimeout(() => runGoes(timeline), 2500); }
  }, 140);
}

/* ------------------------------------------------------- alert overlay -- */
async function pollAlert() {
  try {
    const { data } = await api("/api/module/discord");
    const a = data?.alert;
    const active = a && (Date.now() / 1000 - a.shown_since) <
      (CFG?.alert_display_minutes ?? 10) * 60;
    $("#alert-overlay").classList.toggle("hidden", !active);
    if (active) {
      $("#alert-body").textContent = a.content;
      $("#alert-meta").textContent = `— ${a.author}, ${new Date(a.ts).toLocaleTimeString()}`;
    }
  } catch (_) { /* server restarting; try next minute */ }
}

/* -------------------------------------------------- hidden admin gate --- */
function keySequenceListener(seq) {
  let buf = "";
  document.addEventListener("keydown", (e) => {
    if (e.key.length === 1) buf = (buf + e.key.toLowerCase()).slice(-seq.length);
    if (buf === seq.toLowerCase()) { buf = ""; showAdminGate(); }
    if (e.key === "Escape") $("#admin-gate").classList.add("hidden");
  });
}
function showAdminGate() {
  $("#admin-gate").classList.remove("hidden");
  $("#admin-pass").value = ""; $("#admin-pass").focus();
}
$("#admin-go")?.addEventListener("click", async () => {
  const r = await fetch("/api/admin/login", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("#admin-pass").value }) });
  if (!r.ok) { $("#admin-err").textContent = "nope"; return; }
  const { token } = await r.json();
  location.href = "/admin#" + token;   // full panel; token re-entered there
});

/* ------------------------------------------------------------- utils ---- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function ago(ts) {
  if (!ts) return "";
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago`
    : `${Math.round(m / 1440)}d ago`;
}

boot();
