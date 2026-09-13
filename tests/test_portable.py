"""Protocol tests use a fake native queue, not an Unreal rendering claim."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from client import player
from bridge.bridge import BridgeError, ConversationBridge, invoke_adapter, load_config, validate_response


class FakeRuntime:
    """A protocol peer only: it does not simulate or validate Unreal physics."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        for name in ("inbox", "processed", "outbox", "captures", "chat-events"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.session = str(uuid.uuid4())
        self.revision = 0
        self.running = True
        self.position = 0
        self.observation = 0
        self.event_id = 0
        self.requests = []
        self.errors = []
        self.done = threading.Event()
        self.publish()
        self.worker = None

    def publish(self):
        player.atomic_json(self.root / "runtime.json", {"schema_version": 1, "session_id": self.session,
            "queue_root": str(self.root), "running": self.running, "stop_revision": self.revision,
            "updated_at_utc": player.iso_time(player.utc_now())})

    def event(self, text, speaker="human", reply_to=None):
        self.event_id += 1
        event = {"schema_version": 1, "session_id": self.session, "event_id": self.event_id,
                 "speaker": speaker, "text": text, "occurred_at_utc": player.iso_time(player.utc_now())}
        if reply_to is not None:
            event["reply_to_event_id"] = reply_to
        player.atomic_json(self.root / "chat-events" / (self.session + "-" + str(self.event_id).zfill(20) + ".json"), event)
        return event

    def serve(self):
        while not self.done.wait(.01):
            try:
                self.publish()
                for filename in self.root.joinpath("inbox").glob("*.json"):
                    request = player.read_json(filename)
                    filename.replace(self.root / "processed" / filename.name)
                    self.requests.append(request)
                    ok = request["session_id"] == self.session and player.parse_time(request["deadline_utc"]) >= player.utc_now()
                    if request["action"] in ("move", "look", "say"):
                        ok = ok and request.get("expected_stop_revision") == self.revision
                    if ok and request["action"] == "stop":
                        self.revision += 1
                        self.publish()
                    if ok and request["action"] == "move":
                        self.position += request["forward"] * request["seconds"] * request["speed_cm_s"]
                    if ok and request["action"] == "say":
                        self.event(request["text"], "agent", request.get("reply_to_event_id"))
                    self.observation += 1
                    reply = {key: request[key] for key in ("schema_version", "session_id", "id", "action")}
                    reply.update(ok=ok, status="completed" if ok else "rejected",
                        state={"observation_id": self.observation, "captured_at_utc": player.iso_time(player.utc_now()),
                               "stop_revision": self.revision, "position_cm": {"x": self.position, "y": 0, "z": 0}},
                        capture_error="Diagnostic peer does not render images")
                    player.atomic_json(self.root / "outbox" / filename.name, reply)
            except BaseException as exc:
                self.errors.append(exc)
                self.done.set()

    def start(self):
        self.worker = threading.Thread(target=self.serve, daemon=True)
        self.worker.start()
        return self

    def close(self):
        self.done.set()
        if self.worker:
            self.worker.join(3)
        if self.errors:
            raise self.errors[0]


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Embodiment portable test ")
        self.root = Path(self.temp.name) / "Runtime with spaces"
        self.runtime = FakeRuntime(self.root)
        self.bridges = []
        self.config = load_config(ROOT / "examples" / "mock-agent.json")
        self.config["command_timeout_seconds"] = .5

    def tearDown(self):
        for bridge in reversed(self.bridges):
            bridge.close()
        self.runtime.close()
        self.temp.cleanup()

    def bridge(self, **kwargs):
        bridge = ConversationBridge(self.root, self.config, **kwargs)
        self.bridges.append(bridge)
        return bridge

    def test_roundtrip_real_subprocess_spaces_and_no_duplicate(self):
        self.runtime.start()
        bridge = self.bridge()
        event = self.runtime.event("step")
        self.assertTrue(bridge.poll_once())
        self.assertEqual(self.runtime.position, 50)
        spoken = [r for r in self.runtime.requests if r["action"] == "say"]
        self.assertEqual(len(spoken), 1)
        self.assertEqual(spoken[0]["reply_to_event_id"], event["event_id"])
        self.assertIn("completed", spoken[0]["text"])
        count = len(self.runtime.requests)
        self.assertFalse(bridge.poll_once())
        bridge.close()
        again = self.bridge()
        self.assertFalse(again.poll_once())
        self.assertEqual(len(self.runtime.requests), count)

    def test_adapter_script_and_config_in_relocated_path_with_spaces(self):
        self.runtime.start()
        adapter_dir = Path(self.temp.name) / "Adapter folder with spaces"
        adapter_dir.mkdir()
        shutil.copyfile(ROOT / "examples" / "mock_agent.py", adapter_dir / "my adapter.py")
        player.atomic_json(adapter_dir / "my config.json", {"schema_version": 1, "agent_id": "relocated-agent",
            "command": ["{python}", "my adapter.py"], "cwd": "."})
        self.config = load_config(adapter_dir / "my config.json")
        bridge = self.bridge()
        self.runtime.event("hello")
        self.assertTrue(bridge.poll_once())
        self.assertEqual(bridge.state["deliveries"][-1]["status"], "replied")

    def test_default_start_does_not_replay_existing_messages(self):
        self.runtime.event("step")
        bridge = self.bridge()
        self.assertFalse(bridge.poll_once())
        self.assertEqual(self.runtime.requests, [])

    def test_include_existing_is_explicit(self):
        self.runtime.start()
        self.runtime.event("look left")
        bridge = self.bridge(include_existing=True)
        self.assertTrue(bridge.poll_once())
        self.assertTrue(any(r["action"] == "look" for r in self.runtime.requests))

    def test_client_session_and_stop_revision_reject_before_submission(self):
        with self.assertRaises(player.ClientError):
            player.submit(self.root, "move", {"forward": 1}, expected_session=str(uuid.uuid4()))
        with self.assertRaises(player.ClientError):
            player.submit(self.root, "move", {"expected_stop_revision": 1})
        self.assertEqual(list((self.root / "inbox").glob("*.json")), [])

    def test_client_rejects_nan_control_text_and_unknown_actions(self):
        for action, params in (("move", {"forward": float("nan")}), ("say", {"text": "a\x00b"}),
                               ("say", {"text": "a" * 501}), ("look", {"yaw_delta_deg": 91}),
                               ("pose", {}), ("move", {"seconds": True})):
            with self.assertRaises(player.ClientError):
                player.submit(self.root, action, params)

    def test_client_timeout_preserves_one_submission_and_receipt(self):
        receipt = player.submit(self.root, "move", {"forward": 1})
        with self.assertRaises(player.ReplyTimeout):
            player.wait_for_reply(receipt, timeout=.05, poll=.01)
        self.assertTrue(Path(receipt["receipt_path"]).is_file())
        self.assertEqual(len(list((self.root / "inbox").glob("*.json"))), 1)

    def test_reply_identity_mismatch_is_rejected(self):
        receipt = player.submit(self.root, "observe", capture=False)
        reply = {key: receipt["request"][key] for key in ("schema_version", "session_id", "id", "action")}
        reply.update(ok=False, status="rejected", id="someone_else")
        with self.assertRaises(player.ClientError):
            player.validate_reply(receipt, reply)

    def test_capture_provenance_rejects_outside_path_and_accepts_matching_header(self):
        receipt = player.submit(self.root, "observe")
        image_path = self.root / "captures" / (receipt["request"]["id"] + ".png")
        # Header-only fixture proves provenance validation, never image decoding.
        image_path.write_bytes(player.PNG_SIGNATURE + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 360))
        reply = {key: receipt["request"][key] for key in ("schema_version", "session_id", "id", "action")}
        reply.update(ok=True, status="completed",
            state={"observation_id": 1, "captured_at_utc": player.iso_time(player.utc_now()), "stop_revision": 0},
            capture={"view": "first_person", "observation_id": 1, "path": str(image_path), "width": 640, "height": 360})
        self.assertTrue(player.validate_reply(receipt, reply)["fresh_capture_verified"])
        reply["capture"]["path"] = str(self.root / "outside.png")
        with self.assertRaises(player.ClientError):
            player.validate_reply(receipt, reply)

    def test_client_session_rollover_cannot_complete_old_request(self):
        receipt = player.submit(self.root, "observe", capture=False)
        self.runtime.session = str(uuid.uuid4())
        self.runtime.publish()
        with self.assertRaisesRegex(player.ClientError, "session changed"):
            player.wait_for_reply(receipt, timeout=.05)

    def test_stale_runtime_is_not_a_live_connection(self):
        runtime = player.read_json(self.root / "runtime.json")
        runtime["updated_at_utc"] = "2000-01-01T00:00:00Z"
        player.atomic_json(self.root / "runtime.json", runtime)
        with self.assertRaisesRegex(player.ClientError, "stale"):
            player.submit(self.root, "observe")

    def test_stop_during_provider_discards_late_actions(self):
        self.runtime.start()
        bridge = self.bridge()
        self.runtime.event("step")
        original = invoke_adapter
        def stopped(config, request):
            response = original(config, request)
            self.runtime.revision += 1
            self.runtime.publish()
            return response
        with patch("bridge.bridge.invoke_adapter", stopped):
            bridge.poll_once()
        self.assertEqual(self.runtime.position, 0)
        self.assertEqual(bridge.state["deliveries"][-1]["status"], "superseded")
        self.assertFalse(any(r["action"] == "say" for r in self.runtime.requests))

    def test_new_message_during_provider_supersedes_late_response(self):
        self.runtime.start()
        bridge = self.bridge()
        self.runtime.event("step")
        original = invoke_adapter
        def newer(config, request):
            response = original(config, request)
            self.runtime.event("Actually, stop")
            return response
        with patch("bridge.bridge.invoke_adapter", newer):
            bridge.poll_once()
        self.assertEqual(self.runtime.position, 0)
        self.assertEqual(bridge.state["deliveries"][-1]["status"], "superseded")

    def test_failed_provider_is_not_replayed_after_restart(self):
        self.runtime.start()
        failing = Path(self.temp.name) / "failed adapter.py"
        failing.write_text("import sys\nprint('adapter failed',file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")
        self.config["command"] = [sys.executable, str(failing)]
        bridge = self.bridge()
        self.runtime.event("step")
        with self.assertRaisesRegex(BridgeError, "exit 7"):
            bridge.poll_once()
        self.assertEqual(bridge.state["pending"]["status"], "error_or_uncertain")
        bridge.close()
        with self.assertRaisesRegex(BridgeError, "unresolved"):
            self.bridge()
        resumed = self.bridge(resume_after_error=True)
        self.assertFalse(resumed.poll_once())
        self.assertEqual(resumed.state["deliveries"][-1]["status"], "uncertain_not_retried")

    def test_adapter_timeout_is_reported_without_repeat(self):
        config = dict(self.config)
        config.update(command=[sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=.05)
        with self.assertRaisesRegex(BridgeError, "timed out"):
            invoke_adapter(config, {})

    def test_agent_identity_and_second_bridge_are_guarded(self):
        first = self.bridge()
        with self.assertRaisesRegex(BridgeError, "lock exists"):
            self.bridge()
        first.close()
        self.config["agent_id"] = "different-agent"
        with self.assertRaisesRegex(BridgeError, "another agent_id"):
            self.bridge()

    def test_response_envelope_and_results_action_limit(self):
        request = {"schema_version": 1, "request_id": "request", "agent_id": "agent",
                   "session_id": self.runtime.session, "human_event_id": 1, "stop_revision": 0, "phase": "results"}
        response = {k: v for k, v in request.items() if k != "phase"}
        response.update(reply="hello", actions=[])
        self.assertEqual(validate_response(request, response), response)
        response["session_id"] = str(uuid.uuid4())
        with self.assertRaisesRegex(BridgeError, "identity"):
            validate_response(request, response)
        response["session_id"] = request["session_id"]
        response["actions"] = [{"action": "move", "params": {}}]
        with self.assertRaisesRegex(BridgeError, "Results phase"):
            validate_response(request, response)

    def test_cli_relocated_package_and_queue_with_spaces(self):
        self.runtime.start()
        relocated = Path(self.temp.name) / "Fresh package with spaces"
        shutil.copytree(ROOT / "client", relocated / "client", ignore=shutil.ignore_patterns("__pycache__"))
        result = subprocess.run([sys.executable, str(relocated / "client" / "player.py"),
            "--root", str(self.root), "observe", "--no-capture"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["reply"]["session_id"], self.runtime.session)


if __name__ == "__main__":
    unittest.main()
