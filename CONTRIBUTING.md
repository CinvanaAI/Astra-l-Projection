# Contributing

Start with [the quickstart](docs/QUICKSTART.md), [validation record](docs/VALIDATION.md), and [extension guide](docs/EXTENDING.md). A useful contribution can be a reproducible setup report, a documentation correction, a new provider, or a small runtime capability with measured results.

## Report a finding

Open an issue with the engine/Python/OS versions, the step you tried, what you expected, and what actually happened. Include a minimal reproduction or a short relevant error excerpt. State whether you used the diagnostic provider or a live model. Remove account details, personal paths, chat history, and unrelated logs before posting.

The [reviewer guide](docs/REVIEWER-GUIDE.md) provides a focused first pass. A failed fresh installation is useful evidence even if you cannot identify its cause.

## Make a change

Keep a change focused and explain the user-visible behavior it improves. Preserve session and request identities, correlated replies, local stop, atomic file publication, and the rule against automatically replaying an uncertain action. Update all affected layers when changing the action contract: native plugin, client, bridge, and provider.

Use your own scratch Unreal project with generic assets. This repository distributes code and documentation; keep character assets, maps, engine content, generated builds, runtime observations, conversations, and credentials out of commits.

## Validate it

From the repository root, run the suites relevant to your change:

```text
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s adapters/tests -v
python -B tools/test_tools.py
```

These suites need no model calls. For native changes, compile in a separate C++ host and exercise the changed behavior in Unreal. For rendered observations, inspect a fresh image in a rendered session; a headless logic check cannot establish visual output.

In your pull request, describe the change, checks performed, their environment, and any remaining gaps. Distinguish mocked provider decisions from live inference, and requested actions from observed results. Documentation-only changes need a link and command review rather than new tests.

`MANIFEST.json` is a release inventory. Intentional edits make its old hashes differ; maintainers regenerate it when preparing a release. Preserve the [MIT license](LICENSE) and [dependency notices](THIRD-PARTY-NOTICES.md).
