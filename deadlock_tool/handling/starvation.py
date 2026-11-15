"""
starvation.py — MODULE 3: STARVATION in deadlock handling.

Starvation (indefinite blocking) is different from deadlock:
  * deadlock   — a SET of processes waits for each other; none of them progresses.
  * starvation — the system DOES progress, but one particular process is
                 postponed again and again and never gets to finish.

In deadlock recovery, starvation appears when victim selection is purely
cost-based: if the same deadlock keeps recurring, the same "cheapest" process is
preempted / rolled back / killed every time and never completes.

Fix (aging): include the number of times a process has already been chosen as
a victim in the cost factor, so its cost rises with each selection, and protect
it entirely after MAX_VICTIM_COUNT selections.

simulate_starvation() replays the current deadlock for several rounds (as if
the processes restarted and ran into the same situation again) and picks the
recommended victim each round — once WITHOUT aging and once WITH aging.
"""

from __future__ import annotations

from typing import Any, Dict, List

from deadlock_tool.models import SystemState
from deadlock_tool.output.recovery import AGING_PENALTY, MAX_VICTIM_COUNT, suggest_recoveries


def _run(state: SystemState, rounds: int, aging: bool) -> Dict[str, Any]:
    history: Dict[str, int] = {}
    log: List[Dict[str, Any]] = []
    for k in range(1, rounds + 1):
        opts = suggest_recoveries(state, history if aging else None)
        pick = next((o for o in opts if o["recommended"]), None) \
            or next((o for o in opts if o["resolved"]), None)
        if pick is None:
            break
        for v in pick["victims"]:
            history[v] = history.get(v, 0) + 1
        log.append({"round": k, "title": pick["title"], "victims": pick["victims"],
                    "cost": pick["cost"], "aging": pick["aging"]})
    counts = {p: history.get(p, 0) for p in state.processes}
    worst = max(counts.values()) if counts else 0
    starved = [p for p, c in counts.items() if log and c == len(log) and c >= 3]
    return {"aging": aging, "rounds": log, "counts": counts, "max_count": worst, "starved": starved}


def simulate_starvation(state: SystemState, rounds: int = 6) -> Dict[str, Any]:
    rounds = max(1, min(int(rounds), 12))
    without = _run(state, rounds, aging=False)
    with_aging = _run(state, rounds, aging=True)
    if not without["rounds"]:
        summary = ("The current state has no deadlock, so no victim is selected and recovery cannot starve anyone. "
                   "Load a deadlocked scenario (e.g. T2) to watch the same victim being chosen round after round.")
    elif without["starved"]:
        many = len(without["starved"]) > 1
        summary = ("Without aging, %s %s chosen as the victim in every one of the %d rounds and never "
                   "finish%s — STARVATION. With aging (+%d cost per previous selection, protected after %d), "
                   "the victim role rotates: worst case %d selection(s) for one process."
                   % (" and ".join(without["starved"]), "are" if many else "is", len(without["rounds"]),
                      "" if many else "es", AGING_PENALTY,
                      MAX_VICTIM_COUNT, with_aging["max_count"]))
    else:
        summary = ("Cost-based selection already spreads the victim role here; aging keeps any single process "
                   "from being chosen more than %d times." % MAX_VICTIM_COUNT)
    return {
        "without_aging": without,
        "with_aging": with_aging,
        "aging_penalty": AGING_PENALTY,
        "max_victim_count": MAX_VICTIM_COUNT,
        "summary": summary,
    }
