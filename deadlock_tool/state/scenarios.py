"""
scenarios.py — MODULE 1: preset scenario library + random scenario generator.

Each JSON file in /scenarios describes one system state plus the result we
EXPECT. The same files are used by the UI (demo presets) and by the unit
tests (regression fixtures), so the demo can never drift from the tests.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional

from deadlock_tool.models import SystemState

SCENARIO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scenarios"
)


def _load_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_scenarios() -> List[Dict[str, Any]]:
    """Returns [{id, name, description, category}] for every preset, sorted by file name."""
    items = []
    if not os.path.isdir(SCENARIO_DIR):
        return items
    for fname in sorted(os.listdir(SCENARIO_DIR)):
        if fname.endswith(".json"):
            data = _load_file(os.path.join(SCENARIO_DIR, fname))
            items.append({
                "id": data["id"],
                "name": data["name"],
                "description": data.get("description", ""),
                "category": data.get("category", ""),
            })
    return items


def load_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Returns the full scenario dict (state fields + metadata + expected), or None."""
    if not os.path.isdir(SCENARIO_DIR):
        return None
    for fname in os.listdir(SCENARIO_DIR):
        if fname.endswith(".json"):
            data = _load_file(os.path.join(SCENARIO_DIR, fname))
            if data.get("id") == scenario_id:
                return data
    return None


def random_scenario(
    n_processes: Optional[int] = None,
    n_resources: Optional[int] = None,
    seed: Optional[int] = None,
) -> SystemState:
    """
    Generates a random but always-VALID state.

    Allocation is drawn from the units still free; each request is limited to
    Total - Allocation of that process, so validation rule 5 always holds.
    Roughly half of the generated systems end up deadlocked.
    """
    rng = random.Random(seed)
    n = n_processes or rng.randint(3, 6)
    m = n_resources or rng.randint(2, 4)

    resources = ["R%d" % (r + 1) for r in range(m)]
    processes = ["P%d" % (i + 1) for i in range(n)]
    total = [rng.randint(1, 3) for _ in range(m)]

    allocation = [[0] * m for _ in range(n)]
    free = list(total)
    for r in range(m):
        holders = list(range(n))
        rng.shuffle(holders)
        for i in holders:
            if free[r] == 0:
                break
            if rng.random() < 0.55:
                take = rng.randint(1, free[r])
                allocation[i][r] = take
                free[r] -= take

    request = [[0] * m for _ in range(n)]
    for i in range(n):
        for r in range(m):
            room = total[r] - allocation[i][r]
            if room > 0 and rng.random() < 0.35:
                request[i][r] = rng.randint(1, room)

    # Max claim for Banker's avoidance: what it holds + waits for + maybe a little more.
    max_claim = [[min(total[r], allocation[i][r] + request[i][r] + (rng.randint(0, 1) if rng.random() < 0.4 else 0))
                  for r in range(m)] for i in range(n)]

    return SystemState(processes, resources, total, allocation, request, max_claim)
