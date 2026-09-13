"""Local chat-to-agent bridge using an explicit JSON subprocess adapter.

This portable adapter is new starter code. Session/event correlation, durable
delivery receipts and no-automatic-replay behavior derive from the original
desktop-specific bridge. No desktop-private pipe or model SDK is required.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import player


class BridgeError(RuntimeError):
    pass


class StaleTurn(BridgeError):
    pass


IDENTITY = ("schema_version", "request_id", "agent_id", "session_id", "human_event_id", "stop_revision")
MODEL_ACTIONS = {"observe", "look", "move", "stop"}


def load_config(filename):
    filename = Path(filename).resolve()
    config = player.read_json(filename)
    if config.get("schema_version") != 1:
        raise BridgeError("Config schema_version must be 1")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", config.get("agent_id", "")):
        raise BridgeError("Config agent_id must be a stable lowercase identifier")
    command = config.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(s, str) or not s for s in command):
        raise BridgeError("Config command must be a nonempty argument array; no shell command strings")
    config["command"] = [sys.executable if item == "{python}" else item for item in command]
    config["cwd"] = str((filename.parent / config.get("cwd", ".")).resolve())
    if not Path(config["cwd"]).is_dir():
        raise BridgeError("Config cwd does not exist")
    config["timeout_seconds"] = player.bounded_number("timeout_seconds", config.get("timeout_seconds", 120), 1, 600)
    config["command_timeout_seconds"] = player.bounded_number("command_timeout_seconds", config.get("command_timeout_seconds", 10), .05, 60)
    return config


def read_events(root, session):
    events = {}
    for filename in (Path(root) / "chat-events").glob(session + "-*.json"):
        event = player.read_json(filename)
        event_id = event.get("event_id")
        if (event.get("schema_version") != 1 or event.get("session_id") != session or
                type(event_id) is not int or not 1 <= event_id <= 9007199254740991 or
                event.get("speaker") not in ("human", "agent")):
            raise BridgeError("Invalid current-session chat event")
        player.speech_text(event.get("text"))
        occurred = player.parse_time(event.get("occurred_at_utc"))
        if (occurred - player.utc_now()).total_seconds() > 2:
            raise BridgeError("Chat event timestamp is in the future")
        expected = session + "-" + str(event_id).zfill(20) + ".json"
        if filename.name != expected or event_id in events:
            raise BridgeError("Chat event filename or identity is inconsistent")
        events[event_id] = event
    return [events[key] for key in sorted(events)]


def validate_response(request, response):
    if not isinstance(response, dict):
        raise BridgeError("Adapter response must be a JSON object")
    for name in IDENTITY:
        if type(response.get(name)) is not type(request[name]) or response.get(name) != request[name]:
            raise BridgeError("Adapter response identity mismatch: " + name)
    if set(response) != set(IDENTITY) | {"reply", "actions"}:
        raise BridgeError("Adapter response must include exactly the identity fields, reply and actions")
    text = response.get("reply")
    if text is not None:
        player.speech_text(text)
    actions = response.get("actions")
    if not isinstance(actions, list) or len(actions) > 4:
        raise BridgeError("Adapter must return an actions array with at most four actions")
    if request["phase"] == "results" and actions:
        raise BridgeError("Results phase cannot request more actions")
    for item in actions:
        if not isinstance(item, dict) or set(item) != {"action", "params"}:
            raise BridgeError("Each action must contain only action and params")
        if item["action"] not in MODEL_ACTIONS or not isinstance(item["params"], dict):
            raise BridgeError("Adapter requested an unsupported action")
        if "expected_stop_revision" in item["params"]:
            raise BridgeError("Bridge owns the stop revision guard")
        player.validate_params(item["action"], item["params"])
    return response


def invoke_adapter(config, request):
    # shell=False and an argv array preserve paths with spaces and prevent shell
    # interpretation. The configured adapter is trusted local executable code.
    try:
        result = subprocess.run(config["command"], cwd=config["cwd"],
                                input=json.dumps(request, allow_nan=False),
                                capture_output=True, text=True, encoding="utf-8",
                                timeout=config["timeout_seconds"], shell=False)
    except subprocess.TimeoutExpired as exc:
        raise BridgeError("Adapter timed out; this event will not be retried automatically") from exc
    except OSError as exc:
        raise BridgeError("Could not start adapter: " + str(exc)) from exc
    if result.returncode:
        raise BridgeError("Adapter failed (exit " + str(result.returncode) + "): " + result.stderr[-1500:])
    if len(result.stdout) > 65536:
        raise BridgeError("Adapter output exceeds 64 KiB")
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise BridgeError("Adapter stdout must contain one JSON object and no logs") from exc
    return validate_response(request, response)


class ConversationBridge:
    def __init__(self, root, config, *, include_existing=False, resume_after_error=False):
        self.root, runtime = player.validate_runtime(root)
        self.config = config
        self.session = runtime["session_id"]
        self.folder = self.root / "bridge"
        self.folder.mkdir(exist_ok=True)
        self.state_path = self.folder / "state.json"
        self.lock_path = self.folder / "bridge.lock"
        self.token = uuid.uuid4().hex
        try:
            self.lock_path.mkdir()
        except FileExistsError as exc:
            raise BridgeError("Bridge lock exists. Check bridge/bridge.lock/owner.json; after confirming its process is stopped, remove only that lock directory") from exc
        try:
            player.atomic_json(self.lock_path / "owner.json", {"pid": os.getpid(), "token": self.token,
                "session_id": self.session, "agent_id": config["agent_id"]})
            events = read_events(self.root, self.session)
            previous = player.read_json(self.state_path) if self.state_path.is_file() else None
            if previous and previous.get("session_id") == self.session:
                if previous.get("agent_id") != config["agent_id"]:
                    raise BridgeError("Bridge state belongs to another agent_id; use a new Unreal session")
                self.state = previous
                if self.state.get("pending"):
                    if not resume_after_error:
                        raise BridgeError("Previous delivery is unresolved. Inspect bridge/state.json and command receipts; --resume-after-error skips its replay and accepts newer messages")
                    pending = self.state["pending"]
                    pending["status"] = "uncertain_not_retried"
                    self.state["deliveries"].append(pending)
                    self.state["pending"] = None
            else:
                baseline = 0 if include_existing else max((e["event_id"] for e in events), default=0)
                self.state = {"schema_version": 1, "agent_id": config["agent_id"], "session_id": self.session,
                              "cursor": baseline, "pending": None, "deliveries": [],
                              "startup_policy": "include_existing" if include_existing else "new_messages_only"}
            self.save()
            self.status("connected", "Ready for new human messages")
        except BaseException:
            self.close()
            raise

    def save(self):
        player.atomic_json(self.state_path, self.state)

    def status(self, status, message):
        player.atomic_json(self.root / "chat-bridge-status.json", {
            "schema_version": 1, "session_id": self.session, "agent_id": self.config["agent_id"],
            "status": status, "updated_at_utc": player.iso_time(player.utc_now()), "message": message,
            "last_human_event_id": self.state["cursor"]})

    def close(self):
        owner = self.lock_path / "owner.json"
        if owner.exists() and player.read_json(owner).get("token") == self.token:
            owner.unlink()
            self.lock_path.rmdir()

    def guard(self, revision=None, human_event_id=None):
        _, runtime = player.validate_runtime(self.root)
        if runtime["session_id"] != self.session:
            raise StaleTurn("Unreal session changed; no cross-session delivery")
        if revision is not None and runtime["stop_revision"] != revision:
            raise StaleTurn("Stop revision changed while this turn was pending")
        if human_event_id is not None:
            events = read_events(self.root, self.session)
            if any(e["speaker"] == "human" and e["event_id"] > human_event_id for e in events):
                raise StaleTurn("A newer human message superseded this pending response")
        return runtime

    def native(self, action, params, revision):
        if action in ("move", "look", "say"):
            params = {**params, "expected_stop_revision": revision}
        receipt = player.submit(self.root, action, params, capture=action not in ("say", "stop"),
                                expected_session=self.session)
        # Journal the exact command before waiting, so uncertain delivery is
        # inspectable and never turned into an automatic duplicate submission.
        self.state["pending"].setdefault("command_receipts", []).append(receipt["receipt_path"])
        self.save()
        return player.wait_for_reply(receipt, timeout=self.config["command_timeout_seconds"])

    def best_effort_stop(self):
        try:
            self.guard()
            receipt = player.submit(self.root, "stop", capture=False, expected_session=self.session)
            self.state["pending"]["recovery_stop_receipt"] = receipt["receipt_path"]
            self.save()
            player.wait_for_reply(receipt, timeout=min(2, self.config["command_timeout_seconds"]))
        except (OSError, player.ClientError, BridgeError):
            pass

    def request(self, event, observation, phase, results, revision):
        return {"schema_version": 1, "request_id": uuid.uuid4().hex,
                "agent_id": self.config["agent_id"], "session_id": self.session,
                "human_event_id": event["event_id"], "stop_revision": revision,
                "phase": phase, "human_event": event,
                "history": read_events(self.root, self.session)[-32:],
                "observation": observation, "results": results,
                "capabilities": {"actions": sorted(MODEL_ACTIONS), "max_actions": 4,
                    "description": "Bounded local Unreal actions. Centimeters/degrees/seconds. Movement is swept capsule motion; no grasping or navigation planner. Captures are local PNG paths; the adapter must explicitly load them to see the image."}}

    def poll_once(self):
        runtime = self.guard()
        events = read_events(self.root, self.session)
        candidates = [e for e in events if e["speaker"] == "human" and e["event_id"] > self.state["cursor"]]
        if not candidates:
            self.status("connected", "Ready for new human messages")
            return False
        # The newest message steers a pending turn; history includes preceding
        # messages, so an adapter can interpret split thoughts together.
        event = candidates[-1]
        self.state["cursor"] = event["event_id"]
        self.state["pending"] = {"event_id": event["event_id"], "status": "dispatching",
                                 "started_at_utc": player.iso_time(player.utc_now()),
                                 "included_human_event_ids": [e["event_id"] for e in candidates]}
        self.save()
        self.status("busy", "Processing human message")
        revision = runtime["stop_revision"]
        try:
            observation = self.native("observe", {}, revision)
            if not observation["reply"]["ok"]:
                raise BridgeError("Initial world observation was rejected")
            self.guard(revision, event["event_id"])
            request = self.request(event, observation, "plan", [], revision)
            response = invoke_adapter(self.config, request)
            self.guard(revision, event["event_id"])
            results = []
            for item in response["actions"]:
                self.guard(revision, event["event_id"])
                result = self.native(item["action"], item["params"], revision)
                results.append(result)
                observation = result
                if not result["reply"]["ok"] or result["reply"]["status"] != "completed":
                    break
                if item["action"] == "stop":
                    revision = result["reply"]["state"]["stop_revision"]
            if results:
                self.guard(revision, event["event_id"])
                request = self.request(event, observation, "results", results, revision)
                response = invoke_adapter(self.config, request)
            self.guard(revision, event["event_id"])
            if response["reply"] is not None:
                result = self.native("say", {"text": response["reply"], "reply_to_event_id": event["event_id"]}, revision)
                if not result["reply"]["ok"] or result["reply"]["status"] != "completed":
                    raise BridgeError("Native speech was not confirmed")
            self.state["pending"]["status"] = "replied" if response["reply"] is not None else "silent"
        except StaleTurn as exc:
            self.best_effort_stop()
            self.state["pending"].update(status="superseded", error=str(exc))
        except BaseException as exc:
            self.best_effort_stop()
            self.state["pending"].update(status="error_or_uncertain", error=str(exc))
            self.save()
            self.status("error", str(exc))
            raise
        self.state["deliveries"].append(self.state["pending"])
        self.state["pending"] = None
        self.save()
        self.status("connected", "Message handled")
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="Process currently new messages once, then exit")
    parser.add_argument("--include-existing", action="store_true", help="On first start only, include existing current-session human messages")
    parser.add_argument("--resume-after-error", action="store_true", help="Preserve unresolved receipts, skip replay and accept newer messages")
    args = parser.parse_args()
    bridge = None
    try:
        bridge = ConversationBridge(args.root, load_config(args.config), include_existing=args.include_existing,
                                    resume_after_error=args.resume_after_error)
        print(json.dumps({"status": "connected", "session_id": bridge.session,
                          "agent_id": bridge.config["agent_id"], "startup_policy": bridge.state["startup_policy"]}), flush=True)
        while True:
            handled = bridge.poll_once()
            if handled:
                print(json.dumps({"status": "handled", "human_event_id": bridge.state["cursor"]}), flush=True)
            if args.once:
                break
            time.sleep(.25)
        return 0
    except KeyboardInterrupt:
        return 130
    except (BridgeError, player.ClientError, OSError, ValueError) as exc:
        print(json.dumps({"bridge_error": str(exc), "automatic_retry": False}), file=sys.stderr)
        return 2
    finally:
        if bridge:
            if not bridge.state.get("pending"):
                bridge.status("offline", "Bridge stopped")
            bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
