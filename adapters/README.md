# Connect your own Codex CLI

This optional adapter connects the starter bridge to an authenticated Codex CLI
on your computer. The model receives the current message, recent in-world
conversation, body state and completed action results. It returns speech and a
small list of body actions. The bridge executes those through the Unreal plugin.

This is a **fresh decision call for each provider request**. It does not connect
to, resume or copy an existing Codex desktop conversation. No author's account,
conversation identifier, avatar, room or private desktop connection is included.

## Before you start

Install a current [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) and sign in
with **your own** account through its normal login flow. Choose a model available
to that account. The example selects `gpt-6-astra`; edit that value if your account
uses another available model. Python 3.10 or later is required; this adapter has
no Python dependencies.

From the extracted package root, run the offline compatibility check:

```console
python -B adapters/codex_provider.py --check
```

This only reads local CLI help. It does not authenticate, call a model, or spend
model usage. An `ok:true` result establishes flag compatibility, not account or
model availability. If automatic discovery fails, add
`--codex "C:/path/to/codex.exe"`. The resolver supports the official Windows npm
vendor layouts; it never runs a `.cmd` or `.ps1` wrapper through a shell.

## Start the bridge

First follow the [package quickstart](../docs/QUICKSTART.md) and start your own
Unreal map in Play. Use your running project's runtime queue folder as `--root`:

```console
python -B bridge/bridge.py --root "C:/YourProject/Saved/AgentEmbodiment" --config adapters/codex.example.json
```

The path above is a placeholder for **your** running project. The configuration's
`cwd` is resolved relative to the config file, so `cwd: ".."` runs the adapter
from the extracted package root. `{python}` selects the same Python interpreter
that started the bridge. If needed, add `"--codex", "C:/path/to/codex.exe"` as
two entries in the configuration's `command` array.

Send a new message through your configured in-world chat, such as “Turn a little
to the right.” The
model can request `observe`, `look`, `move`, or `stop`. Hands, grasping, navigation
planning and arbitrary editor commands are not in this adapter's action set.

**Starting this bridge with the Codex configuration enables real model calls.**
The calls use your CLI authentication and your applicable usage allowance or
billing. An event uses one planning call; a plan with actions causes one further
results call before speech is delivered. An idle bridge does not poll the model.
Use the package's deterministic provider for an offline connection demonstration.

## Optional first-person images

By default, the model receives structured state and results. The prompt explicitly
says no image is attached, so a file path is not presented as visual perception.
To include images, add these two entries to the configuration's `command` array:

```json
"--image-dir", "C:/YourProject/Saved/AgentEmbodiment/captures"
```

When enabled, the adapter attaches the latest client-verified capture to Codex
with `--image`. It requires a matching first-person observation, an absolute
capture path inside that exact directory, and the expected 640x360 PNG header.
Symlinks or paths resolving outside that directory are rejected. A missing or
unverified capture results in a state-only request. Your model must support image
input. Enabling images sends those scene captures to the model service.

## What crosses the connection

The bridge sends one JSON request on stdin and expects one JSON object on stdout;
see [the bridge protocol](../bridge/PROTOCOL.md). The model only generates
`reply` and `actions`, constrained by
[the response schema](codex-response.schema.json). The adapter copies the exact
request, agent, session, event and stop-revision identifiers into the response.
It validates action names, numeric bounds, reply length and the four-action limit.
Results-phase responses must contain no new actions. `reply: null` is deliberate
silence. Errors produce no action response and exit nonzero.

Each call runs `codex exec --ephemeral --sandbox read-only --ignore-user-config`
in a temporary directory, with stdin input, an output schema and a temporary
last-message file. It skips the repository check because the task is a decision,
not repository work. CLI diagnostics are suppressed from the bridge output.
The temporary response is removed after validation. The adapter default timeout
is 90 seconds, below the bridge's 120-second provider timeout.

Ignoring user config prevents loading the normal user `config.toml` for this
decision; authentication still uses the CLI's normal auth location. Select the
model explicitly because the usual user-config model preference is ignored.
The read-only setting is a CLI execution policy, **not a privacy isolation
boundary**. Organization policies, installed CLI behavior, service retention,
and the bridge's own local logs remain separate concerns. The adapter prompt
requests no shell, browser or MCP work; model behavior is not itself a security
guarantee. Run only a Codex executable and provider configuration you trust.

The official [non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes saved CLI authentication, ephemeral runs, read-only execution, stdin
prompts and schema-constrained output. The `--image` flag was also verified
against the installed CLI's `exec --help` during preparation.

## Verification and troubleshooting

```console
python -B -m unittest discover -s adapters/tests -v
```

These 11 offline tests replace every decision subprocess with a fake. They check
flags and stdin handling, output correlation, malformed output, failures, timeouts,
bounded actions, results-only behavior, silence, text limits, image boundaries,
and the local-help-only check. The invalid-input test runs the adapter as a real
Python subprocess and exits before any CLI invocation.

**No live model call was made while preparing this package.** Passing tests and
`--check` do not establish that a particular account/model will accept the schema
or produce the intended in-world behavior. The plugin/client/bridge's separate
verification is documented at the package root.

If a decision fails, check the normal CLI login, selected model access, and
`--check`. A model call can time out before returning; the bridge does not
automatically replay the event. Do not add retries around body commands. If the
model reports an unsupported action, extend the plugin, client validation and
bridge protocol together before broadening this adapter's schema.
