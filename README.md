# 🛡️ Deadlock Sentinel: Automated Deadlock Detection Tool

**Problem statement.** Develop a tool that automatically detects potential deadlocks in system processes. The tool should analyze process dependencies and resource allocation to identify circular wait conditions and suggest resolution strategies.

**What the tool does:**

```
 process activity trace  ─┐
 (P1 acquire Printer …)   ├─► SystemState ─► DETECT ─────────────────────────► RESOLVE
 or allocation matrices  ─┘   (M1)           (M2)                              (M3)
                                             • actual deadlock: circular wait   • deadlock  → recovery
                                               in the wait-for graph            • potential → mitigation
                                             • POTENTIAL deadlock:              every strategy simulated
                                               unsafe state (Banker's) or       on a copy and re-verified
                                               lock-order inversion             by the detector
```

1. **Analyzes process dependencies and resource allocation.** Input is Allocation / Request / Max matrices, or a **process activity trace**. The tool builds the resource-allocation graph, the **wait-for graph** (process → process dependencies) and the **lock-order graph** (resource → resource acquisition order).
2. **Detects automatically.** Detection re-runs on every edit, and after **every event** of a trace. The tool reports the exact event where a potential deadlock first appears and the event that closed the circular wait.
3. **Identifies circular wait.** For an actual deadlock it names the cycle (`P1 → P2 → P1`), the resources on each hop, and the processes blocked behind it. For a potential deadlock it names the opposite lock order (`P1 takes Printer before Scanner; P2 takes Scanner before Printer`).
4. **Suggests resolution strategies.** Strategies are ranked by cost, verified by re-running detection, and checked for starvation. The best one is marked ★ and can be applied with one click.

| Verdict | Meaning | Suggested strategies |
| :--- | :--- | :--- |
| 🔴 **DEADLOCK DETECTED** | a circular wait exists now | **Recovery**: preempt, roll back, terminate one, terminate all |
| 🟠 **POTENTIAL DEADLOCK** (unsafe) | no safe sequence: a deadlock can occur if processes claim their maximum | **Mitigation**: suspend and roll back an at-risk process, enforce an acquisition order, and from then on grant requests only through Banker's check |
| 🟠 **POTENTIAL DEADLOCK** (lock order) | processes acquire shared resources in opposite orders | **Mitigation**: enforce one global acquisition order |
| 🟢 **NO DEADLOCK · NO RISK** | safe and consistently ordered | — |

### Syllabus topics covered (supporting the core)

| Topic | Role in the tool | Code |
| :--- | :--- | :--- |
| **Deadlock Characterization** | explains *why*: the four necessary conditions evaluated on the current state | `engine/characterization.py` |
| **Deadlock Detection** | the core detector (Work/Finish algorithm, wait-for graph, Tarjan SCC) | `engine/detection.py`, `cycles.py`, `wait_for_graph.py` |
| **Deadlock Avoidance** | Banker's safety algorithm powers *potential*-deadlock detection; resource-request algorithm in the *Avoidance* tab | `engine/avoidance.py`, `engine/potential.py` |
| **Deadlock Prevention** | one protocol per condition, simulated and verified (*Prevention* tab) | `handling/prevention.py` |
| **Deadlock Recovery** | resolution strategies for detected deadlocks | `output/recovery.py`, `handling/resolution.py` |
| **Starvation** | aging in victim selection plus a recurring-deadlock demo (*Starvation* tab) | `handling/starvation.py` |

It is a simulation only and never touches real operating-system processes.

📘 **Full theory, algorithms, worked examples and viva questions:** see [Theory.md](Theory.md).

---

## 🚀 Run it

```bash
pip install -r requirements.txt
python app.py                 # opens http://127.0.0.1:5050
python -m pytest -v           # 46 tests
```
Works on Python 3.8+.

**Quick demo:** open **Process activity trace** → **Example** → **Analyze trace**. The tool flags a potential deadlock at event #9 and the actual deadlock at event #14. Click any event to load that moment, then see **Resolution Strategies → Suggested**.

**Shortcuts:** <kbd>Space</kbd> runs the detection scan animation · <kbd>R</kbd> loads a random scenario.

---

## 🧾 Process activity trace (input format)

```
resource Printer 1        # resource type with 1 instance (undeclared ones get 1)
P1 claims Scanner         # optional maximum claim; lets the tool warn early
P1 acquire Printer        # granted if free, otherwise P1 WAITS
P1 release Printer        # waiting processes are served in order
```
Synonyms: `request/lock/wait`, `unlock/free`, `max`. A blocked process cannot issue another request, and the parser reports the line of any invalid event.

---

## 🧩 The three modules

| Module | Responsibility | Python | Browser |
| :--- | :--- | :--- | :--- |
| **M1 · System Input** | Build a valid `SystemState` from matrices, presets or a process trace | `deadlock_tool/state/` (validation, presets, random generator, `trace.py`) | `static/js/state.js` |
| **M2 · Detection Engine** | Actual deadlock, potential deadlock, characterization, Banker's | `deadlock_tool/engine/` (pure Python, no UI imports) | `static/js/graph.js` (RAG / WFG / lock-order views) |
| **M3 · Resolution Strategies** | Recovery and mitigation (verified), prevention, starvation control, report | `deadlock_tool/handling/`, `deadlock_tool/output/` | `static/js/results.js` |

[app.py](app.py) is a thin Flask layer that converts JSON to and from `SystemState` and calls the modules.

```
Edit / trace ─► /api/analyze  ─► validate (M1) ─► detect actual + potential (M2) ─► graph + findings
                /api/resolve  ─► recovery or mitigation (M3), each re-verified by M2
                /api/trace    ─► replay events, detection after every event
```

### Project layout
```
OS Project/
├── app.py                         Flask server + REST API
├── deadlock_tool/
│   ├── models.py                  SystemState, DetectionResult (shared contract)
│   ├── state/                     M1: validation.py, scenarios.py, trace.py (process activity trace)
│   ├── engine/                    M2: detection.py, wait_for_graph.py, cycles.py, analyzer.py,
│   │                                  potential.py (potential deadlocks), avoidance.py (Banker's),
│   │                                  characterization.py
│   ├── handling/                  M3: resolution.py (suggested strategies), prevention.py, starvation.py
│   └── output/                    M3: recovery.py (with aging), report.py
├── scenarios/                     16 preset JSON files (each stores its expected result)
├── templates/index.html           UI layout
├── static/css/style.css           futuristic theme + animations
├── static/js/                     api.js, state.js (M1), graph.js + results.js, main.js
└── tests/test_engine.py           46 tests
```

---

## 🔮 Potential-deadlock detection

- **Unsafe state** (Banker's safety algorithm on the declared Max): no safe sequence exists. Not deadlocked yet, but it can become deadlocked. Every deadlocked state is unsafe.
- **Lock-order inversion** (the idea behind Linux *lockdep*): the resource-acquisition graph has an edge `Ra → Rb` when a process holds Ra and still needs Rb. A cycle means processes take shared resources in opposite orders. With single-instance resources, every deadlock shows such a cycle first; a random-state test checks this.
- **At-risk processes** are drawn with a dashed amber ring. The **LOCK ORDER** graph view highlights the inverted cycle in red.

---

## 🧠 Inputs

| Input | Meaning |
| :--- | :--- |
| **Resources + Total** | Resource types and how many instances each has (e.g. `Disk = 2`) |
| **Allocation[i][r]** | Units of r that process i **holds** now |
| **Request[i][r]** | Units of r that process i is **waiting for** now (used by detection) |
| **Max[i][r]** | Declared **maximum claim** (used only by Banker's avoidance). Optional; defaults to Allocation + Request |
| Available | Derived: `Total − Σ Allocation` |
| Need | Derived: `Max − Allocation` |

**Validation rules (M1):**
- names must be unique and not empty;
- every number must be a whole number ≥ 0;
- a resource can't be over-allocated: Σ Allocation ≤ Total;
- Allocation + Request ≤ Total. A request that could never be granted is **invalid input, not a deadlock**;
- Max ≤ Total, and Allocation + Request ≤ Max (a process may not exceed its declared claim).

---

## 🔍 Deadlock characterization

A deadlock can occur only if **all four** conditions hold at the same time:

| Condition | Evaluated as |
| :--- | :--- |
| Mutual exclusion | some non-sharable resource instance is allocated (all resources here are non-sharable) |
| Hold and wait | some process holds ≥ 1 unit **and** waits for more |
| No preemption | resources are released only voluntarily (the simulated system never takes them back) |
| Circular wait | the wait-for graph has a cycle |

The conditions are **necessary, not sufficient**. A test checks on 300 random states that every deadlock has all four conditions. Preset **T4** shows all four holding with **no** deadlock (multi-instance).

---

## 🚧 Deadlock prevention: deny one condition

| Condition denied | Protocol simulated | Drawbacks shown |
| :--- | :--- | :--- |
| Mutual exclusion | Not simulated: printers, locks and so on are inherently non-sharable | cannot generally be denied |
| Hold and wait | **All-or-nothing**: violators release what they hold and re-request everything at once | low utilization, starvation |
| No preemption | **Preempt on block**: a holder whose request can't be granted now loses its resources | only for saveable state, starvation |
| Circular wait | **Resource ordering** F(R1) < F(R2) < …: holders of a higher-ordered resource release it before requesting a lower one | ordering burden |

Each protocol is applied to a copy of the state and **re-checked by the detection engine**. A 200-state random test confirms that every protocol leaves the system deadlock-free and the condition broken.

---

## ⚖️ Deadlock avoidance: Banker's algorithm

- **Safety algorithm:** `Work = Available`. Repeatedly finish any process with `Need ≤ Work`. Safe ⇔ all finish. The output is a **safe sequence**, e.g. ⟨P1, P3, P4, P0, P2⟩ for the textbook example (T13).
- **Resource-request algorithm:** (1) Request ≤ Need, else error. (2) Request ≤ Available, else wait. (3) Pretend to allocate and run the safety check: grant if safe, otherwise wait.
- **State space:** safe ⇒ no deadlock, and deadlocked ⊂ unsafe. Preset **T14** is *unsafe but not deadlocked*. A 300-state random test checks *safe ⇒ not deadlocked*.

---

## ⚙️ Deadlock detection

### 1. Deadlock detection algorithm: decides yes/no
```
Work = Available ; Finish[i] = False for all i
repeat: find i with !Finish[i] and Request[i] ≤ Work
        Work += Allocation[i] ; Finish[i] = True
until none found
deadlock ⇔ some Finish[i] is False
```
- **Intuition:** be optimistic. If a request fits, let the process finish and give everything back. Whoever can never be satisfied is stuck forever.
- Correct for **single- and multi-instance** resources. Time **O(m·n²)**.
- Unlike the textbook version, every process starts at `Finish = False`. That way the tool also reports processes that hold nothing but are *blocked by* the deadlock. The yes/no answer is identical.

### 2. Wait-for graph among the stuck processes: explains who waits for whom
Edge Pi → Pj (labelled with resource r) when Pi still needs r and Pj holds some of it.

### 3. Tarjan SCC + three-colour DFS: names the circular wait
- **Strongly connected components** (Tarjan's algorithm, O(V+E)) with at least 2 members are the **deadlock groups**. Their members are **deadlocked**. Any other stuck process is **blocked by the deadlock**.
- A **three-colour DFS** (white, grey, black; reaching a grey node again means a cycle) extracts one readable cycle per group, e.g. `P1 → P2 → P1`.

**Why every stuck set contains a cycle:** a stuck process waits for units that, after everyone finishable has finished, can only be held by other stuck processes. (Validation rule 4 guarantees they're not all its own.) So every stuck process has an outgoing edge to another stuck process, and a finite graph like that must contain a cycle.

### Single vs. multi-instance
| | A cycle in the RAG/WFG means… |
| :--- | :--- |
| All resources single-instance | cycle **⇔** deadlock |
| Some multi-instance | cycle is **necessary but not sufficient**. See preset **T4**: a cycle, but no deadlock |

A test checks the single-instance equivalence on 300 random systems, and another cross-checks the SCC code against NetworkX.

---

## 🩹 Deadlock recovery, simulated and verified

Every option is applied to a **copy** of the state and **re-checked by the detection engine**. The card shows the verified result, and a before/after graph appears when you select it.

| Strategy | Effect on the state | Cost used for ranking |
| :--- | :--- | :---: |
| Terminate victim (repeat until clear) | Remove the process; its units return to Available | 100/process + units lost |
| Terminate all deadlocked | Baseline | same |
| Preempt resource r from victim | `Alloc[v][r] → 0`, `Request[v][r] += units` (starvation warning) | 20 + 10/unit |
| Roll back victim | `Request[v] += Alloc[v]`, `Alloc[v] = 0` | 50 + 5/unit |

The cheapest strategy that clears the deadlock gets **★ RECOMMENDED**. **Apply to system** commits it, records the victims (for starvation control) and replays the scan.

---

## ⏳ Starvation

Starvation means one process is postponed indefinitely while the rest of the system progresses (in a deadlock, *none* of the set progresses). Pure minimum-cost victim selection can choose the **same victim every time** the deadlock recurs.

- **Aging:** each earlier selection adds **+60** to a process's victim cost. After **3** selections the process is **protected** and never recommended.
- **Victim history:** every applied recovery is recorded and shown as bars.
- **Recurring-deadlock simulation:** replays the current deadlock for 6 rounds *without* and *with* aging. In T2, P1 is the victim 6/6 times without aging, but at most 3 times with it.

---

## 🧪 Preset scenarios (= test fixtures)

| # | Scenario | Expected |
| :---: | :--- | :--- |
| T1 | Temporary wait | No deadlock: P1 → P2 |
| T2 | Two-process deadlock | {P1, P2} |
| T3 | Three-process cycle | {P1, P2, P3} |
| T4 | **Cycle but no deadlock** (multi-instance) | No deadlock: P3 → P4 → P1 → P2 |
| T5 | Multi-instance deadlock | {P1, P2, P3} |
| T6 | Waiting chain, no cycle | No deadlock: P2 → P1 → P3 |
| T7 | Deadlock + blocked process | Deadlocked {P1, P2}, **blocked {P4}**, P3 completes |
| T8 | One process holds several resources | {P1, P2} |
| T9 | T3 after terminating P1 | No deadlock: P3 → P2 |
| T10 | Two independent deadlock groups (DB locks) | {T1, T2} and {T3, T4}; T5 completes |
| T11 | Over-allocated resource | Validation error |
| T12 | Impossible request | Validation error |
| T13 | Banker's textbook example (A=10, B=5, C=7) | Safe: ⟨P1, P3, P4, P0, P2⟩. Request P1 (1,0,2) is granted |
| T14 | 12 tape drives | **Unsafe but not deadlocked** |
| T15 | Requests in resource order | No circular wait. Prevention finds no ordering violators |
| T16 | **Potential deadlock**: opposite lock order, nobody blocked yet | Not deadlocked. Unsafe + lock-order inversion. Fix: enforce Printer < Scanner |

---

## 🎨 UI features
- Boot sequence, particle-network background, perspective grid, neon glass panels
- **Automatic detection** on every edit, with a live status pill (STABLE / POTENTIAL DEADLOCK / DEADLOCK / INVALID) and a findings list
- **Process activity trace** with a clickable event timeline: the potential-risk and deadlock events are highlighted
- Animated graph:
  - request edges flow, deadlock cycles pulse red;
  - resource instance dots fill and empty;
  - toggle between the RAG, WFG and LOCK ORDER views; at-risk processes get a dashed amber ring
- **Detection scan animation:**
  - a scanner ring visits each process while the HUD shows the Work vector;
  - processes turn green as they finish and their released units flow back;
  - a red alarm sounds if anything is left stuck;
  - the trace table highlights each step as it happens
- Explanations in plain English, counters, circular-wait chips, completion order
- Four-condition characterization tiles
- *Resolution Strategies* panel: **Suggested** (recovery or mitigation), Prevention, Avoidance and Starvation tabs, each with a status badge
- Before/after graph comparison with one-click Apply for resolutions, prevention protocols and Banker's grants
- Save/Load scenario JSON, Markdown report export, random scenarios
- Responsive down to phone width, and respects `prefers-reduced-motion`

## ⚠️ Limitations / future work
- Simulation only. Real lock waits (e.g. `/proc/locks`, database lock tables) could be converted into the process-trace format by a small adapter.
- Lock-order analysis relies on what processes hold and still need; declaring Max claims makes the early warnings much stronger.
- Victim cost is a simple fixed formula plus aging. Process priorities could be added.
- Mutual exclusion is explained but not simulated (resources are not marked sharable).
