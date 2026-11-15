# Theory: Deadlock Sentinel, the Automated Deadlock Detection Tool

This document explains everything behind the project: the problem it solves, the operating-system theory it is based on, the algorithms it uses (with worked examples from the tool's own presets), and how the code is organised.

> **Problem statement.** Develop a tool that automatically detects potential deadlocks in system processes. The tool should analyze process dependencies and resource allocation to identify circular wait conditions and suggest resolution strategies.

---

## Contents

1. [Project overview](#1-project-overview)
2. [System model](#2-system-model)
3. [What is a deadlock?](#3-what-is-a-deadlock)
4. [Deadlock characterization](#4-deadlock-characterization)
5. [Methods for handling deadlocks](#5-methods-for-handling-deadlocks)
6. [Deadlock prevention](#6-deadlock-prevention)
7. [Deadlock avoidance (Banker's algorithm)](#7-deadlock-avoidance-bankers-algorithm)
8. [Deadlock detection](#8-deadlock-detection)
9. [Potential-deadlock detection (the core of the tool)](#9-potential-deadlock-detection-the-core-of-the-tool)
10. [Deadlock recovery](#10-deadlock-recovery)
11. [Starvation](#11-starvation)
12. [Resolution strategies engine](#12-resolution-strategies-engine)
13. [Process activity trace and automatic monitoring](#13-process-activity-trace-and-automatic-monitoring)
14. [Architecture and code map](#14-architecture-and-code-map)
15. [Input validation](#15-input-validation)
16. [Testing and correctness checks](#16-testing-and-correctness-checks)
17. [Preset scenarios](#17-preset-scenarios)
18. [Limitations](#18-limitations)
19. [Viva / review questions](#19-viva--review-questions)
20. [Glossary](#20-glossary)
21. [References](#21-references)

---

## 1. Project overview

Deadlock Sentinel is a web-based simulator. It takes a description of a system (processes, resources, and who holds and waits for what) and works in three steps:

| Step | Question it answers | Output |
| :--- | :--- | :--- |
| **Analyze** | How do the processes depend on each other and on the resources? | Resource-allocation graph, wait-for graph, lock-order graph |
| **Detect** | Is the system deadlocked **now**? Could it deadlock **later**? | One of four verdicts, findings, the circular wait, the stuck processes |
| **Resolve** | What should be done about it? | Ranked strategies, each simulated on a copy of the system and re-verified |

The four verdicts:

| Verdict | Meaning |
| :--- | :--- |
| 🔴 **DEADLOCK DETECTED** | A circular wait exists right now. Some processes can never proceed. |
| 🟠 **POTENTIAL DEADLOCK** (unsafe state) | Nobody is stuck yet, but there is no safe sequence. If the processes ask for their declared maximum, a deadlock can occur. |
| 🟠 **POTENTIAL DEADLOCK** (lock-order inversion) | The state is safe, but processes acquire shared resources in opposite orders. A different timing would produce a circular wait. |
| 🟢 **NO DEADLOCK · NO RISK** | Safe state and a consistent acquisition order. |

Detection is **automatic**: it re-runs after every edit, and after every event when a process activity trace is replayed. It is a simulation only and never touches real operating-system processes.

---

## 2. System model

An operating system has a finite number of **resources** shared by competing **processes**.

- **Resource types** R1, R2, …, Rm (printer, scanner, disk, database lock, mutex…).
- Each type Rj has **Wj instances** (e.g. 2 identical disks). Any instance of a type satisfies a request for that type.
- A process uses a resource in three steps:
  1. **Request**: if the resource cannot be granted immediately, the process **waits**.
  2. **Use**: it operates on the resource.
  3. **Release**: it gives the resource back.

### Data structures used by the tool

With *n* processes and *m* resource types:

| Name | Shape | Meaning |
| :--- | :--- | :--- |
| `Total[j]` | m | total instances of resource j |
| `Allocation[i][j]` | n × m | units of j **held** by process i |
| `Request[i][j]` | n × m | units of j that process i is **waiting for right now** (used by detection) |
| `Max[i][j]` | n × m | **maximum** units of j that process i may ever claim (used by avoidance; optional) |
| `Available[j]` | m | derived: `Total[j] − Σi Allocation[i][j]` |
| `Need[i][j]` | n × m | derived: `Max[i][j] − Allocation[i][j]` |

If no Max is declared, the tool uses `Max = Allocation + Request`. This is the most conservative claim consistent with what is already happening.

Vector comparison: for vectors X and Y of length m, **X ≤ Y** means `X[j] ≤ Y[j]` for every j.

---

## 3. What is a deadlock?

> A set of processes is **deadlocked** when every process in the set is waiting for an event (usually the release of a resource) that can only be caused by another process in the same set.

None of them can run, release resources or be woken up, so they wait forever.

**Classic two-process example (preset T2):**

```
P1 holds R1 and waits for R2
P2 holds R2 and waits for R1
```
P1 can't continue until P2 releases R2, and P2 can't continue until P1 releases R1.

### Related but different situations

| Situation | Is anyone making progress? | Example |
| :--- | :--- | :--- |
| **Deadlock** | No process in the set progresses, ever | T2 above |
| **Starvation** | The system progresses, but one process is postponed indefinitely | The same process is chosen as recovery victim every time |
| **Livelock** | Processes keep changing state but do no useful work | Two processes repeatedly back off and retry at the same moment |
| **Blocked by a deadlock** | The process is not in the cycle but waits for a resource held by a deadlocked process | P4 in preset T7 |
| **Temporary wait** | The process waits, but the holder will finish and release | P2 in preset T1 |

The tool tells these apart. It labels each process **completes**, **deadlocked** (on the cycle), **blocked** (stuck behind the cycle) or **at risk** (potential deadlock).

---

## 4. Deadlock characterization

### 4.1 The four necessary conditions (Coffman et al., 1971)

A deadlock can arise **only if all four** of these hold simultaneously:

| # | Condition | Meaning | How the tool evaluates it |
| :---: | :--- | :--- | :--- |
| 1 | **Mutual exclusion** | At least one resource is non-sharable: only one process may use an instance at a time | Holds when any instance is allocated (every resource in the model is non-sharable) |
| 2 | **Hold and wait** | A process holds at least one resource while waiting for others | Some process has `Allocation > 0` **and** `Request > 0` |
| 3 | **No preemption** | Resources are released only voluntarily by the holder | Holds when anything is allocated (the simulated OS never takes resources back on its own) |
| 4 | **Circular wait** | Processes {P0 … Pk} exist where P0 waits for P1, P1 for P2, …, Pk for P0 | The wait-for graph contains a cycle |

The four conditions are **necessary, not sufficient**. If any one of them is missing, deadlock is impossible. All four holding does not guarantee a deadlock (see 4.3).

Condition 4 actually implies condition 2, but the four are listed separately because each one suggests a different prevention technique (section 6).

In the tool, these appear as the four tiles under **"Why? Deadlock characterization"**, each marked HOLDS or NOT MET, with a one-line reason.

### 4.2 Resource-Allocation Graph (RAG)

A directed graph with two kinds of vertices:

- **Process nodes** P1 … Pn (circles)
- **Resource nodes** R1 … Rm (rectangles, with one dot per instance)

and two kinds of edges:

- **Request edge** Pi → Rj: Pi is waiting for an instance of Rj (dashed magenta in the tool)
- **Assignment edge** Rj → Pi: an instance of Rj is held by Pi (solid cyan)

```
   ┌────┐  holds   ( P1 )  waits for  ┌────┐
   │ R1 │────────► (    ) ──────────► │ R2 │
   └────┘                             └────┘
     ▲                                  │
     │ waits for     ( P2 )      holds  │
     └────────────── (    ) ◄───────────┘
```

### 4.3 Cycles and deadlock: the key theorem

| Resource instances | Does a cycle in the RAG mean deadlock? |
| :--- | :--- |
| Every resource has **one instance** | **Yes**: cycle ⇔ deadlock |
| Some resource has **several instances** | **Not necessarily**: a cycle is necessary but not sufficient |
| No cycle at all | **No deadlock**, in both cases |

**Example: cycle but no deadlock (preset T4).** R1 and R2 each have 2 instances.

```
P1 holds R1, waits for R2        P3 holds R1 (needs nothing more)
P2 holds R2, waits for R1        P4 holds R2 (needs nothing more)
```
The graph contains the cycle P1 → R2 → P2 → R1 → P1. But P3 and P4 can finish and release their instances, so P1 and P2 then get what they need. The completion order is P3 → P4 → P1 → P2: **no deadlock**. The tool shows this as "cycle present, but multi-instance resources let everyone finish". That is why the tool runs the full detection algorithm (section 8.2) rather than only looking for cycles.

### 4.4 Wait-For Graph (WFG)

Removing the resource nodes and collapsing the edges gives a **wait-for graph** among processes:

> **Pi → Pj** if Pi is waiting for a resource that Pj currently holds.

The WFG shows the **process dependencies**: who is waiting on whom. With single-instance resources, a cycle in the WFG is exactly a deadlock. In the tool, select the **WFG** view. Each edge is labelled with the resource causing the wait, and deadlock cycles pulse red.

---

## 5. Methods for handling deadlocks

| Approach | Idea | When it acts | Cost |
| :--- | :--- | :--- | :--- |
| **Prevention** | Design the system so that one of the four conditions can never hold | At design time, always | Low resource utilization, restrictive |
| **Avoidance** | Use advance knowledge (Max claims) to refuse any request that could lead to deadlock | At every request | Needs Max claims in advance, plus a run-time check |
| **Detection + Recovery** | Allow deadlocks, detect them periodically, then break them | After the fact | Detection overhead plus lost work |
| **Ignore** ("ostrich algorithm") | Assume deadlocks are rare and let the operator reboot | Never | Used by most general-purpose OSes for application resources |

This tool implements prevention, avoidance, detection and recovery. It also adds **potential-deadlock detection** (section 9), which warns before a deadlock happens, and **starvation control** for recovery.

---

## 6. Deadlock prevention

Prevention guarantees that **at least one necessary condition can never hold**. In the tool's **Prevention** tab, each condition has a card that names the protocol and the processes that currently violate it. The card simulates enforcing the protocol on a copy of the state and re-checks it with the detection engine.

### 6.1 Deny mutual exclusion

- Make resources **sharable** (read-only files can be opened by many processes at once).
- **Usually impossible:** printers, mutex locks and tape drives are intrinsically non-sharable.
- *Tool:* explained only, not simulated.

### 6.2 Deny hold and wait

Two protocols:

1. A process must request **all** of its resources at once, before it starts executing.
2. A process may request resources only when it holds **none**: it must release everything before asking for more.

*Tool simulation ("all-or-nothing allocation"):* every process that holds something while waiting releases what it holds and re-requests everything together.

```
for each process i with Allocation[i] > 0 and Request[i] > 0:
    Request[i] += Allocation[i];  Allocation[i] = 0
```
After this, no process holds while waiting, so condition 2 is broken.

**Drawbacks:** low resource utilization (resources sit allocated but unused), and **starvation** (a process that needs several popular resources may wait forever).

### 6.3 Deny no preemption

Protocol: if a process that holds resources requests one that cannot be granted immediately, **all resources it holds are preempted** (implicitly released) and added to its waiting list. It restarts only when it can regain the old resources and get the new one.

*Tool simulation ("preempt on blocked request"):* every holder whose request exceeds `Available` releases what it holds.

**Drawbacks:** only practical for resources whose state can be saved and restored (CPU registers, memory pages), not for printers or tape drives. Repeated preemption can starve a process.

### 6.4 Deny circular wait (resource ordering)

Protocol: assign every resource type a unique number **F(R)**. A process may request Rj only if `F(Rj) > F(Ri)` for every Ri it currently holds. Equivalently, a process must release higher-numbered resources before requesting a lower-numbered one.

*Tool:* F(R) is the position of the resource in the list (`F(R1)=1 < F(R2)=2 < …`). A violator holds a resource whose order is ≥ the lowest-ordered resource it is requesting. It releases those and re-requests them in increasing order.

**Proof that ordering prevents circular wait.** Suppose a circular wait P0 → P1 → … → Pk → P0 existed, where Pi waits for resource Ri held by Pi+1. Pi+1 holds Ri and requests Ri+1, so by the protocol `F(Ri) < F(Ri+1)`. Going around the cycle gives `F(R0) < F(R1) < … < F(Rk) < F(R0)`, which is impossible. ∎

**Drawbacks:** programmers must follow the order, which may not match the natural order of use, and processes may have to acquire resources earlier than they need them.

### 6.5 Worked example (preset T2)

| Protocol | Violators | Simulated action | Verified result |
| :--- | :--- | :--- | :--- |
| Hold and wait | P1, P2 | Both release what they hold and re-request everything at once | No deadlock |
| No preemption | P1, P2 | Both are blocked holders, so both are preempted | No deadlock |
| Circular wait | P2 | P2 holds R2 but requests R1 (F=1), so it releases R2 and re-requests in order | No deadlock |

---

## 7. Deadlock avoidance (Banker's algorithm)

Avoidance requires each process to declare its **maximum claim** in advance (the **Max** tab of the System Input panel). The system then grants a request **only if the resulting state is safe**.

### 7.1 Safe state and safe sequence

A sequence ⟨P_a, P_b, …, P_z⟩ of all processes is a **safe sequence** if, for every process in it, its remaining `Need` can be satisfied by `Available` plus the resources held by all the processes before it in the sequence.

A state is **safe** if a safe sequence exists.

```
┌─────────────────────────────────────────┐
│ SAFE                                    │
│            ┌───────────────────────┐    │
│            │ UNSAFE                │    │
│            │        ┌───────────┐  │    │
│            │        │ DEADLOCK  │  │    │
│            │        └───────────┘  │    │
│            └───────────────────────┘    │
└─────────────────────────────────────────┘
```

- **safe ⇒ no deadlock**
- **unsafe ⇒ deadlock is possible**, not certain: processes might not actually request their maximum
- **deadlocked ⇒ unsafe** (the deadlocked states are a subset of the unsafe ones)

The tool's Avoidance tab draws this diagram and marks where the current state falls.

*Why deadlocked ⇒ unsafe in this tool:* validation guarantees `Max ≥ Allocation + Request`, so `Need ≥ Request`. A process stuck in detection (its Request never fits) is therefore also stuck in the safety algorithm (its larger Need never fits).

### 7.2 Safety algorithm

```
Work   = Available
Finish = [false] * n
repeat
    find i with Finish[i] == false and Need[i] ≤ Work
    if found:  Work = Work + Allocation[i];  Finish[i] = true
until no such i
safe  ⇔  Finish[i] == true for all i
```
Time complexity: **O(m · n²)**. The order in which processes finish is the safe sequence.

### 7.3 Resource-request algorithm

When process Pi asks for vector `Request_i`:

1. If `Request_i ≤ Need_i`, go to step 2. Otherwise this is an **error**: the process has exceeded its maximum claim.
2. If `Request_i ≤ Available`, go to step 3. Otherwise Pi must **wait**, because the resources are not free.
3. **Pretend** to allocate:
   ```
   Available    = Available    − Request_i
   Allocation_i = Allocation_i + Request_i
   Need_i       = Need_i       − Request_i
   ```
   Run the safety algorithm. If the new state is **safe**, **grant** the request. If it is **unsafe**, Pi must **wait** and the old state is restored.

The tool shows each step with ✓/✗, and **Grant & apply** commits a granted request.

### 7.4 Worked example (preset T13, the textbook example)

Resources A = 10, B = 5, C = 7.

| Process | Allocation (A B C) | Max (A B C) | Need (A B C) |
| :---: | :---: | :---: | :---: |
| P0 | 0 1 0 | 7 5 3 | 7 4 3 |
| P1 | 2 0 0 | 3 2 2 | 1 2 2 |
| P2 | 3 0 2 | 9 0 2 | 6 0 0 |
| P3 | 2 1 1 | 2 2 2 | 0 1 1 |
| P4 | 0 0 2 | 4 3 3 | 4 3 1 |

Available = (3, 3, 2). The safety algorithm, scanning P0…P4 repeatedly:

| Pass | Process | Need ≤ Work? | Work after |
| :---: | :---: | :---: | :---: |
| 1 | P0 | (7,4,3) ≤ (3,3,2)? no | |
| 1 | P1 | (1,2,2) ≤ (3,3,2)? **yes** | (5,3,2) |
| 1 | P2 | (6,0,0) ≤ (5,3,2)? no | |
| 1 | P3 | (0,1,1) ≤ (5,3,2)? **yes** | (7,4,3) |
| 1 | P4 | (4,3,1) ≤ (7,4,3)? **yes** | (7,4,5) |
| 2 | P0 | (7,4,3) ≤ (7,4,5)? **yes** | (7,5,5) |
| 2 | P2 | (6,0,0) ≤ (7,5,5)? **yes** | (10,5,7) |

Safe sequence: **⟨P1, P3, P4, P0, P2⟩**, so the state is safe.

Request examples (all verified by the tests):

| Request | Result | Why |
| :--- | :--- | :--- |
| P1 asks (1,0,2) | **Granted** | ≤ Need, ≤ Available, and the new state is still safe |
| then P4 asks (3,3,0) | **Wait** | not available (only (2,3,0) free) |
| then P0 asks (0,2,0) | **Wait** | available, but the resulting state is unsafe |
| then P3 asks (5,0,0) | **Error** | exceeds P3's remaining Need |

### 7.5 Unsafe is not the same as deadlocked (preset T14)

There are 12 tape drives.

| Process | Allocation | Max | Need |
| :---: | :---: | :---: | :---: |
| P0 | 5 | 10 | 5 |
| P1 | 2 | 4 | 2 |
| P2 | 3 | 9 | 6 |

Available = 2. P1 can finish (Work becomes 4), but then neither P0 (needs 5) nor P2 (needs 6) fits. The state is **unsafe**. Yet no process is waiting right now, so it is **not deadlocked**. A Banker's system would never have given P2 its third drive.

### 7.6 Single-instance alternative: claim edges

For single-instance resources, avoidance can use a RAG with **claim edges** (Pi ⇢ Rj, "Pi may request Rj in future"). A request is granted only if converting the claim edge into an assignment edge does not create a cycle. Banker's algorithm generalises this to multiple instances and is what the tool implements.

---

## 8. Deadlock detection

When neither prevention nor avoidance is used, the system must **detect** deadlocks and then **recover**.

### 8.1 Single-instance resources: wait-for-graph cycle

With one instance per resource type, a deadlock exists **if and only if** the wait-for graph has a cycle. A cycle search costs O(n²) on an adjacency matrix, or O(V + E) with adjacency lists.

### 8.2 Several instances: the detection algorithm

This is structurally the same as the safety algorithm, but it uses **Request** (what processes are waiting for now) instead of **Need** (their future maximum):

```
Work   = Available
Finish = [false] * n
repeat
    find i with Finish[i] == false and Request[i] ≤ Work
    if found:  Work = Work + Allocation[i];  Finish[i] = true
until no such i
deadlocked  ⇔  some Finish[i] == false   (those processes are stuck)
```

**Intuition ("be optimistic").** If a process's current request fits in the free resources, assume it gets them, finishes and returns everything it holds. If its request is still waiting, it will either eventually fit or be stuck forever. Any process that can never be satisfied, even after every other process has finished, is deadlocked.

- Complexity: **O(m · n²)**.
- Correct for single- **and** multi-instance resources (it handles T4 correctly).
- **Difference from the textbook:** the textbook starts `Finish[i] = true` for processes holding nothing. The tool starts every process at false, so it can also report processes that hold nothing but are **blocked by** the deadlock. The yes/no answer is identical.

**Detection versus avoidance, side by side:**

| | Detection algorithm | Safety algorithm |
| :--- | :--- | :--- |
| Vector compared with Work | **Request** (now) | **Need** (future maximum) |
| Question | Is the system deadlocked now? | Can everyone finish even in the worst case? |
| A failure means | deadlock | unsafe (deadlock possible) |

### 8.3 Explaining the deadlock: who is in the cycle?

Knowing *that* processes are stuck is not enough; the user needs to know *why*. After the detection algorithm, the tool does three things:

1. **Builds a wait-for graph among the stuck processes only**, using the resources left free at the end (`final_work`). Edge Pi → Pj on resource r when Pi still waits for r and Pj holds some r.
2. **Finds the strongly connected components (SCCs)** with **Tarjan's algorithm**, O(V + E). An SCC is a set of nodes where each one can reach every other. An SCC with ≥ 2 processes is a **deadlock group**: its members are **deadlocked**. Any other stuck process is **blocked** (it waits on the group but is not part of the cycle).
3. **Extracts one readable cycle per group** with a **three-colour DFS**: white = unvisited, grey = on the current path, black = finished. Reaching a grey node again means a back edge, i.e. a cycle such as `P1 → P2 → P1`.

**Why every stuck set contains a cycle.** Each stuck process waits for units that, after every finishable process has finished, can only be held by other stuck processes. (Validation rule 5 guarantees they are not all its own.) So every stuck process has an outgoing edge to another stuck process. A finite graph in which every node has an outgoing edge must contain a cycle.

### 8.4 Worked example (preset T7: deadlock plus a blocked process)

Resources: Printer = 1, Scanner = 1, Disk = 2.

| Process | Holds | Waits for |
| :---: | :--- | :--- |
| P1 | Printer | Scanner |
| P2 | Scanner | Printer |
| P3 | Disk | — |
| P4 | Disk | Printer |

Available = (0, 0, 0).

| Pass | Process | Request ≤ Work? | Work after |
| :---: | :---: | :---: | :---: |
| 1 | P1 | (0,1,0) ≤ (0,0,0)? no | |
| 1 | P2 | (1,0,0) ≤ (0,0,0)? no | |
| 1 | P3 | (0,0,0) ≤ (0,0,0)? **yes** | (0,0,1) |
| 1 | P4 | (1,0,0) ≤ (0,0,1)? no | |
| 2 | P1, P2, P4 | still no | no progress, so stop |

Stuck: {P1, P2, P4}. Stuck wait-for graph: P1 → P2 (Scanner), P2 → P1 (Printer), P4 → P1 (Printer). Tarjan finds the SCC {P1, P2}, so:

- **Deadlocked:** P1, P2. Circular wait: `P1 —Scanner→ P2 —Printer→ P1`
- **Blocked:** P4, which waits for the Printer held by P1 but is not on the cycle
- **Completes:** P3

The **Run Detection Scan** button animates exactly this trace. A scanner ring visits each process, the HUD shows the Work vector, finished processes turn green and release their units, and the stuck ones turn red.

### 8.5 When should detection run?

In a real OS, detection can run on every request that cannot be granted immediately (deadlock found as early as possible, high overhead), periodically (e.g. hourly), or when CPU utilization drops (a sign that processes are blocked). The tool runs it **after every change** and **after every event of a trace**, which is the "detect immediately" policy.

---

## 9. Potential-deadlock detection (the core of the tool)

Classic detection only reports a deadlock **after** it has happened. The project statement asks for **potential** deadlocks, meaning risks that have not happened yet. The tool combines three analyses ([potential.py](deadlock_tool/engine/potential.py)):

| Severity | Finding | Source |
| :--- | :--- | :--- |
| `deadlock` | **Circular wait** (and processes blocked by it) | Detection algorithm (section 8) |
| `high` | **Unsafe state**: no safe sequence exists | Banker's safety algorithm (section 7) |
| `medium` | **Lock-order inversion** | Resource-acquisition graph (below) |

Risk level = the most severe finding: `deadlock` > `high` > `medium` > `none`.

### 9.1 Lock-order (resource-acquisition) graph

This is the idea behind the Linux kernel's **lockdep** validator. Nodes are **resource types**, and:

> **Ra → Rb** (labelled with process P) if P currently **holds** Ra and still **needs** Rb (Need = Max − Allocation).

In other words, P acquires Ra **before** Rb.

A **cycle** `Ra → Rb → Ra` means some process takes Ra before Rb while another takes Rb before Ra: the processes acquire the same resources in **opposite orders**. Today the timing may be lucky, but another interleaving produces a circular wait. Self-loops are ignored, and a cycle created by one process alone is ignored, because a process cannot deadlock with itself.

**Claim: with single-instance resources, every deadlock shows a lock-order cycle.** In a circular wait P1 → P2 → … → Pk → P1, process Pi holds resource ri and waits for (so needs) ri+1, which is held by Pi+1. That gives edges r1 → r2 → … → rk → r1 in the lock-order graph, involving at least two processes. ∎ So the lock-order cycle is visible **before** the last request closes the circular wait; the tests check this on random systems. With multi-instance resources a lock-order cycle is a warning, not a proof (T4).

The tool's **LOCK ORDER** graph view draws this graph, with the inverted cycle in red.

### 9.2 Worked example (preset T16: a potential deadlock)

Printer = 1, Scanner = 1.

| Process | Holds | Max claim | Still needs |
| :---: | :--- | :--- | :--- |
| P1 | Printer | Printer, Scanner | Scanner |
| P2 | Scanner | Printer, Scanner | Printer |
| P3 | — | Printer | Printer |

Nobody is waiting, so detection says **no deadlock**. However:

- **Unsafe:** Available = (0,0), and every Need is larger, so there is no safe sequence.
- **Lock-order inversion:** P1 takes Printer before Scanner, and P2 takes Scanner before Printer, giving the cycle `Printer → Scanner → Printer`.

Verdict: 🟠 **POTENTIAL DEADLOCK**. The next request by P1 or P2 would close the circular wait. The suggested fix is **Enforce acquisition order Printer < Scanner** (cost 20). P2 releases the Scanner and later re-acquires it in order. The tool verifies that afterwards the risk level is `none`.

---

## 10. Deadlock recovery

Once a deadlock is detected, it must be broken. There are two families of methods.

### 10.1 Process termination

- **Abort all deadlocked processes:** always works, but loses the most work.
- **Abort one process at a time** until the cycle disappears: less work lost, but detection must run after each abort.

Factors when choosing whom to abort: priority, how long it has run and how long it still needs, resources used, resources still needed, how many processes must be terminated, and whether it is interactive or batch.

### 10.2 Resource preemption

Take resources away from some processes and give them to others, until the cycle breaks. Three issues:

1. **Selecting a victim**: minimise cost.
2. **Rollback**: the victim cannot continue normally. It is rolled back to a safe state (a checkpoint, or a total restart) and re-requests the resources.
3. **Starvation**: the same process must not be chosen as the victim every time (section 11).

### 10.3 Strategies generated by the tool

Every strategy is applied to a **copy** of the state and **re-checked by the detection algorithm** ([recovery.py](deadlock_tool/output/recovery.py)):

| Strategy | Effect on the simulated state | Victim cost |
| :--- | :--- | :---: |
| Terminate victim (repeat until clear) | Process removed; its units return to Available | 100 per process + 1 per unit lost |
| Terminate all deadlocked | Every process in the cycle removed | same |
| Preempt resource r from victim | `Allocation[v][r] → 0`, `Request[v][r] += units` | 20 + 10 per unit |
| Roll back victim | `Request[v] += Allocation[v]`, `Allocation[v] = 0` | 50 + 5 per unit |

Ranking: strategies that clear the deadlock come first, then those whose victims are not starvation-protected, then the lowest cost. The best one is marked **★ RECOMMENDED**, and **Apply to system** commits it and replays the detection scan.

**Example (T7):** Preempt Printer from P1 (30) ★, Preempt Scanner from P2 (30), Roll back P1 (55), Roll back P2 (55), Terminate P1 (101), Terminate P2 (101), Terminate all (202). All are verified to clear the deadlock.

---

## 11. Starvation

**Starvation** (indefinite blocking) is when a process waits indefinitely even though the system as a whole keeps making progress. The difference from deadlock: in a deadlock, *no* process of the set progresses; with starvation, others keep running while one is postponed forever.

### 11.1 Where starvation appears in deadlock handling

- **Recovery:** pure minimum-cost victim selection picks the same "cheapest" process every time the deadlock recurs, so it is rolled back forever.
- **Hold-and-wait prevention:** a process that needs several popular resources at once may never find them all free.
- **Preemption protocols:** the same process can be preempted again and again.
- (Outside deadlocks: priority scheduling, where low-priority processes may never run.)

### 11.2 Solution: aging

Include the **number of times a process has already been chosen as a victim** in its cost, so its cost grows with each selection. In this tool:

```
cost = base_cost + 60 × (times this victim was already chosen)
a process chosen 3 times becomes PROTECTED and is never recommended
```

### 11.3 Demonstration (preset T2, deadlock recurring for 6 rounds)

| Round | Without aging | With aging (cost) |
| :---: | :--- | :--- |
| 1 | Preempt R1 from P1 | Preempt R1 from P1 (30) |
| 2 | Preempt R1 from P1 | Preempt R2 from P2 (30) |
| 3 | Preempt R1 from P1 | Preempt R1 from P1 (90 = 30 + 60) |
| 4 | Preempt R1 from P1 | Preempt R2 from P2 (90) |
| 5 | Preempt R1 from P1 | Preempt R1 from P1 (150 = 30 + 120) |
| 6 | Preempt R1 from P1 | Preempt R2 from P2 (150) |
| **Result** | **P1 starves (6/6)** | Victim role rotates; at most 3 each |

The **Starvation** tab shows this simulation, plus the victim history for the current session (it grows each time you apply a recovery).

---

## 12. Resolution strategies engine

[resolution.py](deadlock_tool/handling/resolution.py) chooses the strategy family from the detected risk level:

| Risk level | Mode | Strategies offered |
| :--- | :--- | :--- |
| `deadlock` | **recover** | Recovery options from section 10, with aging |
| `high` (unsafe) | **mitigate** | **Suspend & roll back** an at-risk process so a safe sequence exists again (50 + 5 per unit), and **enforce acquisition order** if a lock-order cycle exists |
| `medium` (lock order) | **mitigate** | **Enforce acquisition order** R1 < R2 < … (15 + 5 per unit released) |
| `none` | none | Nothing to resolve |

*Enforce acquisition order:* every process that holds a resource ordered **after** the first resource it still needs releases it and re-acquires it in order. Afterwards every lock-order edge goes from a lower-ordered to a higher-ordered resource, so the graph is acyclic.

*Verification:* a mitigation counts as **resolved** only if the risk level after applying it is strictly lower and there is no deadlock. Each strategy is simulated, never applied blindly. The panel also gives standing advice: after a recovery, apply prevention or avoidance so the deadlock does not come back. For an unsafe state, grant further requests only through the Banker's check.

---

## 13. Process activity trace and automatic monitoring

Instead of typing matrices, the user can describe **what the processes do**, the kind of log a lock manager or an instrumented program produces ([trace.py](deadlock_tool/state/trace.py)):

```
resource Printer 1        # declare a resource type (undeclared ones get 1 instance)
P1 claims Scanner         # optional maximum claim, which enables early warnings
P1 acquire Printer        # granted if free, otherwise P1 WAITS
P1 release Printer        # give units back; waiting processes are served in order
```

Accepted synonyms are `request / lock / wait / wants`, `release / unlock / free`, and `claims / max`. An optional count can follow the resource (`P1 acquire Disk 2`).

**Semantics.**

- **acquire:** if `count ≤ Available`, the units go into Allocation; otherwise they go into Request (the process blocks).
- **release:** the units return to Available, and waiting processes whose request now fits are granted, in process order.
- A blocked process cannot issue another request.
- Invalid events (releasing what you do not hold, asking for more than exists) are reported with their line number.

**Automatic detection after every event.** After each event the full analysis runs (detection, Banker's safety, lock order). The timeline marks every event green, amber or red and reports:

- the **first event where a potential deadlock appears**, and
- the **event whose request closed the circular wait**.

For the built-in example: *"Potential deadlock first flagged at event #9 (P2 acquire Scanner). DEADLOCK at event #14 (P2 acquire Printer): this request closed the circular wait P1 → P2 → P1."* The tool warns five events before the deadlock. Clicking any event loads the system state at that moment.

---

## 14. Architecture and code map

### 14.1 Three modules

```
            M1 · System Input              M2 · Detection Engine            M3 · Resolution Strategies
 matrices ─┐                         ┌─ analyze()        actual deadlock  ┌─ suggest_resolutions()
 presets   ├─► validate() ─► State ─►├─ assess_risk()    potential        ├─ prevention_analysis()
 trace    ─┘   replay_trace()        ├─ safety_check()   Banker's         ├─ suggest_recoveries()
                                     └─ request_resources()               └─ simulate_starvation()
                                                    ▲                                │
                                                    └──── every strategy re-verified ┘
```

The modules communicate only through two data classes in [models.py](deadlock_tool/models.py): `SystemState` (input) and `DetectionResult` (output). The engine is pure Python with no UI imports, which keeps it easy to test.

### 14.2 Files

| File | Responsibility |
| :--- | :--- |
| `app.py` | Flask server and REST API (thin glue, no deadlock logic) |
| `deadlock_tool/models.py` | `SystemState` (matrices, derived Available/Need), `DetectionResult` |
| `state/validation.py` | Input rules (section 15) |
| `state/scenarios.py` | Preset loader and random-scenario generator |
| `state/trace.py` | Process-trace parser and event-by-event replay |
| `engine/detection.py` | Multi-instance detection algorithm (Work/Finish) |
| `engine/wait_for_graph.py` | Wait-for graph edges (current state, and among stuck processes) |
| `engine/cycles.py` | Tarjan SCC and three-colour DFS cycle extraction |
| `engine/analyzer.py` | `analyze()`: detection, groups, cycles, explanations, characterization |
| `engine/characterization.py` | The four necessary conditions |
| `engine/avoidance.py` | Banker's safety and resource-request algorithms |
| `engine/potential.py` | Lock-order graph and risk assessment (potential deadlocks) |
| `handling/resolution.py` | Suggested strategies (recover or mitigate) |
| `handling/prevention.py` | One prevention protocol per condition, simulated |
| `handling/starvation.py` | Recurring-deadlock simulation with and without aging |
| `output/recovery.py` | Termination, preemption and rollback, with aging-aware victim cost |
| `output/report.py` | Downloadable Markdown report |
| `static/js/*.js` | UI: input deck, graph views and scan animation, result panels |
| `scenarios/*.json` | 16 presets, each storing its expected result |
| `tests/test_engine.py` | 46 tests |

### 14.3 REST API

| Endpoint | Purpose |
| :--- | :--- |
| `POST /api/analyze` | Validate, detect (actual and potential), characterize, run the safety check |
| `POST /api/resolve` | Suggested resolution strategies (`recover` / `mitigate` / `none`) |
| `POST /api/trace` | Replay a process trace with detection after every event |
| `POST /api/prevent` | Prevention protocols, simulated |
| `POST /api/bankers/request` | Banker's resource-request algorithm |
| `POST /api/recover` | Recovery options only |
| `POST /api/starvation` | Starvation simulation |
| `POST /api/report` | Markdown report |
| `GET /api/scenarios`, `/api/scenarios/<id>`, `/api/random`, `/api/trace/example` | Inputs |

---

## 15. Input validation

The detection engine assumes a consistent state, so invalid input is rejected with a clear message instead of a wrong verdict:

1. Names are non-empty and unique; a process and a resource cannot share a name.
2. Matrix shapes are n × m.
3. All numbers are whole numbers ≥ 0 (limits: 20 processes, 12 resource types, 99 instances).
4. **No over-allocation:** `Σ Allocation[i][r] ≤ Total[r]`.
5. **No impossible request:** `Allocation[i][r] + Request[i][r] ≤ Total[r]`. A request that could never be granted, even if everyone else finished, is invalid input, **not** a deadlock (preset T12).
6. **Max claim** (if declared): `Max ≤ Total` and `Allocation + Request ≤ Max` (a process may not exceed its declared claim).

---

## 16. Testing and correctness checks

`python -m pytest -v` runs 46 tests. Besides fixed examples, several tests check **theorems** on hundreds of randomly generated valid systems:

| Property checked | Theory |
| :--- | :--- |
| Single-instance: WFG cycle ⇔ deadlock (300 systems) | Section 4.3 |
| Every deadlock has all four conditions (300) | Section 4.1: the conditions are necessary |
| Safe ⇒ not deadlocked (300) | Section 7.1 |
| Every prevention protocol leaves the system deadlock-free and the condition broken (200) | Section 6 |
| Resource ordering leaves no cycle (200) | Section 6.4 proof |
| Single-instance deadlock ⇒ lock-order cycle (300) | Section 9.1 claim |
| Risk level is "deadlock" ⇔ detection says deadlocked (300) | Section 9 |
| Lock-order fix removes every lock-order cycle (200) | Section 12 |
| Tarjan SCC matches NetworkX (100) | Section 8.3 |
| Every recovery and mitigation option is valid and correctly verified | Sections 10, 12 |
| Textbook Banker's example: safe sequence and request outcomes | Section 7.4 |
| Aging bounds victim selections to ≤ 3; without aging T2's P1 starves | Section 11 |
| Trace example warns before the deadlock and pinpoints event #14 | Section 13 |

Every preset JSON file stores its **expected** result, so the demo scenarios double as regression tests.

---

## 17. Preset scenarios

| # | Scenario | Teaches | Expected |
| :---: | :--- | :--- | :--- |
| T1 | Temporary wait | Waiting ≠ deadlock | No deadlock: P1 → P2 |
| T2 | Two-process deadlock | Classic circular wait; starvation demo | {P1, P2} deadlocked |
| T3 | Three-process cycle | Longer cycle | {P1, P2, P3} |
| T4 | Cycle but no deadlock | Multi-instance: cycle not sufficient | No deadlock; lock-order risk |
| T5 | Multi-instance deadlock | Detection with several instances | {P1, P2, P3} |
| T6 | Waiting chain | Chain without a cycle | No deadlock |
| T7 | Printer & scanner | Deadlocked vs blocked vs completes | {P1, P2}, blocked P4 |
| T8 | One process holds several resources | Victim choice matters | {P1, P2} |
| T9 | T3 after terminating P1 | Recovery result | No deadlock |
| T10 | Database locks | Two independent deadlock groups | {T1, T2} and {T3, T4} |
| T11 | Over-allocated resource | Validation | Error |
| T12 | Impossible request | Invalid ≠ deadlock | Error |
| T13 | Banker's textbook example | Safe sequence, request algorithm | Safe ⟨P1, P3, P4, P0, P2⟩ |
| T14 | 12 tape drives | Unsafe ≠ deadlocked | Unsafe, no deadlock |
| T15 | Ordered requests | Resource ordering prevents circular wait | No deadlock, no risk |
| T16 | Opposite lock order | **Potential deadlock** detected early | Unsafe + lock-order inversion |

---

## 18. Limitations

- It is a **simulation**. It does not read real OS lock tables. An adapter could convert real data (e.g. `/proc/locks`, database lock views) into the process-trace format.
- Potential-deadlock warnings are strongest when **Max claims** are declared. Without them, Need = Request, and "unsafe" coincides with "deadlocked".
- A lock-order cycle with multi-instance resources is a warning, not proof (T4).
- Victim cost is a simple fixed formula plus aging. Real systems would also weigh priority and remaining run time.
- Mutual exclusion is explained but not simulated (resources are not marked sharable).

---

## 19. Viva / review questions

**Q1. What are the four necessary conditions for deadlock?**
Mutual exclusion, hold and wait, no preemption, and circular wait. All four must hold simultaneously. They are necessary, not sufficient.

**Q2. Does a cycle in the resource-allocation graph always mean deadlock?**
Only when every resource has a single instance. With multiple instances, a cycle is necessary but not sufficient (preset T4).

**Q3. What is the difference between deadlock prevention and avoidance?**
Prevention restricts how requests can be made, so a condition can never hold (a static, design-time rule). Avoidance allows every condition but checks each request at run time using Max claims and grants it only if the state stays safe.

**Q4. What is a safe state? Is every unsafe state deadlocked?**
A state for which a safe sequence exists. No: unsafe means a deadlock is *possible*. Preset T14 is unsafe but not deadlocked.

**Q5. How do the detection algorithm and the Banker's safety algorithm differ?**
Same loop. Detection compares **Request** (current waits) with Work; safety compares **Need** (future maximum) with Work. A detection failure means deadlock; a safety failure means unsafe.

**Q6. What is the time complexity of the detection and safety algorithms?**
O(m · n²) for n processes and m resource types. Tarjan's SCC is O(V + E).

**Q7. How does the tool detect a *potential* deadlock?**
Three ways: an unsafe state (Banker's), a lock-order inversion (a cycle in the resource-acquisition graph, like Linux lockdep), and, for a process trace, flagging the first event where either appears, before the circular wait is closed.

**Q8. Why does resource ordering prevent circular wait?**
Along any wait cycle, resource numbers would have to increase strictly forever: F(R0) < F(R1) < … < F(R0), which is impossible.

**Q9. How does the tool distinguish a deadlocked process from a blocked one?**
Among the stuck processes, Tarjan's SCC finds the groups that are in a cycle (deadlocked). Stuck processes outside those groups are only waiting on them (blocked).

**Q10. What causes starvation in recovery, and how is it fixed?**
Cost-based victim selection can choose the same victim every time. Aging fixes it: each earlier selection adds +60 to the victim's cost, and after 3 selections the process is protected.

**Q11. Why is "request more than exists" not reported as a deadlock?**
Such a request could never be granted even if every other process finished, so it is an input error, not a circular wait (validation rule 5, preset T12).

**Q12. How are suggested strategies verified?**
Each strategy is applied to a copy of the state and the detector runs again. Recovery must clear the deadlock; mitigation must lower the risk level. Only then is it marked verified.

**Q13. Why does the tool start every process with Finish = false, unlike the textbook?**
So that a process holding nothing but waiting on the deadlock is reported as **blocked**. The deadlock yes/no answer is unchanged.

**Q14. What do most real operating systems do about deadlocks?**
For application-level resources, many ignore the problem (the "ostrich algorithm") and leave it to developers. Databases use detection and recovery (abort a transaction). Kernels use lock ordering and validators such as lockdep, i.e. prevention.

---

## 20. Glossary

| Term | Meaning |
| :--- | :--- |
| **Allocation** | Units of each resource a process currently holds |
| **Available** | Free units: Total − Σ Allocation |
| **Blocked process** | Stuck because it waits on a deadlocked process, but not part of the cycle itself |
| **Circular wait** | A closed chain of processes each waiting for the next |
| **Claim / Max** | The maximum units a process may ever request (avoidance) |
| **Lock-order inversion** | Two processes acquiring the same resources in opposite orders |
| **Need** | Max − Allocation: what a process may still request |
| **Preemption** | Forcibly taking a resource away from a process |
| **Request** | Units a process is waiting for right now |
| **Rollback** | Returning a process to an earlier checkpoint (or restarting it) |
| **Safe sequence** | An order in which all processes can finish even if they claim their maximum |
| **SCC** | Strongly connected component: nodes that can all reach each other |
| **Starvation** | Indefinite postponement of one process while others progress |
| **Victim** | The process chosen for termination or preemption during recovery |
| **WFG** | Wait-for graph: process → process dependencies |

---

## 21. References

1. A. Silberschatz, P. B. Galvin, G. Gagne. *Operating System Concepts*, chapter "Deadlocks" (system model, characterization, prevention, avoidance, detection, recovery).
2. E. G. Coffman, M. J. Elphick, A. Shoshani. "System Deadlocks." *ACM Computing Surveys* 3(2), 1971 (the four necessary conditions).
3. E. W. Dijkstra. "Cooperating Sequential Processes," 1965 (the Banker's algorithm).
4. R. E. Tarjan. "Depth-First Search and Linear Graph Algorithms." *SIAM Journal on Computing* 1(2), 1972 (strongly connected components).
5. Linux kernel documentation, "Runtime locking correctness validator" (lockdep), for lock-order analysis.
6. A. S. Tanenbaum, H. Bos. *Modern Operating Systems*, chapter "Deadlocks" (the ostrich algorithm, detection, recovery).
