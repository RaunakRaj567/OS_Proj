/* ==========================================================================
   main.js — wires the modules together in the browser.

   Input (matrices or a process trace, Module 1)
     ──► /api/analyze   detection: actual deadlock + POTENTIAL deadlock (risk) + characterization
     ──► /api/resolve   suggested resolution strategies (recover or mitigate)
     ──► /api/prevent, /api/starvation   supporting topics
   Everything re-runs automatically (debounced) after every change.
   ========================================================================== */

const App = {
  view: "rag",
  result: null,
  valid: false,
  title: "",
  seq: 0,
  timer: null,
  svg: null,
  risk: null,
  history: {},          // process -> times chosen as a recovery victim (starvation / aging)
  aging: { penalty: 60, max: 3 },
};

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 2200);
}

/* ---------------- HUD used by the scan animation ---------------- */
const Hud = {
  el: () => document.getElementById("hud"),
  names: [],
  show(work, names) { this.names = names; this.el().hidden = false; this.work(work, false); this.pass(0); },
  hide() { this.el().hidden = true; },
  pass(p) { document.getElementById("hud-pass").textContent = p; },
  work(w, bump) {
    const box = document.getElementById("hud-work");
    const old = [...box.querySelectorAll("b")].map((b) => +b.textContent);
    box.innerHTML = w.map((v, i) => `<span><b class="${bump && old[i] !== v ? "bump" : ""}">${v}</b><small>${esc(this.names[i] || "")}</small></span>`).join("");
  },
  msg(html) { document.getElementById("hud-msg").innerHTML = html; },
};

/* ---------------- analysis pipeline ---------------- */
function scheduleAnalyze(opts = {}) {
  clearTimeout(App.timer);
  App.timer = setTimeout(() => analyze(opts), opts.debounce ? 260 : 0);
}

/* While results are re-rendered, panels must never collapse for a moment: if the page got
   shorter even briefly, the browser would pull the user's scroll position up (a "jump").
   Each re-render therefore pins the current height of the result panels and releases it
   only when the newest analysis has finished rendering. */
const PINNED = [".console", "#lab"];
function pinHeights() {
  PINNED.forEach((sel) => {
    const el = document.querySelector(sel);
    if (el && !el.style.minHeight) el.style.minHeight = el.offsetHeight + "px";
  });
}
function releaseHeights() {
  requestAnimationFrame(() => PINNED.forEach((sel) => {
    const el = document.querySelector(sel);
    if (el) el.style.minHeight = "";
  }));
}

async function analyze(opts = {}) {
  const my = ++App.seq;
  pinHeights();
  try {
    await analyzeInner(opts, my);
  } finally {
    if (my === App.seq) {                          // only the newest run releases the pin
      releaseHeights();
      document.getElementById("options").classList.remove("updating");
    }
  }
}

async function analyzeInner(opts, my) {
  const state = Store.state;
  document.getElementById("empty-msg").hidden = state.processes.length + state.resources.length > 0;
  let resp;
  try { resp = await API.analyze(state); }
  catch (e) { toast("⚠ Server unreachable — is app.py running?"); return; }
  if (my !== App.seq) return;                       // a newer edit superseded this one

  Hud.hide();
  document.getElementById("btn-scan").disabled = false;   // any running scan is cancelled by re-render
  if (!resp.valid) {
    App.valid = false; App.result = null; App.risk = null;
    Store.status = {}; Deck.updateStatusDots();
    Results.showInvalid(resp.errors);
    Graph.render(App.svg, state, null, { view: App.view, animate: opts.structural });
    Results.renderRecovery([], { invalid: true });
    Results.renderPrevention([], { invalid: true });
    Results.renderAvoidance(state, null, { invalid: true });
    Results.renderStarvation(state, App.history, null, App.aging);
    return;
  }
  const res = resp.result;
  const wasDead = App.result && App.result.is_deadlocked;
  App.valid = true; App.result = res; App.risk = resp.risk;
  Store.status = riskStatus(res, resp.risk); Deck.updateStatusDots();
  Results.show(state, res);
  Results.showRisk(state, res, resp.risk);
  Graph.render(App.svg, state, res, gopts({ animate: opts.structural }));

  if (res.is_deadlocked && !wasDead && !opts.scan) alarm(true);
  if (opts.scan) runScan();

  // avoidance (Banker's safety algorithm result came with /api/analyze)
  Results.renderAvoidance(state, resp.safety, { deadlocked: res.is_deadlocked });
  document.getElementById("options").classList.add("updating");   // keep old cards, dimmed

  // resolution strategies, prevention and starvation — fetched in parallel
  const snap = clone(state);
  let prev, rec, starv;
  try {
    [prev, rec, starv] = await Promise.all([
      API.prevent(state),
      API.resolve(state, App.history),
      API.starvation(state, 6),
    ]);
  } catch (e) { toast("⚠ Server unreachable — is app.py running?"); return; }
  if (my !== App.seq) return;
  const ctx = { state: snap, result: res };
  Results.renderPrevention(prev.protocols || [], { ...ctx, apply: applyPrevention });
  Results.renderRecovery(rec.strategies || [], { ...ctx, mode: rec.mode, advice: rec.advice, apply: applyRecovery });
  document.getElementById("options").classList.remove("updating");
  if (starv && starv.valid) App.aging = { penalty: starv.aging_penalty, max: starv.max_victim_count };
  Results.renderStarvation(state, App.history, starv && starv.valid ? starv : null, App.aging);
}

/* graph options: the risk report feeds the LOCK ORDER view and the at-risk highlight */
function gopts(extra = {}) {
  return { view: App.view, risk: App.risk, atRisk: App.risk ? App.risk.at_risk : [], ...extra };
}

/* status dots in the matrix: completing processes that are at risk show amber-dashed */
function riskStatus(res, risk) {
  const st = { ...res.status };
  ((risk && risk.at_risk) || []).forEach((p) => { if (st[p] === "completes") st[p] = "atrisk"; });
  return st;
}

function alarm(bad) {
  const f = document.getElementById("alert-flash");
  f.className = "";
  void f.offsetWidth;                                // restart CSS animation
  f.className = bad ? "on" : "ok";
  if (bad) {
    const st = document.getElementById("stage");
    st.classList.remove("shake"); void st.offsetWidth; st.classList.add("shake");
  }
}

function runScan() {
  if (!App.valid || !App.result || !Store.state.processes.length) return toast("Nothing to scan");
  const btn = document.getElementById("btn-scan");
  btn.disabled = true;
  if (App.view === "lock") setView("rag");          // the scan animates processes
  Graph.render(App.svg, Store.state, App.result, gopts());
  document.getElementById("algo-trace").open = true;
  Graph.scan(App.svg, Store.state, App.result, {
    speed: +document.getElementById("speed").value,
    hud: Hud,
    onStep: (k) => Results.highlightTrace(k),
    onDone: (dead) => { btn.disabled = false; alarm(dead); },
  });
  setTimeout(() => (btn.disabled = false), 60000);
}

function applyState(title, desc, after, msg) {
  App.title = (App.title || "Custom") + " → " + title;
  document.getElementById("scenario-select").value = "";
  document.getElementById("scenario-desc").textContent = desc;
  Store.set(after, { structural: true, scan: true });
  toast(msg);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function applyRecovery(o) {
  (o.victims || []).forEach((v) => (App.history[v] = (App.history[v] || 0) + 1));   // aging record
  applyState(o.title, "Resolution applied: " + o.title + ". " + o.description, o.after_state, "⚡ Applied: " + o.title);
}

function setView(v) {
  App.view = v;
  document.querySelectorAll("#view-toggle button").forEach((x) => x.classList.toggle("active", x.dataset.view === v));
}

/* ---------------- process activity trace (automatic, event-by-event detection) ---------------- */
const Trace = { timeline: [] };

async function analyzeTrace() {
  const text = document.getElementById("trace-text").value;
  const out = await API.trace(text);
  const sum = document.getElementById("trace-summary"), list = document.getElementById("timeline");
  if (!out.ok) {
    sum.className = "cond-summary bad";
    sum.textContent = "⚠ " + (out.errors || ["Could not parse the trace"]).join(" ");
    list.innerHTML = "";
    return;
  }
  Trace.timeline = out.timeline;
  sum.className = "cond-summary " + (out.first_deadlock ? "bad" : out.first_risk ? "warn" : "ok");
  sum.textContent = out.summary;
  const mark = { deadlock: "bad", high: "warn", medium: "warn", none: "ok" };
  list.innerHTML = out.timeline.map((t) => `
    <li class="${mark[t.level]}${t.step === out.first_deadlock || t.step === out.first_risk ? " key" : ""}" data-step="${t.step}" title="Click to load the system state after this event">
      <span class="ts">#${t.step}</span><span class="te">${esc(t.description)}</span></li>`).join("");
  list.querySelectorAll("li").forEach((li) => (li.onclick = () => loadStep(+li.dataset.step)));
  loadStep(out.first_deadlock || out.timeline.length, true);
}

function loadStep(step, quiet) {
  const t = Trace.timeline[step - 1];
  if (!t) return;
  document.querySelectorAll("#timeline li").forEach((li) => {
    li.classList.toggle("sel", +li.dataset.step === step);
    if (+li.dataset.step === step) scrollWithin(document.getElementById("timeline"), li);
  });
  resetHistory();
  App.title = "Trace · after event #" + step;
  document.getElementById("scenario-select").value = "";
  document.getElementById("scenario-desc").textContent = "Process trace, state after event #" + step + ": " + t.event;
  Store.set(t.state, { structural: true, scan: !quiet });
}

function applyPrevention(p) {
  applyState("prevent " + p.condition.toLowerCase(),
    "Prevention protocol enforced (" + p.technique + "): " + p.rule, p.after_state, "🛡 Enforced: " + p.technique);
}

function applyGrant(out) {
  const proc = document.getElementById("rq-proc").value;
  applyState("grant " + proc, "Banker's algorithm granted " + proc + "'s request; the state is still safe.",
    out.after_state, "✓ Request granted to " + proc);
}

async function checkRequest() {
  if (!App.valid) return toast("⚠ Fix the input first");
  const proc = document.getElementById("rq-proc").value;
  if (!proc) return toast("Add a process first");
  const vec = [...document.querySelectorAll("#rq-vec input")].map((x) => Math.max(0, parseInt(x.value, 10) || 0));
  const out = await API.bankers(Store.state, proc, vec);
  Results.renderBankers(out, { apply: applyGrant });
}

function resetHistory() { App.history = {}; }

const clone = (o) => JSON.parse(JSON.stringify(o));

/* ---------------- scenario loading ---------------- */
async function loadScenario(id, scan = true) {
  const sc = await API.scenario(id);
  resetHistory();
  App.title = sc.name;
  document.getElementById("scenario-desc").textContent = sc.description;
  document.getElementById("scenario-select").value = id;
  Store.set(sc, { structural: true, scan });
}

async function initScenarios() {
  const sel = document.getElementById("scenario-select");
  const list = await API.scenarios();
  const groups = { potential: "Potential deadlocks", basic: "No deadlock", multi: "Multi-instance (characterization)", deadlock: "Deadlocks (detection & recovery)",
                   recovery: "After recovery", prevention: "Prevention", avoidance: "Avoidance (Banker's)", invalid: "Invalid input" };
  const byCat = {};
  list.forEach((s) => (byCat[s.category] = byCat[s.category] || []).push(s));
  Object.keys(groups).forEach((cat) => {
    if (!byCat[cat]) return;
    const og = document.createElement("optgroup");
    og.label = groups[cat];
    byCat[cat].forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; og.appendChild(o); });
    sel.appendChild(og);
  });
  sel.onchange = () => sel.value && loadScenario(sel.value);
}

/* ---------------- toolbar wiring ---------------- */
function wire() {
  document.getElementById("btn-random").onclick = async () => {
    const s = await API.random();
    resetHistory();
    App.title = "Random scenario";
    document.getElementById("scenario-select").value = "";
    document.getElementById("scenario-desc").textContent = "Randomly generated valid system — about 1 in 3 are deadlocked. Roll again!";
    Store.set(s, { structural: true, scan: true });
  };
  document.getElementById("btn-clear").onclick = () => {
    resetHistory();
    App.title = "";
    document.getElementById("scenario-select").value = "";
    document.getElementById("scenario-desc").textContent = "Empty system. Add resources, then processes.";
    Store.clear();
  };
  document.getElementById("btn-scan").onclick = runScan;
  document.getElementById("btn-rq").onclick = checkRequest;
  document.getElementById("btn-trace").onclick = analyzeTrace;
  document.getElementById("btn-trace-example").onclick = async () => {
    document.getElementById("trace-text").value = (await API.get("/api/trace/example")).text;
    analyzeTrace();
  };
  document.getElementById("btn-st-reset").onclick = () => {
    resetHistory();
    scheduleAnalyze();
    toast("⟲ Victim history cleared");
  };
  document.querySelectorAll(".topic-tabs .tab").forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll(".topic-tabs .tab").forEach((x) => x.classList.toggle("active", x === t));
      document.querySelectorAll(".topic").forEach((el) => (el.hidden = el.id !== "topic-" + t.dataset.topic));
    };
  });
  document.querySelectorAll("#view-toggle button").forEach((b) => {
    b.onclick = () => {
      setView(b.dataset.view);
      Hud.hide();
      Graph.render(App.svg, Store.state, App.result, gopts({ animate: true }));
    };
  });
  document.getElementById("btn-report").onclick = async () => {
    if (!App.valid) return toast("⚠ Fix the input before exporting a report");
    const r = await API.report(Store.state, App.title, App.history);
    const blob = await r.blob();
    download(blob, "deadlock_report.md");
    toast("⎙ Report downloaded");
  };
  document.getElementById("btn-save").onclick = () => {
    const data = { name: App.title || "Custom scenario", ...Store.state };
    download(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), "scenario.json");
    toast("⤓ Scenario saved");
  };
  document.getElementById("file-load").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      App.title = data.name || f.name;
      resetHistory();
      document.getElementById("scenario-select").value = "";
      document.getElementById("scenario-desc").textContent = "Loaded from " + f.name;
      Store.set(data, { structural: true, scan: true });
    } catch (err) { toast("⚠ Not a valid scenario JSON"); }
    e.target.value = "";
  };
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key === " ") { e.preventDefault(); runScan(); }
    if (e.key === "r") document.getElementById("btn-random").click();
  });
}

function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------------- ambient particle network ---------------- */
function background() {
  const c = document.getElementById("bg-canvas"), ctx = c.getContext("2d");
  let w, h, pts;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const resize = () => {
    w = c.width = innerWidth; h = c.height = innerHeight;
    const count = Math.min(70, Math.floor((w * h) / 26000));
    pts = Array.from({ length: count }, () => ({ x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35, r: Math.random() * 1.6 + .4 }));
  };
  resize(); addEventListener("resize", resize);
  const frame = () => {
    ctx.clearRect(0, 0, w, h);
    const alertMode = App.result && App.result.is_deadlocked;
    const col = alertMode ? "255,59,92" : "34,229,255";
    for (const p of pts) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.fillStyle = `rgba(${col},.7)`;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill();
    }
    for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
      const a = pts[i], b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < 130) {
        ctx.strokeStyle = `rgba(${col},${(1 - d / 130) * .22})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    if (!reduce) requestAnimationFrame(frame);
  };
  frame();
}

/* ---------------- boot sequence ---------------- */
function boot() {
  return new Promise((resolve) => {
    const el = document.getElementById("boot"), lines = document.getElementById("boot-lines");
    const msgs = ["Reading process dependencies", "Building resource allocation & wait-for graphs",
                  "Arming deadlock detector  O(m·n²)", "Potential-deadlock analysis (Banker's + lock order)",
                  "Resolution simulator online", "Starvation guard (aging) enabled"];
    let done = false;
    const finish = () => { if (done) return; done = true; el.classList.add("done"); resolve(); };
    msgs.forEach((m, i) => setTimeout(() => {
      const d = document.createElement("div");
      d.innerHTML = esc(m) + ' <span class="ok">[ OK ]</span>';
      lines.appendChild(d);
    }, 120 + i * 260));
    setTimeout(finish, 2100);
    el.onclick = finish;
  });
}

/* ---------------- start ---------------- */
(async function main() {
  App.svg = document.getElementById("graph");
  background();
  Deck.init();
  wire();
  Store.onChange((opts) => scheduleAnalyze(opts));
  const booting = boot();
  try { await initScenarios(); } catch (e) { toast("⚠ Could not load scenarios"); }
  await booting;
  loadScenario("t07_printer_scanner", true).catch(() => Store.clear());
})();
