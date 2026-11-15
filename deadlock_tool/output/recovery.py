"""
recovery.py — MODULE 3: simulated deadlock recovery with verification.

Rule: every strategy is applied to a COPY of the state and then re-checked by
the detection engine (Module 2). Only verified outcomes are shown. Nothing
here touches real operating-system processes.

Strategies
----------
terminate      Abort one victim (its resources return to Available). If the
               deadlock remains, keep aborting the deadlocked process that
               holds the most units until it clears.
terminate_all  Abort every deadlocked process (baseline).
preempt        Take all units of one resource from a victim and give them to the
               waiters. The victim keeps running but must re-request them:
                   Allocation[v][r] -> 0,  Request[v][r] += units
rollback       Restart a victim from scratch: it releases everything it holds
               and re-requests all of it:  Request[v] += Allocation[v]; Allocation[v] = 0

Victim selection (minimum cost):
    terminate      100 per aborted process + 1 per unit of lost work
    rollback        50 + 5 per unit released
    preempt         20 + 10 per unit taken

STARVATION guard (aging): if the same process is always the cheapest victim it
may never finish. With a victim `history` ({process: times already chosen}),
    cost += AGING_PENALTY × (times each victim was already chosen)
and a process chosen MAX_VICTIM_COUNT times becomes PROTECTED (never recommended).
Options that clear the deadlock come first, cheapest first; the cheapest
non-protected one is marked "recommended".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from deadlock_tool.models import SystemState
from deadlock_tool.engine import analyze

AGING_PENALTY = 60          # extra cost per time a process was already chosen as victim
MAX_VICTIM_COUNT = 3        # after this many selections a process is protected


def _option(strategy: str, title: str, description: str, actions: List[str], cost: int,
            after: SystemState, victims: List[str], history: Dict[str, int],
            warning: Optional[str] = None) -> Dict[str, Any]:
    result = analyze(after)
    aging = AGING_PENALTY * sum(history.get(v, 0) for v in victims)
    protected = [v for v in victims if history.get(v, 0) >= MAX_VICTIM_COUNT]
    return {
        "strategy": strategy,
        "title": title,
        "description": description,
        "actions": actions,
        "victims": victims,
        "base_cost": cost,
        "aging": aging,
        "cost": cost + aging,
        "protected": protected,
        "resolved": not result.is_deadlocked,
        "remaining_deadlocked": result.deadlocked + result.blocked,
        "warning": warning,
        "after_state": after.to_dict(),
        "after_result": result.to_dict(),
        "recommended": False,
    }


def _units_held(state: SystemState, name: str) -> int:
    return sum(state.allocation[state.processes.index(name)])


def suggest_recoveries(state: SystemState, history: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """
    Returns ranked, verified recovery options. Empty list if there is no deadlock.
    `history` maps process -> how many times it was already chosen as a victim (aging).
    """
    history = {str(k): int(v) for k, v in (history or {}).items() if isinstance(v, int) and v > 0}
    before = analyze(state)
    if not before.is_deadlocked:
        return []

    options: List[Dict[str, Any]] = []
    res = state.resources

    # ---- 1. terminate one victim (repeat until clear) ---------------------
    for victim in before.deadlocked:
        current = state.without_process(victim)
        victims = [victim]
        lost = _units_held(state, victim)
        res_after = analyze(current)
        while res_after.is_deadlocked and res_after.deadlocked:
            # next victim: not protected, least often chosen before, then the one holding most units
            nxt = min(res_after.deadlocked, key=lambda p: (history.get(p, 0) >= MAX_VICTIM_COUNT,
                                                           history.get(p, 0), -_units_held(current, p)))
            lost += _units_held(current, nxt)
            current = current.without_process(nxt)
            victims.append(nxt)
            res_after = analyze(current)
        held = state.allocation[state.processes.index(victim)]
        released = ", ".join("%s×%d" % (res[r], held[r]) for r in range(state.m) if held[r]) or "nothing"
        title = "Terminate " + " then ".join(victims)
        options.append(_option(
            "terminate", title,
            "Abort %s (simulated). %s releases %s back to the pool."
            % (" and ".join(victims), victim, released),
            ["Terminate %s" % v for v in victims],
            100 * len(victims) + lost,
            current, victims, history,
        ))

    # ---- 2. terminate every deadlocked process ---------------------------
    if len(before.deadlocked) > 1:
        current = state
        lost = 0
        for p in before.deadlocked:
            lost += _units_held(current, p)
            current = current.without_process(p)
        options.append(_option(
            "terminate_all", "Terminate all deadlocked processes",
            "Abort every process in the circular wait (%s). Always works, but loses the most work."
            % ", ".join(before.deadlocked),
            ["Terminate %s" % p for p in before.deadlocked],
            100 * len(before.deadlocked) + lost,
            current, list(before.deadlocked), history,
        ))

    # ---- 3. preempt one resource from a victim ---------------------------
    seen = set()
    for edge in before.deadlock_edges:
        victim, r_name = edge["to"], edge["resource"]
        if (victim, r_name) in seen:
            continue
        seen.add((victim, r_name))
        i, r = state.processes.index(victim), state.resources.index(r_name)
        units = state.allocation[i][r]
        after = state.clone()
        after.allocation[i][r] = 0
        after.request[i][r] += units
        options.append(_option(
            "preempt", "Preempt %s from %s" % (r_name, victim),
            "Forcibly take %s×%d from %s and hand it to the waiting process(es). "
            "%s keeps running but must request it again." % (r_name, units, victim, victim),
            ["Preempt %s×%d from %s" % (r_name, units, victim)],
            20 + 10 * units,
            after, [victim], history,
            warning="Starvation risk if %s is preempted again and again (see the Starvation tab)." % victim,
        ))

    # ---- 4. rollback (restart) a victim ----------------------------------
    for victim in before.deadlocked:
        i = state.processes.index(victim)
        units = sum(state.allocation[i])
        after = state.clone()
        after.request[i] = [after.request[i][r] + after.allocation[i][r] for r in range(state.m)]
        after.allocation[i] = [0] * state.m
        options.append(_option(
            "rollback", "Roll back %s" % victim,
            "Restart %s from its beginning (simulated checkpoint): it releases everything it "
            "holds (%d unit%s) and requests it all again later." % (victim, units, "" if units == 1 else "s"),
            ["Roll back %s" % victim],
            50 + 5 * units,
            after, [victim], history,
            warning="Work done by %s since its checkpoint is lost." % victim,
        ))

    options.sort(key=lambda o: (not o["resolved"], bool(o["protected"]), o["cost"], o["title"]))
    for k, opt in enumerate(options):
        opt["id"] = "opt%d" % (k + 1)
    for opt in options:
        if opt["resolved"] and not opt["protected"]:
            opt["recommended"] = True
            break
    return options
