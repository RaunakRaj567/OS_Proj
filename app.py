"""
app.py — Flask server for the Automated Deadlock Detection Tool.

Core: analyse process dependencies and resource allocation, automatically
detect actual AND potential deadlocks (circular wait), and suggest verified
resolution strategies. Thin glue layer — no deadlock logic lives here.

    input (matrices or a process activity trace)
        -> detection: actual deadlock (circular wait) + potential deadlock (unsafe / lock order)
        -> resolution strategies (recovery or mitigation), each simulated & verified

Syllabus coverage
-----------------
Deadlock characterization   /api/analyze   -> result.conditions (four necessary conditions)
Deadlock prevention         /api/prevent
Deadlock avoidance          /api/analyze   -> safety (Banker's safety algorithm)
                            /api/bankers/request  (resource-request algorithm)
Deadlock detection          /api/analyze   -> result
Deadlock recovery           /api/recover
Starvation                  /api/recover (aging via victim history), /api/starvation

Run:   python app.py          ->  http://127.0.0.1:5050

API
---
GET  /api/scenarios            list preset scenarios                         (Module 1)
GET  /api/scenarios/<id>       load one preset                               (Module 1)
GET  /api/random               random valid scenario                         (Module 1)
POST /api/analyze   {state}    validate + detect (actual + potential) + characterize  (Module 1 + 2)
POST /api/resolve   {state, history}  suggested resolution strategies (recover / mitigate) (Module 3)
POST /api/trace     {text}     replay a process activity trace with detection after every event
GET  /api/trace/example        example trace
POST /api/prevent   {state}    prevention protocols, simulated & verified       (Module 3)
POST /api/bankers/request {state, process, request}  Banker's request algorithm (Module 2)
POST /api/recover   {state, history}  ranked, verified recovery simulations   (Module 3)
POST /api/starvation {state, rounds}  repeated recovery with / without aging  (Module 3)
POST /api/report    {state}    Markdown report download                       (Module 3)
"""

import os
import sys
import threading
import webbrowser

from flask import Flask, Response, jsonify, render_template, request

from deadlock_tool.models import SystemState
from deadlock_tool.state import (TRACE_EXAMPLE, list_scenarios, load_scenario, random_scenario,
                                 replay_trace, validate)
from deadlock_tool.engine import analyze, assess_risk, request_resources, safety_check
from deadlock_tool.handling import prevention_analysis, simulate_starvation, suggest_resolutions
from deadlock_tool.output import suggest_recoveries, build_report

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE, "templates"),
            static_folder=os.path.join(BASE, "static"))


def _state_from_request():
    payload = request.get_json(silent=True) or {}
    return SystemState.from_dict(payload.get("state", payload)), payload


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)     # the page uses an inline SVG icon


@app.route("/api/scenarios")
def api_scenarios():
    return jsonify(list_scenarios())


@app.route("/api/scenarios/<scenario_id>")
def api_scenario(scenario_id):
    data = load_scenario(scenario_id)
    if data is None:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify(data)


@app.route("/api/random")
def api_random():
    return jsonify(random_scenario().to_dict())


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    state, _ = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors})
    result, safety = analyze(state), safety_check(state)
    return jsonify({"valid": True, "errors": [], "result": result.to_dict(), "safety": safety,
                    "risk": assess_risk(state, result, safety)})


def _full_analysis(state):
    result = analyze(state)
    return result, assess_risk(state, result, safety_check(state))


@app.route("/api/trace", methods=["POST"])
def api_trace():
    payload = request.get_json(silent=True) or {}
    out = replay_trace(str(payload.get("text", "")), _full_analysis)
    if out.get("ok"):
        errors = validate(SystemState.from_dict(out["final_state"]))
        if errors:
            out["ok"], out["errors"] = False, errors
    return jsonify(out)


@app.route("/api/trace/example")
def api_trace_example():
    return jsonify({"text": TRACE_EXAMPLE})


@app.route("/api/resolve", methods=["POST"])
def api_resolve():
    state, payload = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors, "strategies": []})
    out = suggest_resolutions(state, _history(payload))
    out["valid"] = True
    return jsonify(out)


@app.route("/api/prevent", methods=["POST"])
def api_prevent():
    state, _ = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors, "protocols": []})
    return jsonify({"valid": True, "protocols": prevention_analysis(state)})


@app.route("/api/bankers/request", methods=["POST"])
def api_bankers_request():
    state, payload = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors})
    req = payload.get("request_vector") or []
    out = request_resources(state, str(payload.get("process", "")), list(req))
    out["valid"] = True
    return jsonify(out)


def _history(payload):
    h = payload.get("history") or {}
    return h if isinstance(h, dict) else {}


@app.route("/api/recover", methods=["POST"])
def api_recover():
    state, payload = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors, "options": []})
    return jsonify({"valid": True, "options": suggest_recoveries(state, _history(payload))})


@app.route("/api/starvation", methods=["POST"])
def api_starvation():
    state, payload = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors})
    try:
        rounds = int(payload.get("rounds", 6))
    except (TypeError, ValueError):
        rounds = 6
    out = simulate_starvation(state, rounds)
    out["valid"] = True
    return jsonify(out)


@app.route("/api/report", methods=["POST"])
def api_report():
    state, payload = _state_from_request()
    errors = validate(state)
    if errors:
        return jsonify({"valid": False, "errors": errors}), 400
    result, safety = analyze(state), safety_check(state)
    md = build_report(state, result, suggest_recoveries(state, _history(payload)),
                      payload.get("title", ""), safety=safety,
                      prevention=prevention_analysis(state),
                      risk=assess_risk(state, result, safety),
                      resolution=suggest_resolutions(state, _history(payload)))
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=deadlock_report.md"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:%d" % port)).start()
    print("Deadlock Sentinel running at http://127.0.0.1:%d" % port)
    app.run(host="127.0.0.1", port=port, debug=False)
