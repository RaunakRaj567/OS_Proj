/* ==========================================================================
   results.js — MODULE 3 (visual)
     Detection         verdict (deadlock / potential / safe), findings, stats,
                       circular wait, explanations, trace table
     Resolution        suggested strategies (recovery or mitigation) + before/after
     Characterization  four-condition tiles
     Prevention        one card per condition, simulated protocol + before/after
     Avoidance         Banker's safety result, Need matrix, state-space diagram,
                       resource-request algorithm
     Recovery          ranked option cards + before/after comparison
     Starvation        victim history (aging) + recurring-deadlock simulation
   ========================================================================== */

const Results = {
  $: (id) => document.getElementById(id),
  lastVerdict: null,

  setStatusPill(kind, text) {
    const pill = this.$("sys-status");
    pill.className = "status-pill " + kind;
    pill.querySelector("span").textContent = text;
  },

  verdict(kind, title, sub) {
    const v = this.$("verdict");
    const changed = this.lastVerdict !== kind + title;
    v.className = "verdict " + kind + (changed ? " pop" : "");
    v.querySelector(".verdict-title").textContent = title;
    v.querySelector(".verdict-sub").textContent = sub;
    this.lastVerdict = kind + title;
  },

  countTo(el, target) {
    const from = +el.textContent || 0;
    if (from === target) return;
    const t0 = performance.now(), dur = 450;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      el.textContent = Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  },

  showInvalid(errors) {
    this.setStatusPill("invalid", "INVALID INPUT");
    this.verdict("invalid", "INVALID STATE", "Fix the highlighted input — detection is paused");
    const box = this.$("errors");
    box.hidden = false;
    box.innerHTML = errors.map((e) => `<div>${esc(e)}</div>`).join("");
    this.$("explain").innerHTML = "";
    this.$("conditions").innerHTML = "";
    this.$("cond-summary").textContent = "";
    ["cycles-block", "order-block", "findings-block"].forEach((id) => (this.$(id).hidden = true));
    ["st-ok", "st-bad", "st-warn"].forEach((id) => this.countTo(this.$(id), 0));
    this.$("trace").innerHTML = "";
  },

  show(state, res) {
    this.$("errors").hidden = true;
    const n = state.processes.length;
    if (n === 0) {
      this.setStatusPill("idle", "SYSTEM IDLE");
      this.verdict("idle", "AWAITING INPUT", "Detection runs automatically on every change");
    } else if (res.is_deadlocked) {
      this.setStatusPill("bad", "DEADLOCK DETECTED");
      this.verdict("bad", "DEADLOCK DETECTED",
        `${res.deadlocked.length} in circular wait · ${res.blocked.length} blocked · ${res.completion_order.length} can finish`);
    } else {
      this.setStatusPill("ok", "SYSTEM STABLE");
      this.verdict("ok", "NO DEADLOCK", res.cycle_without_deadlock
        ? "Cycle present, but multi-instance resources let everyone finish"
        : "Every process can run to completion");
    }

    this.countTo(this.$("st-ok"), res.completion_order.length);
    this.countTo(this.$("st-bad"), res.deadlocked.length);
    this.countTo(this.$("st-warn"), res.blocked.length);

    // circular waits (with the resources on each hop)
    const cb = this.$("cycles-block");
    cb.hidden = !res.cycles.length;
    this.$("cycles").innerHTML = res.cycles.map((cyc, ci) => {
      const hops = [];
      for (let i = 0; i < cyc.length - 1; i++) {
        const e = res.deadlock_edges.find((x) => x.from === cyc[i] && x.to === cyc[i + 1]);
        hops.push(`<b>${esc(cyc[i])}</b> <small>—${esc(e ? e.resource : "")}→</small> `);
      }
      return `<div class="cycle-line" style="animation-delay:${ci * 80}ms">${hops.join("")}<b>${esc(cyc[cyc.length - 1])}</b></div>`;
    }).join("");

    // completion order
    const ob = this.$("order-block");
    ob.hidden = !res.completion_order.length;
    this.$("order").innerHTML = res.completion_order
      .map((p, i) => `<span class="chip" style="animation-delay:${i * 70}ms">${esc(p)}</span>`)
      .join('<span class="arrow">→</span>');

    // explanations
    this.$("explain").innerHTML = res.explanations.map((e, i) => {
      const cls = /^DEADLOCK/.test(e) ? "bad" : /BLOCKED/.test(e) ? "warn"
        : /^No deadlock|can still finish/.test(e) ? "ok" : /waits for/.test(e) ? "bad" : "";
      return `<li class="${cls}" style="animation-delay:${i * 70}ms">${esc(e)}</li>`;
    }).join("");

    this.renderConditions(res);
    this.renderTrace(res);
  },

  /* ---------------- Potential-deadlock risk (core) ---------------- */
  showRisk(state, res, risk) {
    const n = state.processes.length;
    const fb = this.$("findings-block");
    fb.hidden = !n || !risk || !risk.findings.length;
    if (!risk || !n) return;
    if (risk.level === "high" || risk.level === "medium") {
      this.setStatusPill("warn", "POTENTIAL DEADLOCK");
      this.verdict("warn", "POTENTIAL DEADLOCK",
        (risk.level === "high" ? "Unsafe state" : "Lock-order inversion") + " · " + risk.at_risk.length +
        " process(es) at risk · not deadlocked yet");
    } else if (risk.level === "none" && !res.is_deadlocked) {
      this.verdict("ok", "NO DEADLOCK · NO RISK", res.cycle_without_deadlock
        ? "A cycle exists but multi-instance resources let everyone finish"
        : "Safe state and a consistent resource-acquisition order");
    }
    const sev = { deadlock: "bad", high: "warn", medium: "warn" };
    const lbl = { deadlock: "DEADLOCK", high: "HIGH RISK", medium: "RISK" };
    this.$("findings").innerHTML = risk.findings.map((f, i) => `
      <li class="${sev[f.severity] || ""}" style="animation-delay:${i * 70}ms">
        <span class="sev">${lbl[f.severity] || f.severity}</span><b>${esc(f.title)}</b><p>${esc(f.detail)}</p></li>`).join("");
  },

  /* ---------------- Characterization ---------------- */
  condIcons: { mutual_exclusion: "⊘", hold_and_wait: "✋", no_preemption: "🔒", circular_wait: "↻" },

  renderConditions(res) {
    const conds = res.conditions || [];
    this.$("conditions").innerHTML = conds.map((c, i) => `
      <div class="cond ${c.holds ? "on" : "off"}" style="animation-delay:${i * 60}ms" title="${esc(c.detail)}">
        <div class="cond-top"><span class="cond-ico">${this.condIcons[c.key] || "•"}</span><b>${esc(c.name)}</b>
          <span class="cond-flag">${c.holds ? "HOLDS" : "NOT MET"}</span></div>
        <p>${esc(c.detail)}</p>
      </div>`).join("");
    const all = conds.length && conds.every((c) => c.holds);
    const el = this.$("cond-summary");
    el.textContent = (res.explanations || []).find((e) => /necessary/.test(e)) || "";
    el.className = "cond-summary " + (!conds.length ? "" : res.is_deadlocked ? "bad" : all ? "warn" : "ok");
  },

  setBadge(topic, kind, text) {
    const b = this.$("tb-" + topic);
    if (!b) return;
    b.className = "tb " + (kind || "");
    b.textContent = text || "";
  },

  renderTrace(res) {
    let html = "<tr><th>Pass</th><th>Process</th><th>Request</th><th>Work</th><th>Result</th></tr>";
    html += `<tr><td>0</td><td>—</td><td></td><td>[${res.available}]</td><td>Work = Available</td></tr>`;
    res.trace.forEach((ev, k) => {
      if (ev.type === "check") {
        html += `<tr data-k="${k}"><td>${ev.pass}</td><td>${esc(ev.process)}</td><td>[${ev.request}]</td><td>[${ev.work}]</td>
          <td class="${ev.fits ? "y" : "n"}">${ev.fits ? "fits" : "wait"}</td></tr>`;
      } else {
        html += `<tr class="fin" data-k="${k}"><td>${ev.pass}</td><td>${esc(ev.process)}</td><td>+[${ev.released}]</td><td>[${ev.work}]</td><td>finished ✓</td></tr>`;
      }
    });
    this.$("trace").innerHTML = html;
  },

  highlightTrace(k) {
    this.$("trace").querySelectorAll("tr.active").forEach((r) => r.classList.remove("active"));
    const row = this.$("trace").querySelector(`tr[data-k="${k}"]`);
    if (row) { row.classList.add("active"); if (row.closest("details").open) scrollWithin(row.closest(".trace-wrap"), row); }
  },

  /* ---------------- Recovery Lab ---------------- */
  icons: { terminate: "✕", terminate_all: "☠", preempt: "⇄", rollback: "↺", lock_order: "⇅" },
  kinds: { terminate: "Recovery · termination", terminate_all: "Recovery · abort all",
           preempt: "Recovery · resource preemption", rollback: "Rollback", lock_order: "Mitigation · acquisition order" },

  renderRecovery(options, ctx) {
    const box = this.$("options");
    const mitigate = ctx.mode === "mitigate";
    this.$("rec-compare").hidden = true;
    this.setBadge("recovery", ctx.mode === "recover" ? "bad" : mitigate ? "warn" : "",
      ctx.mode === "recover" ? "recover" : mitigate ? "mitigate" : "");
    this.$("lab-empty").hidden = options.length > 0;
    this.$("lab-empty").textContent = ctx.invalid ? "Fix the input to get resolution strategies."
      : ctx.pending ? "Calculating resolution strategies…" : "No deadlock and no risk → nothing to resolve. ✔";
    if (ctx.advice) this.$("res-advice").innerHTML = `<b>${ctx.mode === "recover" ? "Deadlock detected → recover" : mitigate ? "Potential deadlock → mitigate" : "All clear"}.</b> ${esc(ctx.advice)}`;
    box.innerHTML = "";
    options.forEach((o, i) => {
      const card = document.createElement("button");
      card.className = "opt" + (o.recommended ? " rec" : "");
      card.dataset.s = o.strategy;
      card.style.animationDelay = i * 55 + "ms";
      card.innerHTML = `
        <div class="opt-top"><div class="opt-ico">${this.icons[o.strategy] || "•"}</div>
          <div><div class="opt-title">${esc(o.title)}</div><div class="opt-kind">${this.kinds[o.strategy] || ""}</div></div></div>
        <p>${esc(o.description)}</p>
        ${o.warning ? `<div class="warn-line">⚠ ${esc(o.warning)}</div>` : ""}
        ${o.protected && o.protected.length ? `<div class="warn-line prot">🛡 ${o.protected.map(esc).join(", ")} protected by aging (starvation guard)</div>` : ""}
        <div class="opt-foot">
          <span class="${o.resolved ? "verified" : "unverified"}">${o.resolved
            ? (mitigate ? "✓ verified: risk removed" : "✓ verified: clears deadlock")
            : (mitigate ? "✗ risk remains" : "✗ still deadlocked")}</span>
          <span class="cost" title="base victim cost + aging penalty">cost ${o.aging ? `${o.base_cost} <em>+${o.aging} aging</em>` : o.cost}</span>
        </div>`;
      card.onclick = () => {
        box.querySelectorAll(".opt").forEach((c) => c.classList.toggle("sel", c === card));
        this.compare(this.$("rec-compare"), o, ctx);
      };
      box.appendChild(card);
    });
  },

  /* Generic before/after comparison used by Prevention, Avoidance and Recovery.
     o = {title, after_state, after_result}, ctx = {state, result, apply, applyLabel} */
  compare(el, o, ctx) {
    const id = el.id;
    el.hidden = false;
    el.innerHTML = `
      <div class="cmp-side"><h4>BEFORE</h4><svg id="${id}-b" viewBox="0 0 800 560"></svg><p id="${id}-bt"></p></div>
      <div class="cmp-arrow">⟹</div>
      <div class="cmp-side"><h4>AFTER <span>· ${esc(o.title)}</span></h4><svg id="${id}-a" viewBox="0 0 800 560"></svg><p id="${id}-at"></p></div>
      ${ctx.apply ? `<div class="cmp-actions"><button class="btn neon">${ctx.applyLabel || "⚡ Apply to system"}</button></div>` : ""}`;
    Graph.render(this.$(id + "-b"), ctx.state, ctx.result, { view: "rag", animate: true });
    Graph.render(this.$(id + "-a"), o.after_state, o.after_result, { view: "rag", animate: true });
    const summary = (r, s) => !s.processes.length ? "No processes left."
      : r.is_deadlocked ? `<span style="color:var(--red)">DEADLOCK</span> · stuck: ${r.deadlocked.concat(r.blocked).map(esc).join(", ")}`
      : `<span style="color:var(--green)">NO DEADLOCK</span> · order: ${r.completion_order.map(esc).join(" → ")}`;
    this.$(id + "-bt").innerHTML = summary(ctx.result, ctx.state);
    this.$(id + "-at").innerHTML = summary(o.after_result, o.after_state);
    if (ctx.apply) el.querySelector(".cmp-actions button").onclick = () => ctx.apply(o);
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  },

  /* ---------------- Prevention ---------------- */
  renderPrevention(protocols, ctx) {
    const box = this.$("prev-list");
    this.$("prev-compare").hidden = true;
    const fixes = protocols.filter((p) => p.simulated && p.resolved).length;
    this.setBadge("prevention", fixes ? "ok" : "", fixes ? fixes + " fix" + (fixes > 1 ? "es" : "") : "");
    if (ctx.invalid) { box.innerHTML = '<p class="desc">Fix the input to analyse prevention protocols.</p>'; return; }
    if (!protocols.length) { box.innerHTML = '<p class="desc">Add processes and resources to analyse prevention.</p>'; return; }
    box.innerHTML = "";
    protocols.forEach((p, i) => {
      const card = document.createElement("div");
      card.className = "prev " + (p.simulated ? (p.resolved ? "fix" : "nofix") : p.key === "mutual_exclusion" ? "na" : "clean");
      card.style.animationDelay = i * 60 + "ms";
      const order = p.ordering && p.ordering.length
        ? `<div class="ordering">${p.ordering.map((o) => `<span>F(${esc(o.resource)})=${o.order}</span>`).join("<i>&lt;</i>")}</div>` : "";
      card.innerHTML = `
        <div class="prev-head"><span class="cond-ico">${this.condIcons[p.key] || "•"}</span>
          <div><div class="opt-kind">Deny: ${esc(p.condition)}</div><div class="opt-title">${esc(p.technique)}</div></div>
          <span class="cond-flag ${p.holds ? "on" : "off"}">${p.holds ? "holds now" : "denied"}</span></div>
        <p class="rule">${esc(p.rule)}</p>${order}
        ${p.violators.length ? `<div class="viol"><b>Violators:</b> ${p.violators.map((v) => `<span class="chip bad">${esc(v)}</span>`).join(" ")}</div>
          <ul class="acts">${p.actions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
        <div class="prev-verdict">${esc(p.verdict)}</div>
        <ul class="drawbacks">${p.drawbacks.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
        ${p.simulated ? `<button class="btn mini sim">▶ Show before / after</button>` : ""}`;
      if (p.simulated) {
        card.querySelector(".sim").onclick = () => {
          box.querySelectorAll(".prev").forEach((c) => c.classList.toggle("sel", c === card));
          this.compare(this.$("prev-compare"), { ...p, title: "enforce " + p.technique.toLowerCase() },
            { ...ctx, applyLabel: "⚡ Enforce protocol on system" });
        };
      }
      box.appendChild(card);
    });
  },

  /* ---------------- Avoidance ---------------- */
  renderAvoidance(state, safety, ctx = {}) {
    const v = this.$("av-verdict");
    this.$("rq-steps").innerHTML = "";
    this.$("rq-actions").hidden = true;
    if (!safety) {
      v.className = "av-verdict";
      v.textContent = ctx.invalid ? "Fix the input to run the safety algorithm." : "";
      ["av-seq", "av-need", "av-trace", "av-sets", "rq-vec", "rq-proc"].forEach((id) => (this.$(id).innerHTML = ""));
      this.setBadge("avoidance", "", "");
      return;
    }
    const n = state.processes.length;
    v.className = "av-verdict " + (!n ? "" : safety.safe ? "ok" : "bad");
    v.innerHTML = `<b>${!n ? "EMPTY SYSTEM" : safety.safe ? "SAFE STATE" : "UNSAFE STATE"}</b><span>${esc(safety.message)}</span>`;
    this.setBadge("avoidance", !n ? "" : safety.safe ? "ok" : "bad", !n ? "" : safety.safe ? "safe" : "unsafe");

    const chips = (list, cls) => list.map((p, i) => `<span class="chip ${cls}" style="animation-delay:${i * 70}ms">${esc(p)}</span>`);
    let seq = chips(safety.sequence, "").join('<span class="arrow">→</span>');
    if (!safety.safe) seq += (seq ? '<span class="arrow">→</span>' : "") + chips(safety.unsafe, "bad").join(" ");
    this.$("av-seq").innerHTML = seq || '<span class="desc">—</span>';

    // Need matrix (hover a cell for Max − Allocation)
    let html = "<thead><tr><th>Process</th>" + state.resources.map((r) => `<th>${esc(r)}</th>`).join("") + "</tr></thead><tbody>";
    state.processes.forEach((p, i) => {
      const bad = safety.unsafe.includes(p);
      html += `<tr><td class="${bad ? "neg" : ""}">${esc(p)}</td>` + safety.need[i].map((x, r) =>
        `<td title="Max ${safety.max[i][r]} − Allocation ${state.allocation[i][r]}">${x}</td>`).join("") + "</tr>";
    });
    html += '<tr class="foot"><td>Available</td>' + safety.available.map((a) => `<td>${a}</td>`).join("") + "</tr>";
    this.$("av-need").innerHTML = n && state.resources.length ? html + "</tbody>" : "";

    // safety-algorithm trace
    let t = "<tr><th>Pass</th><th>Process</th><th>Need</th><th>Work</th><th>Result</th></tr>";
    t += `<tr><td>0</td><td>—</td><td></td><td>[${safety.available}]</td><td>Work = Available</td></tr>`;
    safety.trace.forEach((ev) => {
      t += ev.type === "check"
        ? `<tr><td>${ev.pass}</td><td>${esc(ev.process)}</td><td>[${ev.need}]</td><td>[${ev.work}]</td><td class="${ev.fits ? "y" : "n"}">${ev.fits ? "Need ≤ Work" : "wait"}</td></tr>`
        : `<tr class="fin"><td>${ev.pass}</td><td>${esc(ev.process)}</td><td>+[${ev.released}]</td><td>[${ev.work}]</td><td>finish ✓</td></tr>`;
    });
    this.$("av-trace").innerHTML = t;

    this.drawSets(safety.safe, ctx.deadlocked, n);

    // resource-request form (keeps the previous selection / vector when possible)
    const sel = this.$("rq-proc"), prev = sel.value;
    sel.innerHTML = state.processes.map((p) => `<option>${esc(p)}</option>`).join("");
    if (state.processes.includes(prev)) sel.value = prev;
    const old = [...this.$("rq-vec").querySelectorAll("input")].map((x) => +x.value || 0);
    this.$("rq-vec").innerHTML = state.resources.map((r, k) =>
      `<label>${esc(r)}<input type="number" min="0" max="99" value="${old.length === state.resources.length ? old[k] : 0}"></label>`).join("");
  },

  /* nested sets: deadlock ⊂ unsafe; everything else is safe. A marker shows the current state. */
  drawSets(safe, dead, n) {
    const svg = this.$("av-sets");
    svg.innerHTML = `
      <rect x="4" y="4" width="292" height="182" rx="14" class="set safe"/>
      <text x="18" y="28" class="set-l safe">SAFE</text>
      <ellipse cx="190" cy="105" rx="100" ry="74" class="set unsafe"/>
      <text x="150" y="50" class="set-l unsafe">UNSAFE</text>
      <ellipse cx="210" cy="124" rx="56" ry="38" class="set dead"/>
      <text x="210" y="112" class="set-l dead" text-anchor="middle">DEADLOCK</text>`;
    if (!n) return;
    const pt = dead ? [210, 136] : safe ? [55, 115] : [128, 118];
    svg.insertAdjacentHTML("beforeend",
      `<g class="here ${dead ? "dead" : safe ? "safe" : "unsafe"}" transform="translate(${pt[0]},${pt[1]})"><circle r="7"/><circle r="14" class="ring"/></g>`);
  },

  renderBankers(out, ctx) {
    const steps = this.$("rq-steps");
    const list = out.steps || (out.errors || []).map((e) => ({ ok: false, text: e }));
    steps.innerHTML = list.map((s, i) => `<li class="${s.ok ? "ok" : "bad"}" style="animation-delay:${i * 120}ms">${esc(s.text)}</li>`).join("");
    const verdict = { grant: ["ok", "✓ REQUEST GRANTED — state stays safe"], wait: ["warn", "⏳ PROCESS MUST WAIT"],
                      error: ["bad", "✗ ERROR"] }[out.decision] || ["bad", "✗ ERROR"];
    steps.insertAdjacentHTML("beforeend", `<li class="final ${verdict[0]}" style="animation-delay:${list.length * 120}ms">${verdict[1]}</li>`);
    const act = this.$("rq-actions");
    act.hidden = out.decision !== "grant";
    if (out.decision === "grant") this.$("btn-rq-apply").onclick = () => ctx.apply(out);
  },

  /* ---------------- Starvation ---------------- */
  renderStarvation(state, history, sim, cfg = {}) {
    const maxN = cfg.max || 3;
    if (cfg.penalty) this.$("st-pen").textContent = cfg.penalty;
    this.$("st-max").textContent = maxN;
    const names = [...new Set([...state.processes, ...Object.keys(history)])];
    this.$("st-history").innerHTML = names.length ? names.map((p) => {
      const c = history[p] || 0, gone = !state.processes.includes(p);
      return `<div class="hist-row ${c >= maxN ? "prot" : ""}"><span class="hn">${esc(p)}${gone ? " <small>(terminated)</small>" : ""}</span>
        <span class="hbar"><i style="width:${Math.min(100, (c / maxN) * 100)}%"></i></span>
        <span class="hc">${c}×${c >= maxN ? " 🛡" : ""}</span></div>`;
    }).join("") : '<p class="desc">No processes.</p>';
    const anyHist = Object.values(history).some((c) => c > 0);
    this.setBadge("starvation", Object.values(history).some((c) => c >= maxN) ? "warn" : "", anyHist ? "aging" : "");

    const box = this.$("st-sim"), sum = this.$("st-summary");
    if (!sim) { box.innerHTML = '<p class="desc">Fix the input to run the simulation.</p>'; sum.textContent = ""; return; }
    sum.textContent = sim.summary;
    sum.className = "cond-summary " + (sim.without_aging.starved.length ? "bad" : "ok");
    if (!sim.without_aging.rounds.length) { box.innerHTML = ""; return; }
    const col = (run, label, cls) => `
      <div class="sim-col ${cls}"><h4>${label}</h4>
        ${run.rounds.map((r, i) => `<div class="sim-row" style="animation-delay:${i * 70}ms"><span class="rn">#${r.round}</span>
          <span class="rt">${r.victims.map((v) => `<b class="${run.starved.includes(v) ? "starved" : ""}">${esc(v)}</b>`).join(", ")}</span>
          <span class="rc">${esc(r.title)}</span></div>`).join("")}
        <div class="sim-count">victim counts: ${Object.entries(run.counts).filter(([, c]) => c).map(([p, c]) =>
          `<span class="${run.starved.includes(p) ? "starved" : ""}">${esc(p)} ${c}×</span>`).join(" · ")}</div>
      </div>`;
    box.innerHTML = col(sim.without_aging, "Without aging · min cost only", "no") + col(sim.with_aging, "With aging", "yes");
  },
};
