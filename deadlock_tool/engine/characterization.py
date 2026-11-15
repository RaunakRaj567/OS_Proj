"""
characterization.py — MODULE 2: DEADLOCK CHARACTERIZATION.

A deadlock can arise only if FOUR conditions hold simultaneously
(Coffman et al., 1971):

1. Mutual exclusion   at least one resource is non-sharable: only one process
                      can use an instance at a time.
2. Hold and wait      a process holds at least one resource while waiting to
                      acquire more resources held by others.
3. No preemption      a resource is released only voluntarily by the process
                      holding it, after it has finished its task.
4. Circular wait      a set {P0, P1, ..., Pn} exists such that P0 waits for P1,
                      P1 waits for P2, ..., Pn waits for P0.

These are NECESSARY conditions, not sufficient ones:
  * single-instance resources : a cycle in the RAG  <=>  deadlock
  * multi-instance resources  : a cycle is necessary but NOT sufficient

In this simulator every resource instance is non-sharable (a printer, a lock,
a tape drive) and the system never takes resources away on its own, so
conditions 1 and 3 hold whenever something is allocated. Conditions 2 and 4
depend on the current Allocation/Request matrices.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from deadlock_tool.models import SystemState


def _cond(key: str, name: str, holds: bool, detail: str, prevent: str) -> Dict[str, Any]:
    return {"key": key, "name": name, "holds": holds, "detail": detail, "prevent": prevent}


def evaluate_conditions(state: SystemState, wfg_cycle: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Evaluates the four necessary conditions on the current state."""
    n, m = state.n, state.m
    held = [r for r in range(m) if any(state.allocation[i][r] > 0 for i in range(n))]
    holders = [state.processes[i] for i in range(n) if any(state.allocation[i])]
    hold_wait = [state.processes[i] for i in range(n)
                 if any(state.allocation[i]) and any(state.request[i])]

    me = _cond(
        "mutual_exclusion", "Mutual exclusion", bool(held),
        ("Non-sharable resources are in use: %s. Each instance can be used by only one process at a time."
         % ", ".join(state.resources[r] for r in held)) if held
        else "No resource instance is currently allocated, so nothing is being used exclusively.",
        "Usually cannot be denied: printers, locks and tape drives are intrinsically non-sharable "
        "(only sharable resources such as read-only files avoid it).",
    )
    hw = _cond(
        "hold_and_wait", "Hold and wait", bool(hold_wait),
        ("%s hold%s resources while waiting for more."
         % (", ".join(hold_wait), "s" if len(hold_wait) == 1 else "")) if hold_wait
        else "No process is holding a resource while waiting for another.",
        "Require a process to request ALL its resources at once, or to release everything before requesting.",
    )
    np_ = _cond(
        "no_preemption", "No preemption", bool(holders),
        ("Resources are released only voluntarily by their holders (%s); the system never takes them back."
         % ", ".join(holders)) if holders
        else "Nothing is held, so there is nothing that could be preempted.",
        "If a holding process's request cannot be granted immediately, it must release (be preempted of) what it holds.",
    )
    cw = _cond(
        "circular_wait", "Circular wait", wfg_cycle is not None,
        ("The wait-for graph contains the cycle %s." % " → ".join(wfg_cycle)) if wfg_cycle
        else "The wait-for graph has no cycle.",
        "Impose a total ordering on resource types and request them only in increasing order.",
    )
    return [me, hw, np_, cw]


def single_instance(state: SystemState) -> bool:
    return all(t <= 1 for t in state.total)


def characterization_summary(state: SystemState, conditions: List[Dict[str, Any]], is_deadlocked: bool) -> str:
    all_hold = all(c["holds"] for c in conditions)
    missing = [c["name"] for c in conditions if not c["holds"]]
    if not all_hold:
        return ("No deadlock can exist at this moment: %s %s not hold right now, and all four conditions are "
                "necessary. (Whether one can still FORM later is what the potential-deadlock findings tell you.)"
                % (" and ".join(missing), "does" if len(missing) == 1 else "do"))
    if is_deadlocked:
        return "All four necessary conditions hold, and the system IS deadlocked."
    if single_instance(state):
        return "All four conditions hold."  # cannot happen: single-instance cycle => deadlock
    return ("All four necessary conditions hold, yet there is NO deadlock: with multi-instance resources "
            "the conditions (and a cycle) are necessary but not sufficient.")
