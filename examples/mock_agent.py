"""Deterministic wiring diagnostic, not a language model or reasoning demo."""
import json
import sys


def respond(request):
    response = {key: request[key] for key in ("schema_version", "request_id", "agent_id", "session_id", "human_event_id", "stop_revision")}
    response.update(reply=None, actions=[])
    if request["phase"] == "results":
        complete = all(r["reply"]["ok"] and r["reply"]["status"] == "completed" for r in request["results"])
        response["reply"] = "Diagnostic: native actions completed." if complete else "Diagnostic: an action was blocked or interrupted. Inspect its receipt."
        return response
    message = request["human_event"]["text"].strip().lower()
    if message == "step":
        response["actions"] = [{"action": "move", "params": {"forward": 1, "seconds": .5, "speed_cm_s": 100}}]
    elif message == "look left":
        response["actions"] = [{"action": "look", "params": {"yaw_delta_deg": -30}}]
    elif message == "stop":
        response["actions"] = [{"action": "stop", "params": {}}]
    else:
        response["reply"] = "Diagnostic connected. Type step, look left, or stop to test a bounded native action. This is a scripted adapter."
    return response


if __name__ == "__main__":
    print(json.dumps(respond(json.load(sys.stdin)), ensure_ascii=False))
