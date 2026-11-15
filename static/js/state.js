/* ==========================================================================
   state.js — MODULE 1 (UI side): holds the SystemState being edited and
   renders the Control Deck (resources list + Allocation / Request / Max matrices).
   Max (declared maximum claim) is used only by Banker's avoidance; it is kept
   >= Allocation + Request automatically while you edit.
   Every edit calls Store.changed(), which triggers automatic re-detection.
   ========================================================================== */

const MAX_PROC = 20, MAX_RES = 12, MAX_INST = 99;

const Store = {
  state: { processes: [], resources: [], total: [], allocation: [], request: [], max: [] },
  matrix: "allocation",          // which matrix tab is visible
  status: {},                    // latest per-process status from the engine
  listeners: [],

  onChange(fn) { this.listeners.push(fn); },
  changed(opts = {}) { this.listeners.forEach((fn) => fn(opts)); },

  set(newState, opts = {}) {
    const s = newState || {};
    this.state = {
      processes: [...(s.processes || [])],
      resources: [...(s.resources || [])],
      total: [...(s.total || [])],
      allocation: (s.allocation || []).map((r) => [...r]),
      request: (s.request || []).map((r) => [...r]),
      max: (s.max || []).map((r) => [...r]),
    };
    this.fixMax(true);
    this.status = {};
    Deck.render();
    this.changed(opts);
  },

  available() {
    const s = this.state;
    return s.total.map((t, r) => t - s.allocation.reduce((a, row) => a + (row[r] || 0), 0));
  },

  /* Max must cover Allocation + Request. Missing rows/cells are filled in; with raise=true
     any cell below Allocation + Request is raised to it. */
  fixMax(raise = true) {
    const s = this.state;
    s.max = s.processes.map((_, i) => s.resources.map((_, r) => {
      const floor = ((s.allocation[i] || [])[r] || 0) + ((s.request[i] || [])[r] || 0);
      const cur = (s.max[i] || [])[r];
      if (cur === undefined || cur === null || isNaN(cur)) return floor;
      return raise ? Math.max(cur, floor) : cur;
    }));
  },

  uniqueName(prefix, taken) {
    let k = 1;
    while (taken.includes(prefix + k)) k++;
    return prefix + k;
  },

  addProcess() {
    const s = this.state;
    if (s.processes.length >= MAX_PROC) return toast("Limit: " + MAX_PROC + " processes");
    s.processes.push(this.uniqueName("P", [...s.processes, ...s.resources]));
    s.allocation.push(s.resources.map(() => 0));
    s.request.push(s.resources.map(() => 0));
    s.max.push(s.resources.map(() => 0));
    Deck.render(); this.changed({ structural: true });
  },
  removeProcess(i) {
    const s = this.state;
    s.processes.splice(i, 1); s.allocation.splice(i, 1); s.request.splice(i, 1); s.max.splice(i, 1);
    Deck.render(); this.changed({ structural: true });
  },
  addResource() {
    const s = this.state;
    if (s.resources.length >= MAX_RES) return toast("Limit: " + MAX_RES + " resource types");
    s.resources.push(this.uniqueName("R", [...s.resources, ...s.processes]));
    s.total.push(1);
    s.allocation.forEach((row) => row.push(0));
    s.request.forEach((row) => row.push(0));
    s.max.forEach((row) => row.push(0));
    Deck.render(); this.changed({ structural: true });
  },
  removeResource(r) {
    const s = this.state;
    s.resources.splice(r, 1); s.total.splice(r, 1);
    s.allocation.forEach((row) => row.splice(r, 1));
    s.request.forEach((row) => row.splice(r, 1));
    s.max.forEach((row) => row.splice(r, 1));
    Deck.render(); this.changed({ structural: true });
  },
  clear() { this.set({}, { structural: true }); },
};

/* ---------- Control Deck renderer ---------- */
const Deck = {
  el: {},
  init() {
    this.el.res = document.getElementById("res-list");
    this.el.matrix = document.getElementById("matrix");
    document.getElementById("btn-add-res").onclick = () => Store.addResource();
    document.getElementById("btn-add-proc").onclick = () => Store.addProcess();
    document.querySelectorAll(".deck .tab").forEach((t) => {
      t.onclick = () => {
        document.querySelectorAll(".deck .tab").forEach((x) => x.classList.toggle("active", x === t));
        Store.matrix = t.dataset.matrix;
        this.renderMatrix();
      };
    });
  },

  render() { this.renderResources(); this.renderMatrix(); },

  renderResources() {
    const s = Store.state, avail = Store.available();
    this.el.res.innerHTML = "";
    s.resources.forEach((name, r) => {
      const row = document.createElement("div");
      row.className = "res-item";
      row.style.animationDelay = r * 40 + "ms";
      row.innerHTML = `
        <input type="text" value="${esc(name)}" maxlength="14" aria-label="Resource name">
        <div class="stepper"><button aria-label="fewer">−</button><span>${s.total[r]}</span><button aria-label="more">+</button></div>
        <span class="avail-badge ${avail[r] < 0 ? "neg" : ""}" title="Available">${avail[r]} free</span>
        <button class="x" title="Remove resource">✕</button>`;
      const [nameIn] = row.getElementsByTagName("input");
      const [minus, plus] = row.querySelectorAll(".stepper button");
      nameIn.oninput = () => { s.resources[r] = nameIn.value.trim(); this.renderMatrixHead(); Store.changed({ structural: true, debounce: true }); };
      minus.onclick = () => { if (s.total[r] > 0) { s.total[r]--; this.render(); Store.changed(); } };
      plus.onclick = () => { if (s.total[r] < MAX_INST) { s.total[r]++; this.render(); Store.changed(); } };
      row.querySelector(".x").onclick = () => Store.removeResource(r);
      this.el.res.appendChild(row);
    });
    if (!s.resources.length) this.el.res.innerHTML = '<p class="desc">No resources yet.</p>';
  },

  renderMatrixHead() {
    const head = this.el.matrix.querySelector("thead tr");
    if (!head) return;
    Store.state.resources.forEach((name, r) => { const th = head.children[r + 2]; if (th) th.textContent = name; });
  },

  renderMatrix() {
    const s = Store.state, key = Store.matrix, M = s[key], avail = Store.available();
    const t = this.el.matrix;
    t.className = "matrix " + (key === "request" ? "req" : key === "max" ? "mx" : "");
    if (!s.processes.length || !s.resources.length) {
      const msg = !s.resources.length ? "Add a resource first." : "Add a process to start.";
      t.innerHTML = `<tr><td class="desc" style="padding:14px">${msg}</td></tr>`;
      return;
    }
    let html = "<thead><tr><th></th><th>Process</th>" + s.resources.map((r) => `<th>${esc(r)}</th>`).join("") + "<th></th></tr></thead><tbody>";
    s.processes.forEach((p, i) => {
      const st = Store.status[p] || "";
      html += `<tr style="animation-delay:${i * 30}ms"><td><span class="st-dot ${st}" title="${st}"></span></td>
        <td class="pname"><input type="text" value="${esc(p)}" maxlength="10" data-p="${i}" aria-label="Process name"></td>` +
        s.resources.map((_, r) => `<td><input type="number" min="0" max="${MAX_INST}" value="${M[i][r]}" data-i="${i}" data-r="${r}" class="${M[i][r] ? "nz" : ""}"></td>`).join("") +
        `<td><button class="x" data-del="${i}" title="Remove process">✕</button></td></tr>`;
    });
    if (key === "max") {
      html += '<tr class="foot"><td></td><td colspan="' + (s.resources.length + 2) + '" style="text-align:left">Max ≥ Allocation + Request · Need = Max − Allocation</td></tr>';
    }
    if (key === "allocation") {
      html += '<tr class="foot"><td></td><td>Available</td>' + avail.map((a) => `<td class="${a < 0 ? "neg" : ""}">${a}</td>`).join("") + "<td></td></tr>";
    }
    t.innerHTML = html + "</tbody>";

    t.querySelectorAll("input[type=number]").forEach((inp) => {
      inp.oninput = () => {
        let v = parseInt(inp.value, 10);
        if (isNaN(v) || v < 0) v = 0;
        if (v > MAX_INST) v = MAX_INST;
        M[+inp.dataset.i][+inp.dataset.r] = v;
        inp.classList.toggle("nz", v > 0);
        if (key !== "max") Store.fixMax(true);     // keep Max >= Allocation + Request
        this.renderResources();
        if (key === "allocation") this.updateFoot();
        Store.changed({ debounce: true });
      };
      inp.onfocus = () => inp.select();
    });
    t.querySelectorAll("input[data-p]").forEach((inp) => {
      inp.oninput = () => { s.processes[+inp.dataset.p] = inp.value.trim(); Store.changed({ structural: true, debounce: true }); };
    });
    t.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => Store.removeProcess(+b.dataset.del)));
  },

  updateFoot() {
    const foot = this.el.matrix.querySelector("tr.foot");
    if (!foot) return;
    Store.available().forEach((a, r) => {
      const td = foot.children[r + 2];
      td.textContent = a; td.classList.toggle("neg", a < 0);
    });
  },

  updateStatusDots() {
    this.el.matrix.querySelectorAll("input[data-p]").forEach((inp) => {
      const dot = inp.closest("tr").querySelector(".st-dot");
      dot.className = "st-dot " + (Store.status[Store.state.processes[+inp.dataset.p]] || "");
    });
  },
};

/* Scroll `el` into view INSIDE its scrollable `box` only. Unlike el.scrollIntoView(),
   this never moves the page, so automatic updates (scan animation, trace timeline)
   cannot fight the user's own scrolling. */
function scrollWithin(box, el) {
  if (!box || !el) return;
  const b = box.getBoundingClientRect(), r = el.getBoundingClientRect();
  if (r.top < b.top) box.scrollTop -= b.top - r.top;
  else if (r.bottom > b.bottom) box.scrollTop += r.bottom - b.bottom;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
