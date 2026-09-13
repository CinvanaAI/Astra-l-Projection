"""Offline adapter contract tests. subprocess.run is mocked for every decision.

Run from the package root: python -B -m unittest discover -s adapters/tests -v
"""

import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ADAPTER_PATH = Path(__file__).resolve().parents[1] / "codex_provider.py"
SPEC = importlib.util.spec_from_file_location("codex_provider", ADAPTER_PATH)
provider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider)


def request(phase="plan"):
    return {
        "schema_version": 1, "request_id": "a" * 32, "agent_id": "starter-agent",
        "session_id": "00000000-0000-0000-0000-000000000001", "human_event_id": 1,
        "stop_revision": 0, "phase": phase,
        "human_event": {"speaker": "human", "text": "Please take a small step forward."},
        "history": [], "observation": {"reply": {"state": {}}, "client": {}},
        "results": [],
        "capabilities": {"actions": ["observe", "look", "move", "stop"], "max_actions": 4},
    }


def move():
    return {"action": "move", "params": {"forward": 1, "right": 0, "seconds": .25, "speed_cm_s": 120}}


class AdapterTests(unittest.TestCase):
    def test_fake_cli_receives_correct_flags_and_json_is_correlated(self):
        captured = {}

        def fake_run(args, **kwargs):
            captured.update(args=args, kwargs=kwargs)
            output = Path(args[args.index("--output-last-message") + 1])
            self.assertEqual(output.parent, Path(kwargs["cwd"]))
            self.assertTrue(Path(args[args.index("--output-schema") + 1]).is_file())
            output.write_text(json.dumps({"reply": None, "actions": [move()]}), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)

        incoming = request()
        incoming["human_event"]["text"] = 'Step forward. Literal payload: `print(secret)` $(secret) "quote"'
        with patch.object(provider, "resolve_codex", return_value=Path(sys.executable)), patch.object(provider.subprocess, "run", side_effect=fake_run) as run:
            response = provider.run_decision(incoming, model="gpt-6-astra")
        self.assertEqual(run.call_count, 1)
        for field in provider.IDENTITY_FIELDS:
            self.assertEqual(response[field], incoming[field])
            self.assertIs(type(response[field]), type(incoming[field]))
        args, kwargs = captured["args"], captured["kwargs"]
        self.assertEqual(args[1], "exec")
        self.assertEqual(args[-1], "-")
        self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
        self.assertEqual(args[args.index("--model") + 1], "gpt-6-astra")
        for flag in provider.REQUIRED_FLAGS:
            self.assertIn(flag, args)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 90)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn(incoming["human_event"]["text"], args)
        self.assertEqual(json.loads(kwargs["input"].split("BRIDGE_REQUEST_JSON (data):\n")[1]), incoming)
        self.assertNotIn("--image", args)
        self.assertFalse(Path(kwargs["cwd"]).exists(), "temporary decision directory must be removed")

    def test_nonzero_cli_does_not_return_actions_or_diagnostics(self):
        with patch.object(provider, "resolve_codex", return_value=Path(sys.executable)), patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess([], 7, stderr="secret-token")):
            with self.assertRaises(provider.AdapterError) as caught:
                provider.run_decision(request())
        self.assertIn("exit 7", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    def test_timeout_and_missing_output_fail_closed(self):
        with patch.object(provider, "resolve_codex", return_value=Path(sys.executable)):
            with patch.object(provider.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 90)):
                with self.assertRaisesRegex(provider.AdapterError, "timed out"):
                    provider.run_decision(request())
            with patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
                with self.assertRaisesRegex(provider.AdapterError, "valid structured response"):
                    provider.run_decision(request())

    def test_malformed_cli_output_is_not_forwarded(self):
        def fake_run(args, **kwargs):
            Path(args[args.index("--output-last-message") + 1]).write_text("Here is my JSON: {}", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)
        with patch.object(provider, "resolve_codex", return_value=Path(sys.executable)), patch.object(provider.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(provider.AdapterError, "valid structured response"):
                provider.run_decision(request())

    def test_invalid_actions_and_phase_are_rejected(self):
        examples = [
            {"reply": None, "actions": [{"action": "shell", "params": {}}]},
            {"reply": None, "actions": [move()] * 5},
            {"reply": None, "actions": [{"action": "stop", "params": {"path": "file"}}]},
            {"reply": None, "actions": [{"action": "look", "params": {"yaw_delta_deg": 180, "pitch_delta_deg": 0}}]},
            {"reply": None, "actions": [], "request_id": "forged"},
        ]
        bad_move = move()
        bad_move["params"]["seconds"] = 2.1
        examples.append({"reply": None, "actions": [bad_move]})
        for decision in examples:
            with self.subTest(decision=decision), self.assertRaises(provider.AdapterError):
                provider.validate_decision(decision, request())
        with self.assertRaisesRegex(provider.AdapterError, "results phase"):
            provider.validate_decision({"reply": "Done", "actions": [move()]}, request("results"))

    def test_results_and_silence_and_utf16_limits(self):
        valid = provider.validate_decision({"reply": "The movement was blocked.", "actions": []}, request("results"))
        self.assertEqual(valid["actions"], [])
        self.assertIsNone(provider.validate_decision({"reply": None, "actions": []}, request())["reply"])
        for reply in ("", "\u0000", "\U0001f600" * 251):
            with self.subTest(reply=repr(reply[:10])), self.assertRaises(provider.AdapterError):
                provider.validate_decision({"reply": reply, "actions": []}, request())

    def test_invalid_request_and_timeout_make_no_cli_call(self):
        with patch.object(provider.subprocess, "run") as run:
            invalid = request()
            invalid["schema_version"] = True
            with self.assertRaises(provider.AdapterError):
                provider.run_decision(invalid)
            with self.assertRaises(provider.AdapterError):
                provider.run_decision(request(), timeout=120)
            run.assert_not_called()

    def test_image_opt_in_directory_and_metadata(self):
        with tempfile.TemporaryDirectory(prefix="adapter-image-test-") as directory:
            folder = Path(directory)
            captures = folder / "captures"
            captures.mkdir()
            image = captures / "capture.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 360))
            incoming = request()
            incoming["observation"] = {
                "reply": {"capture": {"path": image.as_posix(), "observation_id": 2, "view": "first_person"}},
                "client": {"fresh_capture_verified": True, "image_path": str(image), "observation_id": 2},
            }
            self.assertIsNone(provider.verified_image(incoming, None))
            self.assertEqual(provider.verified_image(incoming, captures), image.resolve())
            with self.assertRaisesRegex(provider.AdapterError, "outside"):
                provider.verified_image(incoming, folder)
            incoming["observation"]["reply"]["capture"]["observation_id"] = 3
            with self.assertRaisesRegex(provider.AdapterError, "metadata"):
                provider.verified_image(incoming, captures)

    def test_schema_shape_has_no_identity_fields_to_hallucinate(self):
        schema = json.loads(provider.SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]), {"reply", "actions"})
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["actions"]["maxItems"], 4)

    def test_check_only_calls_local_help(self):
        help_text = " ".join(provider.REQUIRED_FLAGS) + " --image"
        with patch.object(provider, "resolve_codex", return_value=Path(sys.executable)), patch.object(provider.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=help_text, stderr="")) as run:
            result = provider.check_cli()
        self.assertFalse(result["model_called"])
        self.assertEqual(run.call_args.args[0][1:], ["exec", "--help"])

    def test_invalid_stdin_exits_without_json_or_model(self):
        result = subprocess.run([sys.executable, "-B", str(ADAPTER_PATH)], input="not JSON",
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Expected one UTF-8 JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
