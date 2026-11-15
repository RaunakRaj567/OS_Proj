"""MODULE 2 — Detection engine (pure Python, no UI imports).

analyze()        actual deadlock detection + characterization (circular wait, who is stuck)
safety_check()   Banker's safety algorithm (avoidance)
assess_risk()    POTENTIAL deadlock detection: unsafe state + lock-order inversion
"""

from deadlock_tool.engine.analyzer import analyze
from deadlock_tool.engine.avoidance import request_resources, safety_check
from deadlock_tool.engine.potential import assess_risk

__all__ = ["analyze", "safety_check", "request_resources", "assess_risk"]
