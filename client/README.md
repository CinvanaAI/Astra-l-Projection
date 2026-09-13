# Direct command client

Python 3.10+, standard library only. Start the Unreal world with one
AgentEmbodiment character and run from the package directory:

```powershell
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" observe
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" look --yaw-delta-deg 30
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" move --forward 1 --seconds 0.5
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" say --text "Hello from the command client."
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" stop --no-capture
```

The plugin publishes `runtime.json` in its queue directory. The client checks the
live session UUID, directory and heartbeat, pins body commands to the current
stop revision, writes a durable receipt, and atomically publishes a command to
`inbox`. It waits for the matching `outbox` reply and verifies identity and fresh
observation/capture metadata. Each command uses a unique ID and is submitted once.

For a tool-enabled agent, read the live session and stop revision from an initial
observation, then require them explicitly on subsequent actions:

```powershell
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" --session "SESSION-UUID-FROM-RUNTIME" move --forward 1 --seconds 0.5 --expected-stop-revision 0
```

Replace both placeholders with the live values. This prevents a delayed agent
decision from silently following a restarted world or human stop.

`--no-wait` submits and returns a command ID and receipt path immediately. Receipts
default to `Saved/AgentEmbodiment/client-receipts`; `--receipts` overrides that
location. Resume waiting without re-submitting:

```powershell
python client/player.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" wait COMMAND_ID
```

`--timeout` controls the wait (default 10 seconds, maximum 60), not cancellation.
A timed-out command may still execute before its 30-second native deadline. Use
`wait` to inspect it or submit `stop` to the same live session. The client never
automatically retries commands.

Every native action accepts `--no-capture`. By default the client asks for a
640x360 first-person PNG. A successful path/header/provenance check is reported
as `fresh_capture_verified`; an adapter must open that file to actually see it.
Reported rendering failure does not fabricate an image and need not prevent a
state-only observation.

The Python API is also importable:

```python
from client.player import submit, wait_for_reply

receipt = submit(queue_path, "observe", expected_session=session_uuid)
result = wait_for_reply(receipt)
print(result["reply"]["state"])
```

Exit code 0 means native completion, 1 means a native rejection/block/interruption,
and 2 means client validation, I/O or timeout failure. Inspect `reply.status`,
`reply.ok`, and the measured state rather than treating receipt creation as success.

The transport and core validation were extracted from the working project client.
The starter intentionally exposes only `observe`, `look`, `move`, `stop`, and
`say`; avatar-specific poses and object/hand manipulation are outside this package.
