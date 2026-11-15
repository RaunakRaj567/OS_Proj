"""MODULE 3 — Recovery (with starvation-aware victim selection) and reporting.
The visual side lives in static/js/graph.js and static/js/results.js."""

from deadlock_tool.output.recovery import suggest_recoveries
from deadlock_tool.output.report import build_report

__all__ = ["suggest_recoveries", "build_report"]
