"""
resolution.py — MODULE 3: suggested RESOLUTION STRATEGIES (the tool's answer).

    risk level        mode        strategies
    ----------        ----        ----------
    deadlock          recover     terminate / preempt / roll back a victim
                                  (output/recovery.py, starvation-aware)
    high  (unsafe)    mitigate    roll back or suspend an at-risk process so
                                  the state becomes SAFE again; from now on grant
                                  requests only through the Banker's check
    medium (lock      mitigate    enforce one global acquisition order: holders
            order)                release resources acquired out of order and
                                  re-acquire them in order
    none              none        nothing to do

Every strategy is applied to a COPY of the state and verified: for recovery,
the detection algorithm must report no deadlock; for mitigation, the risk
assessment must report a lower level. Strategies are ranked by
(clears the problem, not starvation-protected, cost).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from deadlock_tool.models import SystemState
from deadlock_tool.engine import analyze, safety_check
from deadlock_tool.engine.potential import assess_risk, lock_order_cycles
from deadlock_tool.output.recovery import AGING_PENALTY, MAX_VICTIM_COUNT, suggest_recoveries

_RANK = {"none": 0, "medium": 1, "high": 2, "deadlock": 3}


def _risk(state: SystemState) -> Dict[str, Any]:
    return assess_risk(state, analyze(state), safety_check(state))


def _mitigation(strategy: str, title: str, description: str, actions: List[str], cost: int,
                after: SystemState, before_level: str, victims: List[str], history: Dict[str, int],
                warning: Optional[str] = None) -> Dict[str, Any]:
    res = analyze(after)
    risk = assess_risk(after, res, safety_check(after))
    aging = AGING_PENALTY * sum(history.get(v, 0) for v in victims)
    return {
        "strategy": strategy, "title": title, "description": description, "actions": actions,
        "victims": victims, "base_cost": cost, "aging": aging, "cost": cost + aging,
        "protected": [v for v in victims if history.get(v, 0) >= MAX_VICTIM_COUNT],
        "resolved": _RANK[risk["level"]] < _RANK[before_level] and not res.is_deadlocked,
        "risk_after": risk["level"],
        "remaining_deadlocked": res.deadlocked + res.blocked,
        "warning": warning,
        "after_state": after.to_dict(), "after_result": res.to_dict(),
        "recommended": False,
    }


def _held(state: SystemState, i: int, rs: List[int]) -> str:
    return ", ".join("%s×%d" % (state.resources[r], state.allocation[i][r]) for r in rs if state.allocation[i][r]) or "nothing"


def _mitigations(state: SystemState, risk: Dict[str, Any], history: Dict[str, int]) -> List[Dict[str, Any]]:
    level, out = risk["level"], []
    m = state.m

    # ---- A. enforce a global acquisition order (fixes lock-order inversion) ----
    if lock_order_cycles(state):
        need = state.need
        after, actions, victims, units = state.clone(), [], [], 0
        for i, p in enumerate(state.processes):
            wanted = [r for r in range(m) if need[i][r] > 0]
            if not wanted:
                continue
            lowest = min(wanted)
            bad = [r for r in range(m) if state.allocation[i][r] > 0 and r > lowest]
            if bad:
                victims.append(p)
                units += sum(state.allocation[i][r] for r in bad)
                actions.append("%s releases %s, then re-acquires in order %s"
                               % (p, _held(state, i, bad), " < ".join(state.resources)))
                for r in bad:
                    after.request[i][r] += after.allocation[i][r]
                    after.allocation[i][r] = 0
        if victims:
            out.append(_mitigation(
                "lock_order", "Enforce acquisition order " + " < ".join(state.resources),
                "Fix the root cause: every process must acquire resources in one global order. "
                "Processes holding a resource 'too early' release it and re-acquire it in order, "
                "so no lock-order cycle (and no circular wait) can form.",
                actions, 15 + 5 * units, after, level, victims, history,
                warning="Requires changing how the processes acquire resources (a code/design fix)."))

    # ---- B. roll back / suspend an at-risk process (fixes unsafe state) ----
    if level == "high":
        for p in risk["at_risk"]:
            i = state.processes.index(p)
            units = sum(state.allocation[i])
            if not units:
                continue
            after = state.clone()
            after.request[i] = [after.request[i][r] + after.allocation[i][r] for r in range(m)]
            after.allocation[i] = [0] * m
            out.append(_mitigation(
                "rollback", "Suspend & roll back %s" % p,
                "Take back what %s holds (%s) and let it restart later, so the remaining processes "
                "have a safe sequence again." % (p, _held(state, i, list(range(m)))),
                ["Roll back %s" % p], 50 + 5 * units, after, level, [p], history,
                warning="Work done by %s since its checkpoint is lost; repeated rollback may starve it." % p))
    return out


def suggest_resolutions(state: SystemState, history: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    history = {str(k): int(v) for k, v in (history or {}).items() if isinstance(v, int) and v > 0}
    risk = _risk(state)
    level = risk["level"]
    if level == "deadlock":
        return {"mode": "recover", "level": level, "strategies": suggest_recoveries(state, history),
                "advice": "Break the deadlock now (recovery). Afterwards, apply a prevention or avoidance "
                          "strategy so it cannot happen again."}
    if level == "none":
        return {"mode": "none", "level": level, "strategies": [],
                "advice": "Nothing to resolve: no deadlock and no deadlock risk."}

    strategies = _mitigations(state, risk, history)
    strategies.sort(key=lambda o: (not o["resolved"], bool(o["protected"]), o["cost"], o["title"]))
    for k, o in enumerate(strategies):
        o["id"] = "mit%d" % (k + 1)
    for o in strategies:
        if o["resolved"] and not o["protected"]:
            o["recommended"] = True
            break
    advice = ("The system is not deadlocked yet. Act before it is: restore a safe state and grant every further "
              "request only through the Banker's check (Avoidance tab)." if level == "high" else
              "The system is safe right now, but processes take resources in conflicting orders. Enforcing one "
              "acquisition order removes the circular-wait condition permanently (Prevention tab).")
    return {"mode": "mitigate", "level": level, "strategies": strategies, "advice": advice}
