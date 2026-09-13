"""Portable AgentEmbodiment command client. Python 3.10+, standard library only.

Extracted from the working project client: atomic queue transport, session/reply
correlation, bounded values, durable receipts and first-person PNG verification.
The starter exposes only observe, look, move, stop and say.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import struct
import sys
import time
import uuid


CLIENT_DIR = Path(__file__).resolve().parent
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
class ClientError(RuntimeError):
    pass


class ReplyTimeout(ClientError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def iso_time(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value):
    if not isinstance(value, str):
        raise ClientError("Expected UTC timestamp string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClientError("Invalid UTC timestamp") from exc
    if result.tzinfo is None:
        raise ClientError("Timestamp is missing a timezone")
    return result.astimezone(timezone.utc)


def read_json(path):
    # Windows may expose a newly renamed engine reply while its write handle is
    # still closing, or briefly hide runtime.json during native replacement.
    # Retry only this read; never cache a session or resubmit a command.
    for attempt in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            break
        except (PermissionError, FileNotFoundError) as exc:
            if attempt == 4 or (isinstance(exc, FileNotFoundError) and path.name != "runtime.json"):
                raise ClientError(f"Cannot read JSON at {path}: {exc}") from exc
            time.sleep(.025 * (2 ** attempt))
        except (OSError, ValueError) as exc:
            raise ClientError(f"Cannot read JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClientError(f"Expected JSON object at {path}")
    return value


def atomic_json(path, data):
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, allow_nan=False)
            handle.write("\n")
        # A concurrent Windows reader can briefly deny replacement. Retry only
        # publishing these exact bytes, never create/replay a queue command.
        for attempt in range(6):
            try:
                temp.replace(path)
                break
            except PermissionError as exc:
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                    raise
                time.sleep(.025 * (2 ** attempt))
    finally:
        temp.unlink(missing_ok=True)


def bounded_number(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClientError(f"{name} must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise ClientError(f"{name} must be in [{low}, {high}]")
    return value


def speech_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ClientError("text must be a nonempty string")
    if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in value):
        raise ClientError("text may contain newline and tab, but no other ASCII controls or DEL")
    try:
        units = len(value.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise ClientError("text contains invalid Unicode surrogates") from exc
    if not 1 <= units <= 500:
        raise ClientError("text must contain 1 to 500 UTF-16 code units")
    return value


def validate_runtime(root):
    root = Path(root).resolve()
    runtime = read_json(root / "runtime.json")
    if runtime.get("schema_version") != 1 or runtime.get("running") is not True:
        raise ClientError("Runtime is not running with schema version 1")
    session = runtime.get("session_id")
    try:
        uuid.UUID(session)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ClientError("Runtime session_id is not a UUID") from exc
    if Path(runtime.get("queue_root", "")).resolve() != root:
        raise ClientError("Runtime queue_root does not match --root")
    for folder in ("inbox", "outbox", "captures", "chat-events"):
        if not (root / folder).is_dir():
            raise ClientError(f"Runtime folder is missing: {root / folder}")
    updated = parse_time(runtime.get("updated_at_utc"))
    age = (utc_now() - updated).total_seconds()
    if age > 10 or age < -2:
        raise ClientError("Runtime heartbeat is stale; no command submitted")
    if type(runtime.get("stop_revision")) is not int or runtime["stop_revision"] < 0:
        raise ClientError("Runtime has no valid stop revision")
    return root, runtime



ACTION_FIELDS = {
    "observe": set(), "stop": set(),
    "move": {"forward", "right", "seconds", "speed_cm_s"},
    "look": {"yaw_delta_deg", "pitch_delta_deg"},
    "say": {"text", "reply_to_event_id"},
}


def validate_params(action, params=None):
    params = dict(params or {})
    allowed = ACTION_FIELDS.get(action)
    if allowed is None or set(params) - (allowed | {"expected_stop_revision"}):
        raise ClientError("Unknown action or action parameter")
    if "expected_stop_revision" in params:
        revision = params["expected_stop_revision"]
        if type(revision) is not int or not 0 <= revision <= 9007199254740991:
            raise ClientError("Invalid stop revision")
    if action == "move":
        for name in ("forward", "right"):
            params[name] = bounded_number(name, params.get(name, 0), -1, 1)
        params["seconds"] = bounded_number("seconds", params.get("seconds", .5), .05, 2)
        params["speed_cm_s"] = bounded_number("speed_cm_s", params.get("speed_cm_s", 120), 1, 300)
    elif action == "look":
        params["yaw_delta_deg"] = bounded_number("yaw_delta_deg", params.get("yaw_delta_deg", 0), -90, 90)
        params["pitch_delta_deg"] = bounded_number("pitch_delta_deg", params.get("pitch_delta_deg", 0), -60, 60)
    elif action == "say":
        params["text"] = speech_text(params.get("text"))
        if "reply_to_event_id" in params:
            event_id = params["reply_to_event_id"]
            if type(event_id) is not int or not 1 <= event_id <= 9007199254740991:
                raise ClientError("reply_to_event_id must be a positive safe integer")
    return params


def submit(root, action, params=None, *, capture=True, receipt_dir=None,
           expected_session=None, deadline_seconds=30):
    root, runtime = validate_runtime(root)
    if expected_session is not None and runtime["session_id"] != expected_session:
        raise ClientError("Runtime session changed; no command submitted")
    params = validate_params(action, params)
    if action in ("move", "look", "say"):
        expected = params.get("expected_stop_revision", runtime["stop_revision"])
        if expected != runtime["stop_revision"]:
            raise ClientError("Stop revision changed; stale command was not submitted")
        params["expected_stop_revision"] = expected
    bounded_number("deadline_seconds", deadline_seconds, .1, 30)
    now = utc_now()
    command_id = action + "_" + uuid.uuid4().hex
    request = {"schema_version": 1, "session_id": runtime["session_id"],
               "id": command_id, "action": action, "capture": bool(capture),
               "deadline_utc": iso_time(now + timedelta(seconds=deadline_seconds)), **params}
    receipt_dir = Path(receipt_dir or root / "client-receipts")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / (command_id + ".json")
    receipt = {"schema_version": 1, "root": str(root), "submitted_at_utc": iso_time(now),
               "request": request, "receipt_path": str(receipt_path.resolve())}
    atomic_json(receipt_path, receipt)
    atomic_json(root / "inbox" / (command_id + ".json"), request)
    return receipt

def validate_reply(receipt, reply):
    request = receipt["request"]
    for field in ("schema_version", "session_id", "id", "action"):
        if reply.get(field) != request[field]:
            raise ClientError(f"Reply {field} does not match submitted request")
    if not isinstance(reply.get("ok"), bool):
        raise ClientError("Reply has no Boolean ok result")
    if reply.get("status") not in ("completed", "blocked", "interrupted", "rejected"):
        raise ClientError("Unknown runtime reply status")
    # Rejections may not contain fresh state. Blocked/interrupted actions still do.
    if reply["status"] == "rejected":
        return {"fresh_capture_verified": False, "runtime_rejected": True}
    state = reply.get("state")
    if not isinstance(state, dict):
        raise ClientError("Non-rejected reply has no state")
    if type(state.get("stop_revision")) is not int or state["stop_revision"] < 0:
        raise ClientError("Reply has no valid stop revision")
    if (reply["ok"] and reply["status"] == "completed" and "expected_stop_revision" in request
            and state["stop_revision"] != request["expected_stop_revision"]):
        raise ClientError("Completed reply belongs to a different stop revision")
    observation_id = state.get("observation_id")
    if type(observation_id) is not int or observation_id < 0:
        raise ClientError("Missing or invalid observation_id")
    captured_at = parse_time(state.get("captured_at_utc"))
    submitted_at = parse_time(receipt["submitted_at_utc"])
    if captured_at < submitted_at - timedelta(seconds=1):
        raise ClientError("Reply observation predates this command")
    if captured_at > utc_now() + timedelta(seconds=2):
        raise ClientError("Reply observation timestamp is in the future")
    capture = reply.get("capture")
    if not isinstance(capture, dict):
        if not request["capture"] or reply["status"] in ("blocked", "interrupted") or reply.get("capture_error"):
            return {"fresh_capture_verified": False, "capture_requested": request["capture"],
                    "capture_absent": True, "observation_id": observation_id,
                    "capture_absence_reason": reply.get("capture_error") or
                    ("not_requested" if not request["capture"] else reply["status"] + "_without_capture")}
        raise ClientError("Requested capture is missing: " + str(reply.get("capture_error", "no reason supplied")))
    if capture.get("observation_id") != observation_id or capture.get("view") != "first_person":
        raise ClientError("Capture does not match the first-person observation")
    image_path = Path(capture.get("path", ""))
    if not image_path.is_absolute():
        raise ClientError("Capture path must be absolute")
    image_path = image_path.resolve()
    captures_root = (Path(receipt["root"]) / "captures").resolve()
    if image_path != captures_root / (request["id"] + ".png") or not image_path.is_relative_to(captures_root):
        raise ClientError("Capture path is outside this runtime's captures folder")
    try:
        with image_path.open("rb") as handle:
            header = handle.read(24)
        image_mtime = datetime.fromtimestamp(image_path.stat().st_mtime, timezone.utc)
    except OSError as exc:
        raise ClientError(f"Capture file is unavailable: {exc}") from exc
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ClientError("Capture file lacks a PNG IHDR header")
    dimensions = struct.unpack(">II", header[16:24])
    if dimensions != (capture.get("width"), capture.get("height")) or dimensions != (640, 360):
        raise ClientError("Capture dimensions do not match the 640x360 runtime contract")
    if image_mtime < submitted_at - timedelta(seconds=1):
        raise ClientError("Capture file predates this command")
    return {"fresh_capture_verified": True, "image_path": str(image_path), "observation_id": observation_id,
            "validation_scope": "session, request, timestamp, local path and PNG header; visual content requires viewing"}


def wait_for_reply(receipt, *, timeout=10, poll=.1):
    bounded_number("timeout", timeout, .05, 60)
    root = Path(receipt["root"])
    request = receipt["request"]
    response_path = root / "outbox" / (request["id"] + ".json")
    end = time.monotonic() + timeout
    while True:
        runtime = read_json(root / "runtime.json")
        if runtime.get("session_id") != request["session_id"]:
            raise ClientError("Runtime session changed; command will not be retried")
        if response_path.is_file():
            reply = read_json(response_path)
            verification = validate_reply(receipt, reply)
            return {"reply": reply, "client": {"receipt_path": receipt["receipt_path"], **verification}}
        if runtime.get("running") is not True:
            raise ClientError("Runtime stopped before replying; command will not be retried")
        if time.monotonic() >= end:
            raise ReplyTimeout("Timed out waiting for " + request["id"] + "; command is not cancelled and was not retried. Use wait for its reply or stop the current session.")
        time.sleep(min(poll, max(0, end - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Project/Saved/AgentEmbodiment")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--session", help="Require this session UUID; recommended for agent tools")
    parser.add_argument("--receipts", type=Path, help="Default: runtime root/client-receipts")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ACTION_FIELDS:
        command = commands.add_parser(action)
        command.add_argument("--no-capture", action="store_true")
        if action == "move":
            command.add_argument("--forward", type=float, default=0)
            command.add_argument("--right", type=float, default=0)
            command.add_argument("--seconds", type=float, default=.5)
            command.add_argument("--speed-cm-s", type=float, default=120)
        elif action == "look":
            command.add_argument("--yaw-delta-deg", type=float, default=0)
            command.add_argument("--pitch-delta-deg", type=float, default=0)
        elif action == "say":
            command.add_argument("--text", required=True)
            command.add_argument("--reply-to-event-id", type=int)
        if action in ("move", "look", "say"):
            command.add_argument("--expected-stop-revision", type=int)
    commands.add_parser("wait").add_argument("id")
    args = parser.parse_args()
    receipt = None
    try:
        bounded_number("timeout", args.timeout, .05, 60)
        if args.action == "wait":
            if not ID_PATTERN.fullmatch(args.id):
                raise ClientError("Invalid command id")
            receipt = read_json((args.receipts or args.root / "client-receipts") / (args.id + ".json"))
            if args.root.resolve() != Path(receipt["root"]).resolve():
                raise ClientError("--root differs from submitted command")
            if args.session and receipt["request"]["session_id"] != args.session:
                raise ClientError("Receipt differs from --session")
        else:
            names = ACTION_FIELDS[args.action] | {"expected_stop_revision"}
            params = {name: getattr(args, name) for name in names if getattr(args, name, None) is not None}
            receipt = submit(args.root, args.action, params, capture=not args.no_capture,
                             receipt_dir=args.receipts, expected_session=args.session)
            if args.no_wait:
                print(json.dumps({"submitted": True, "id": receipt["request"]["id"],
                                  "receipt_path": receipt["receipt_path"]}, indent=2))
                return 0
        result = wait_for_reply(receipt, timeout=args.timeout)
        print(json.dumps(result, indent=2))
        return 0 if result["reply"]["ok"] and result["reply"]["status"] == "completed" else 1
    except (ClientError, OSError) as exc:
        error = {"client_error": str(exc), "error_type": type(exc).__name__, "automatic_retry": False}
        if receipt:
            error.update(id=receipt["request"]["id"], receipt_path=receipt["receipt_path"])
        print(json.dumps(error, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


