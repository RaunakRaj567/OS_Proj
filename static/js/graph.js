/* ==========================================================================
   graph.js — MODULE 3 (visual): draws three views of the system as animated SVG
     RAG   Resource Allocation Graph (holds / waits-for edges)
     WFG   Wait-For Graph: process dependencies, deadlock cycles in red
     LOCK  Resource-acquisition (lock-order) graph: Ra → Rb when a process holds
           Ra and still needs Rb. A cycle here = POTENTIAL circular wait.
   and plays the step-by-step "detection scan" animation from the engine's trace.

   Layout: processes on an outer ring, resources on an inner ring. Each
   resource is rotated toward the processes it is connected to, so cycles
   look like cycles.
   ========================================================================== */

const NS = "http://www.w3.org/2000/svg";
const W = 800, H = 560, CX = 400, CY = 280;

function svgEl(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const rad = (d) => (d * Math.PI) / 180;
const angDist = (a, b) => { const d = Math.abs(((a - b) % 360 + 540) % 360 - 180); return d; };

const Graph = {
  /* ---------------- layout ---------------- */
  layout(state, view) {
    const n = state.processes.length, m = state.resources.length;
    const pos = {};
    if (view === "lock") {
      const R = m <= 1 ? 0 : Math.min(220, 130 + m * 14);
      state.resources.forEach((r, k) => {
        const a = -90 - (m >= 2 ? 180 / m : 0) + (360 * k) / Math.max(m, 1);
        pos[r] = { x: CX + R * Math.cos(rad(a)), y: CY + R * Math.sin(rad(a)) };
      });
      return pos;
    }
    const Rp = n <= 1 ? 0 : Math.min(228, 150 + n * 9);
    const start = n >= 2 ? -90 - 180 / n : -90;
    const pAng = {};
    state.processes.forEach((p, i) => {
      const a = start + (360 * i) / Math.max(n, 1);
      pAng[p] = a;
      pos[p] = { x: CX + Rp * Math.cos(rad(a)), y: CY + Rp * Math.sin(rad(a)) };
    });
    if (view === "wfg" || m === 0) return pos;

    if (n === 0) {
      const R = m === 1 ? 0 : 160;
      state.resources.forEach((r, k) => {
        const a = -90 + (360 * k) / m;
        pos[r] = { x: CX + R * Math.cos(rad(a)), y: CY + R * Math.sin(rad(a)) };
      });
      return pos;
    }

    // desired angle of each resource = circular mean of the processes touching it
    const desired = state.resources.map((r, k) => {
      let sx = 0, sy = 0;
      state.processes.forEach((p, i) => {
        const w = (state.allocation[i][k] > 0 ? 1 : 0) + (state.request[i][k] > 0 ? 1 : 0);
        sx += w * Math.cos(rad(pAng[p])); sy += w * Math.sin(rad(pAng[p]));
      });
      const has = Math.hypot(sx, sy) > 1e-6;
      return { k, a: has ? (Math.atan2(sy, sx) * 180) / Math.PI : (360 * k) / m, has };
    });

    if (m === 1) {
      const d = desired[0];
      const R = d.has && n > 2 ? Rp * 0.35 : 0;
      pos[state.resources[0]] = { x: CX + R * Math.cos(rad(d.a)), y: CY + R * Math.sin(rad(d.a)) };
      return pos;
    }
    const Rr = Math.max(92, Rp * 0.5);
    const sorted = [...desired].sort((a, b) => a.a - b.a);
    let best = 0, bestCost = Infinity;
    for (let phi = 0; phi < 360; phi += 3) {
      let c = 0;
      sorted.forEach((d, j) => { if (d.has) c += angDist(d.a, phi + (360 * j) / m) ** 2; });
      if (c < bestCost) { bestCost = c; best = phi; }
    }
    sorted.forEach((d, j) => {
      const a = best + (360 * j) / m;
      pos[state.resources[d.k]] = { x: CX + Rr * Math.cos(rad(a)), y: CY + Rr * Math.sin(rad(a)) };
    });
    return pos;
  },

  resWidth(name, total) {
    const dots = total <= 8 ? total * 13 + 10 : 60;
    return Math.max(72, 18 + name.length * 8.2, dots);
  },

  /* boundary point of a node toward (tx,ty) */
  boundary(node, tx, ty) {
    const dx = tx - node.x, dy = ty - node.y, len = Math.hypot(dx, dy) || 1;
    if (node.kind === "proc") return { x: node.x + (dx / len) * 33, y: node.y + (dy / len) * 33 };
    const hw = node.w / 2 + 3, hh = 28;
    const t = Math.min(hw / (Math.abs(dx) || 1e-9), hh / (Math.abs(dy) || 1e-9));
    return { x: node.x + dx * t, y: node.y + dy * t };
  },

  /* ---------------- render ---------------- */
  render(svg, state, result, opts = {}) {
    const view = opts.view || "rag";
    const lockView = view === "lock";
    const atRisk = new Set(opts.atRisk || []);
    if (svg._scanToken) svg._scanToken.cancelled = true;
    svg.innerHTML = "";
    svg.classList.remove("scanning");
    const id = svg.id;
    const status = (result && result.status) || {};
    const pos = this.layout(state, view);

    // defs: glow filter + arrow markers
    const defs = svgEl("defs", {}, svg);
    const colors = { c: "#22e5ff", m: "#ff3df2", r: "#ff3b5c", a: "#ffb020" };
    for (const k in colors) {
      const mk = svgEl("marker", { id: `${id}-ar-${k}`, viewBox: "0 0 10 10", refX: "9", refY: "5",
        markerWidth: "9", markerHeight: "9", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" }, defs);
      svgEl("path", { d: "M0,0 L10,5 L0,10 z", fill: colors[k] }, mk);
    }

    // ring guides
    const guides = svgEl("g", { opacity: ".35" }, svg);
    svgEl("circle", { cx: CX, cy: CY, r: 250, fill: "none", stroke: "rgba(34,229,255,.12)", "stroke-dasharray": "2 10" }, guides);
    svgEl("circle", { cx: CX, cy: CY, r: 130, fill: "none", stroke: "rgba(139,92,246,.15)", "stroke-dasharray": "2 8" }, guides);

    const nodes = {};
    if (!lockView) state.processes.forEach((p) => (nodes[p] = { ...pos[p], kind: "proc" }));
    if (view === "rag" || lockView) state.resources.forEach((r, k) => (nodes[r] = { ...pos[r], kind: "res", w: this.resWidth(r, state.total[k]) }));

    // which edges are part of a deadlock?
    const dead = new Set();
    const deadRes = new Set();
    ((result && result.deadlock_edges) || []).forEach((e) => {
      dead.add(`req|${e.from}|${e.resource}`); dead.add(`asg|${e.resource}|${e.to}`); dead.add(`wfg|${e.from}|${e.to}`);
      deadRes.add(e.resource);
    });

    const edgeLayer = svgEl("g", { class: "edges" + (opts.animate ? " enter" : "") }, svg);
    const assignEdges = {};
    const drawEdge = (from, to, cls, marker, label) => {
      const a = nodes[from], b = nodes[to];
      if (!a || !b) return null;
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      const off = 22;
      const ctrl = { x: (a.x + b.x) / 2 - (dy / len) * off, y: (a.y + b.y) / 2 + (dx / len) * off };
      const p0 = this.boundary(a, ctrl.x, ctrl.y), p1 = this.boundary(b, ctrl.x, ctrl.y);
      const path = svgEl("path", {
        d: `M${p0.x},${p0.y} Q${ctrl.x},${ctrl.y} ${p1.x},${p1.y}`,
        class: "edge " + cls, "marker-end": `url(#${id}-ar-${marker})`,
      }, edgeLayer);
      if (label) {
        const mx = 0.25 * p0.x + 0.5 * ctrl.x + 0.25 * p1.x, my = 0.25 * p0.y + 0.5 * ctrl.y + 0.25 * p1.y;
        const t = svgEl("text", { x: mx, y: my + 4, class: "edge-label", "text-anchor": "middle" }, edgeLayer);
        t.textContent = label;
      }
      return path;
    };

    if (view === "rag") {
      state.processes.forEach((p, i) => {
        state.resources.forEach((r, k) => {
          const a = state.allocation[i][k], q = state.request[i][k];
          if (a > 0) {
            const isDead = dead.has(`asg|${r}|${p}`);
            const el = drawEdge(r, p, isDead ? "assign dead" : "assign", isDead ? "r" : "c", a > 1 ? "×" + a : "");
            (assignEdges[p] = assignEdges[p] || []).push({ el, r, units: a });
          }
          if (q > 0) {
            const isDead = dead.has(`req|${p}|${r}`);
            drawEdge(p, r, isDead ? "request dead" : "request", isDead ? "r" : "m", q > 1 ? "×" + q : "");
          }
        });
      });
    } else if (lockView) {
      const cyc = new Set();
      ((opts.risk && opts.risk.lock_order_cycles) || []).forEach((c) => c.hops.forEach((h) => cyc.add(h.from + "|" + h.to)));
      const merged = {};
      ((opts.risk && opts.risk.lock_order_edges) || []).forEach((e) => {
        const k = e.from + "|" + e.to;
        (merged[k] = merged[k] || { from: e.from, to: e.to, procs: [] }).procs.push(e.process);
      });
      Object.values(merged).forEach((e) => {
        const bad = cyc.has(e.from + "|" + e.to);
        drawEdge(e.from, e.to, bad ? "lock bad" : "lock", bad ? "r" : "a", [...new Set(e.procs)].join(","));
      });
    } else {
      const merged = {};
      ((result && result.wait_for_edges) || []).forEach((e) => {
        const k = e.from + "|" + e.to;
        (merged[k] = merged[k] || { from: e.from, to: e.to, res: [] }).res.push(e.resource);
      });
      Object.values(merged).forEach((e) => {
        const isDead = dead.has(`wfg|${e.from}|${e.to}`);
        drawEdge(e.from, e.to, isDead ? "wfg dead" : "wfg", isDead ? "r" : "a", e.res.join(","));
      });
    }

    // nodes
    const nodeLayer = svgEl("g", {}, svg);
    const nodeEls = {}, resDots = {};
    let order = 0;
    if (view === "rag" || lockView) {
      const lockRes = new Set();
      if (lockView) ((opts.risk && opts.risk.lock_order_cycles) || []).forEach((c) => c.cycle.forEach((r) => lockRes.add(r)));
      state.resources.forEach((r, k) => {
        const nd = nodes[r];
        const held = state.allocation.reduce((s, row) => s + row[k], 0);
        // outer <g> positions the node; inner <g> is free to animate its own CSS transform
        const holder = svgEl("g", { transform: `translate(${nd.x},${nd.y})` }, nodeLayer);
        const hot = lockView ? lockRes.has(r) : deadRes.has(r);
        const g = svgEl("g", { class: "node res" + (hot ? " res-dead" : "") + (opts.animate ? " enter" : "") }, holder);
        if (opts.animate) g.style.animationDelay = order++ * 60 + "ms";
        svgEl("rect", { x: -nd.w / 2, y: -26, width: nd.w, height: 52, rx: 10, class: "res-core" }, g);
        const label = svgEl("text", { x: 0, y: -6, class: "res-label" }, g);
        label.textContent = r;
        const t = state.total[k];
        resDots[r] = [];
        if (t <= 8) {
          const x0 = -((t - 1) * 13) / 2;
          for (let u = 0; u < t; u++) {
            resDots[r].push(svgEl("circle", { cx: x0 + u * 13, cy: 12, r: 4.6, class: "inst " + (u < held ? "held" : "free") }, g));
          }
        } else {
          const tx = svgEl("text", { x: 0, y: 16, class: "res-label", fill: "#22e5ff" }, g);
          tx.textContent = `${held}/${t} held`;
        }
        nodeEls[r] = g;
      });
    }
    if (!lockView) state.processes.forEach((p) => {
      const nd = nodes[p];
      const st = status[p] === "completes" && atRisk.has(p) ? "completes atrisk" : (status[p] || "");
      const holder = svgEl("g", { transform: `translate(${nd.x},${nd.y})` }, nodeLayer);
      const g = svgEl("g", { class: "node proc " + st + (opts.animate ? " enter" : "") }, holder);
      if (opts.animate) g.style.animationDelay = order++ * 60 + "ms";
      svgEl("circle", { r: 38, class: "proc-ring" }, g);
      svgEl("circle", { r: 29, class: "proc-core" }, g);
      const t = svgEl("text", { class: "proc-label" }, g);
      t.textContent = p;
      const title = svgEl("title", {}, g);
      title.textContent = `${p}: ${status[p] || "not analysed"}${atRisk.has(p) && status[p] === "completes" ? " (at risk of deadlock)" : ""}`;
      nodeEls[p] = g;
    });

    svg._layout = { nodes, nodeEls, assignEdges, resDots, view };
  },

  /* ---------------- detection scan animation ---------------- */
  scan(svg, state, result, { speed = 1.5, hud, onStep, onDone } = {}) {
    const L = svg._layout;
    if (!L || !result) return;
    if (svg._scanToken) svg._scanToken.cancelled = true;
    const token = { cancelled: false };
    svg._scanToken = token;

    svg.classList.add("scanning");
    const scannerWrap = svgEl("g", { class: "scanner-wrap" }, svg);
    const scanner = svgEl("circle", { r: 46, class: "scanner" }, scannerWrap);
    const step = 950 / speed;

    // live held-dot counters so released units visibly return to the pool
    const held = {};
    state.resources.forEach((r, k) => (held[r] = state.allocation.reduce((s, row) => s + row[k], 0)));

    hud.show(result.available, state.resources);
    hud.msg("Work ← Available. Looking for a process whose request fits…");

    const events = result.trace;
    let k = 0;
    const clearMarks = () => Object.values(L.nodeEls).forEach((g) => g.classList.remove("checking"));

    const next = () => {
      if (token.cancelled) return;
      if (k >= events.length) return finish();
      const ev = events[k];
      onStep && onStep(k);
      const g = L.nodeEls[ev.process], nd = L.nodes[ev.process];
      hud.pass(ev.pass);
      if (ev.type === "check") {
        clearMarks();
        scanner.style.opacity = 1;
        scannerWrap.style.transform = `translate(${nd.x}px,${nd.y}px)`;
        g.classList.add("checking");
        g.classList.remove("nofit");
        hud.msg(`<b>${esc(ev.process)}</b> request [${ev.request}] ≤ work [${ev.work}] ? ` +
          (ev.fits ? '<span class="y">YES → can finish</span>' : '<span class="n">NO → must wait</span>'));
        if (!ev.fits) setTimeout(() => !token.cancelled && g.classList.add("nofit"), step * 0.45);
      } else {
        g.classList.remove("checking", "nofit");
        g.classList.add("done");
        (L.assignEdges[ev.process] || []).forEach((a) => {
          a.el.classList.add("released");
          held[a.r] -= a.units;
          (L.resDots[a.r] || []).forEach((dot, u) => dot.setAttribute("class", "inst " + (u < held[a.r] ? "held" : "free")));
        });
        hud.work(ev.work, true);
        hud.msg(`<b>${esc(ev.process)}</b> finishes and releases [${ev.released}] → work = [${ev.work}]`);
      }
      k++;
      setTimeout(next, ev.type === "check" ? step : step * 1.1);
    };

    const finish = () => {
      scanner.style.opacity = 0;
      clearMarks();
      setTimeout(() => {
        if (token.cancelled) return;
        scannerWrap.remove();
        svg.classList.remove("scanning");
        Object.values(L.nodeEls).forEach((g) => g.classList.remove("done", "nofit"));
        L.view === "rag" && Object.values(L.assignEdges).flat().forEach((a) => a.el.classList.remove("released"));
        state.resources.forEach((r, k2) => {
          const h = state.allocation.reduce((s, row) => s + row[k2], 0);
          (L.resDots[r] || []).forEach((dot, u) => dot.setAttribute("class", "inst " + (u < h ? "held" : "free")));
        });
        if (result.is_deadlocked) {
          const stuck = result.deadlocked.concat(result.blocked);
          hud.msg(`No more requests fit. Stuck: <span class="n">${stuck.map(esc).join(", ")}</span> → <span class="n">DEADLOCK</span>`);
        } else {
          hud.msg(`All processes finished → <span class="y">NO DEADLOCK</span>`);
        }
        onDone && onDone(result.is_deadlocked);
      }, step * 0.6);
    };

    setTimeout(next, step * 0.8);
  },
};
