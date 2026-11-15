"""
report.py — MODULE 3: builds a downloadable Markdown report organised by the
deadlock syllabus: characterization, prevention, avoidance, detection,
recovery and starvation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from deadlock_tool.models import DetectionResult, SystemState
from deadlock_tool.output.recovery import AGING_PENALTY, MAX_VICTIM_COUNT


def _matrix_table(state: SystemState, matrix: List[List[int]]) -> List[str]:
    lines = ["| Process | " + " | ".join(state.resources) + " |",
             "| :--- | " + " | ".join(":---:" for _ in state.resources) + " |"]
    for i, p in enumerate(state.processes):
        lines.append("| %s | %s |" % (p, " | ".join(str(v) for v in matrix[i])))
    return lines


def build_report(state: SystemState, result: DetectionResult,
                 recoveries: List[Dict[str, Any]], title: str = "",
                 safety: Optional[Dict[str, Any]] = None,
                 prevention: Optional[List[Dict[str, Any]]] = None,
                 risk: Optional[Dict[str, Any]] = None,
                 resolution: Optional[Dict[str, Any]] = None) -> str:
    L: List[str] = []
    L.append("# Deadlock Detection Report")
    if title:
        L.append("**Scenario:** %s  " % title)
    L.append("**Generated:** %s  " % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    L.append("**Detection verdict:** %s  " % ("\U0001F534 DEADLOCK DETECTED" if result.is_deadlocked else "\U0001F7E2 NO DEADLOCK"))
    if safety is not None:
        L.append("**Avoidance verdict:** %s  " % ("SAFE state" if safety["safe"] else "UNSAFE state"))
    if risk is not None:
        L.append("**Risk level:** %s" % risk["level"].upper())
    L.append("")

    # ---- summary: findings + suggested resolution ------------------------
    if risk is not None:
        L.append("## Summary: Detection Findings")
        L.append(risk["headline"])
        L.append("")
        for f in risk["findings"]:
            L.append("- **[%s] %s** — %s" % (f["severity"].upper(), f["title"], f["detail"]))
        L.append("")
    if resolution is not None and resolution["strategies"]:
        L.append("## Summary: Suggested Resolution Strategies")
        L.append(resolution["advice"])
        L.append("")
        L.append("| Rank | Strategy | Verified | Cost |")
        L.append("| :---: | :--- | :---: | :---: |")
        for k, o in enumerate(resolution["strategies"], 1):
            L.append("| %d | %s%s | %s | %d |" % (k, o["title"], " ⭐" if o["recommended"] else "",
                                                 "yes" if o["resolved"] else "no", o["cost"]))
        L.append("")

    # ---- 1. state ----------------------------------------------------------
    L.append("## 1. System State")
    L.append("| Resource | Total | Available |")
    L.append("| :--- | :---: | :---: |")
    for r, name in enumerate(state.resources):
        L.append("| %s | %d | %d |" % (name, state.total[r], result.available[r]))
    L.append("")
    for label, matrix in (("Allocation** (units held)", state.allocation),
                          ("Request** (units waited for now)", state.request),
                          ("Max** (declared maximum claim)", state.claim),
                          ("Need** = Max − Allocation", state.need)):
        L.append("**" + label)
        L.extend(_matrix_table(state, matrix))
        L.append("")

    # ---- 2. characterization -----------------------------------------------
    L.append("## 2. Deadlock Characterization")
    L.append("| Necessary condition | Holds? | Why |")
    L.append("| :--- | :---: | :--- |")
    for c in result.conditions:
        L.append("| %s | %s | %s |" % (c["name"], "yes" if c["holds"] else "no", c["detail"]))
    L.append("")

    # ---- 3. prevention -----------------------------------------------------
    if prevention:
        L.append("## 3. Deadlock Prevention")
        L.append("| Condition denied | Protocol | Violators | Outcome |")
        L.append("| :--- | :--- | :--- | :--- |")
        for p in prevention:
            L.append("| %s | %s | %s | %s |" % (p["condition"], p["technique"],
                                               ", ".join(p["violators"]) or "—", p["verdict"]))
        L.append("")

    # ---- 4. avoidance ------------------------------------------------------
    if safety is not None:
        L.append("## 4. Deadlock Avoidance (Banker's Safety Algorithm)")
        L.append(safety["message"])
        L.append("")
        L.append("| Pass | Process | Need | Work | Outcome |")
        L.append("| :---: | :--- | :--- | :--- | :--- |")
        for ev in safety["trace"]:
            if ev["type"] == "check":
                L.append("| %d | %s | %s | %s | %s |" % (ev["pass"], ev["process"], ev["need"], ev["work"],
                                                       "Need ≤ Work → can finish" if ev["fits"] else "must wait"))
            else:
                L.append("| %d | %s | | %s | releases %s |" % (ev["pass"], ev["process"], ev["work"], ev["released"]))
        L.append("")

    # ---- 5. detection ------------------------------------------------------
    L.append("## 5. Deadlock Detection")
    L.append("| Process | Status |")
    L.append("| :--- | :--- |")
    for p in state.processes:
        L.append("| %s | %s |" % (p, result.status[p]))
    L.append("")
    if result.cycles:
        L.append("**Circular wait:** " + "; ".join(" → ".join(c) for c in result.cycles))
        L.append("")
    if result.completion_order:
        L.append("**Completion order:** " + " → ".join(result.completion_order))
        L.append("")
    L.append("### Explanation")
    for e in result.explanations:
        L.append("- " + e)
    L.append("")
    L.append("### Detection Algorithm Trace")
    L.append("Work starts at Available = %s." % result.available)
    L.append("")
    L.append("| Pass | Process | Request | Work | Outcome |")
    L.append("| :---: | :--- | :--- | :--- | :--- |")
    for ev in result.trace:
        if ev["type"] == "check":
            L.append("| %d | %s | %s | %s | %s |" % (
                ev["pass"], ev["process"], ev["request"], ev["work"],
                "fits → finishes" if ev["fits"] else "must wait"))
        else:
            L.append("| %d | %s | | %s | releases %s |" % (ev["pass"], ev["process"], ev["work"], ev["released"]))
    L.append("")

    # ---- 6. recovery -------------------------------------------------------
    if result.is_deadlocked:
        L.append("## 6. Deadlock Recovery (simulated & verified)")
        L.append("| Rank | Strategy | Clears deadlock? | Cost | Notes |")
        L.append("| :---: | :--- | :---: | :---: | :--- |")
        for k, o in enumerate(recoveries, 1):
            L.append("| %d | %s%s | %s | %d | %s |" % (
                k, o["title"], " ⭐" if o["recommended"] else "",
                "yes" if o["resolved"] else "no", o["cost"], o["warning"] or ""))
        L.append("")
        L.append("_Victim cost: terminate = 100/process + lost units; rollback = 50 + 5/unit; "
                 "preempt = 20 + 10/unit._")
        L.append("")

    # ---- 7. starvation -----------------------------------------------------
    L.append("## 7. Starvation")
    L.append("Starvation is indefinite postponement of one process while the rest of the system progresses. "
             "Pure minimum-cost victim selection can pick the same victim every time a deadlock recurs. "
             "This tool applies **aging**: each previous selection adds %d to a process's victim cost, and "
             "after %d selections the process is protected." % (AGING_PENALTY, MAX_VICTIM_COUNT))
    L.append("")

    L.append("---")
    L.append("_Methods: four necessary conditions (characterization); hold-and-wait / no-preemption / "
             "resource-ordering protocols (prevention); Banker's safety & resource-request algorithms "
             "(avoidance); Work/Finish detection algorithm O(m·n²) with wait-for graph and Tarjan SCC "
             "(detection); termination, preemption & rollback (recovery); aging (starvation)._")
    return "\n".join(L)
