# Portable conversation bridge

The bridge reads durable human chat events from Unreal, obtains a fresh world
observation, calls your chosen local agent adapter, executes up to four bounded
commands, returns their measured outcomes to the adapter, then displays its final
reply in the world. It uses the supplied command client throughout.

This subprocess connection is new starter code. The earlier project connected
to an existing desktop conversation through a private local integration; that
installation-specific connection is not included. The shared concepts retained
here are session/event correlation, atomic file transport, durable receipts,
explicit silence, and refusing automatic replay after uncertain delivery.

## Start with the diagnostic adapter

Requires Python 3.10 or newer. No pip packages, account, key or model quota are
needed for the diagnostic. Start your Unreal world first. From this package:

```powershell
python bridge/bridge.py --root "C:/Projects/MyWorld/Saved/AgentEmbodiment" --config examples/mock-agent.json
```

Type `step`, `look left`, or `stop` into the native in-world chat. `step` requests
0.5 seconds of forward movement at 100 cm/s. Any other text returns an explicitly
diagnostic greeting. This adapter is deterministic code, not an AI demonstration.
The tests exercise its round trip against a fake queue peer; an actual Unreal
run is a separate check.

The default startup rule is **new messages only**: messages already present when
the bridge first connects are left alone. Send a new message after connection.
`--include-existing` opts into the current session's existing messages on first
startup. `--once` processes currently available new messages once and exits.

Only one bridge may own a queue. The world session UUID and configured `agent_id`
remain fixed for that bridge run. Changing agent identity requires a new Unreal
session. A restarted bridge resumes its same-session journal without replaying
completed messages. Several newly queued human messages are sent as history, with
the newest message as the turn's correlation anchor.

## Connect your agent

Copy `examples/mock-agent.json` and edit it. `command` is an argument array; the
bridge never interprets it through a shell. Relative script paths resolve against
`cwd`, which resolves against the config file's directory. The exact argument
`{python}` expands to the Python executable running the bridge. Spaces in paths
are supported without nested quoting inside an array item.

```json
{
  "schema_version": 1,
  "agent_id": "my-agent",
  "command": ["{python}", "my_adapter.py"],
  "cwd": ".",
  "timeout_seconds": 120,
  "command_timeout_seconds": 10
}
```

The configured executable is trusted local code and runs with your user
permissions. Choosing a hosted-model adapter means that adapter controls what it
sends to its provider. The core bridge makes no network or model API calls.

Each invocation receives one JSON object on standard input and must write one
JSON object on standard output, then exit. Put diagnostics on standard error.
The adapter process starts anew each invocation; history is supplied explicitly.
An adapter may implement its own longer-term conversation storage.

Input fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `request_id` | Unique ID for this adapter invocation |
| `agent_id` | Stable configured agent identity |
| `session_id` | Live Unreal session UUID |
| `human_event_id` | Current human event correlation anchor |
| `stop_revision` | Current native cancellation revision |
| `phase` | `plan` or `results` |
| `human_event` | The durable event: speaker, text, IDs and UTC timestamp |
| `history` | Up to 32 most recent current-session human/agent chat events |
| `observation` | Full client result: `{ "reply": ..., "client": ... }` |
| `results` | Native client results for requested actions; empty in `plan` |
| `capabilities` | Supported action names, maximum count and physical scope |

Return exactly these fields, copying every identity value with its original type:

```json
{
  "schema_version": 1,
  "request_id": "copy-from-input",
  "agent_id": "copy-from-input",
  "session_id": "copy-from-input",
  "human_event_id": 1,
  "stop_revision": 0,
  "reply": null,
  "actions": [
    {"action": "move", "params": {"forward": 1, "seconds": 0.5, "speed_cm_s": 100}}
  ]
}
```

`reply` is null for intentional silence, or nonempty text of at most 500 UTF-16
code units. `actions` contains zero to four `observe`, `move`, `look`, or `stop`
objects. The bridge owns command identities and stop guards; adapters cannot set
those inside action parameters. In a `results` invocation, actions must be empty.

When a plan requests actions, its initial text is deferred and the bridge makes
one results invocation after the actions finish or the first fails. The results
reply becomes the spoken text. This lets the agent describe the actual outcome
instead of claiming success before execution. There are at most two provider
invocations per human turn. There is no unbounded agent action loop.

Supported parameters:

| Action | Parameters and limits |
| --- | --- |
| `observe` | `{}`; returns state and attempts a first-person PNG |
| `move` | `forward`, `right`: -1..1, default 0; `seconds`: 0.05..2, default 0.5; `speed_cm_s`: 1..300, default 120 |
| `look` | `yaw_delta_deg`: -90..90; `pitch_delta_deg`: -60..60; defaults 0 |
| `stop` | `{}`; cancels motion and advances the stop revision |

The model does not see an image merely because a path appears in JSON. A visual
adapter must explicitly load the verified PNG under the queue's `captures`
directory and send it through its model's image input. Check
`observation.client.fresh_capture_verified` first. Capture metadata validation
checks session/request/time/path/PNG header, not image meaning. Capture failure
is reported as absence; state observations can still work without rendering.

## Failure, interruption and recovery

- A session change, a human stop, or a newer human message invalidates a pending
  response. Stale body actions and speech are discarded. If an action was already
  in flight, the bridge attempts a same-session native stop.
- A provider timeout, invalid envelope or process error leaves a durable
  unresolved delivery in `bridge/state.json`. It is not automatically retried.
  The bridge attempts a native stop and exits. Inspect receipts before resuming.
- `--resume-after-error` preserves that record as uncertain, skips replay, and
  accepts newer messages. It does not prove the old command did or did not run.
- Command-client timeout means the wait ended; it does **not** itself cancel or
  retry a command. Use the saved receipt with `wait`, or send a session-pinned
  `stop`. Commands have a maximum 30-second native deadline.
- The default adapter timeout is 120 seconds. A timeout kills the configured
  direct child; an adapter that launches other processes must manage their
  cleanup itself and should use a shorter internal timeout.
- `bridge/bridge.lock/owner.json` identifies the owning PID. After a crash,
  inspect that process and remove only this lock directory once the process is
  confirmed stopped. The bridge does not guess that a lock is stale.

Runtime files contain local messages, paths and observations. They belong in the
user's project's `Saved` directory and are not part of the distributed source.
Keep the queue on a local filesystem; this is not a network service or a security
boundary between mutually untrusted processes.
