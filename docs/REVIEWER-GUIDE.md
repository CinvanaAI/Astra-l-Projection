# Review Astra-l-Projection

The question for this review is concrete: **can another developer understand, install, and build on this connection between an agent and an Unreal body?** You do not need a custom avatar or paid model usage for the initial checks.

## A quick inspection

Read the [overview](../README.md) and [validation record](VALIDATION.md), then follow one action through the code:

| Layer | Starting point | What to inspect |
| --- | --- | --- |
| Native world | [AgentEmbodimentCharacter.cpp](../Plugins/AgentEmbodiment/Source/AgentEmbodiment/Private/AgentEmbodimentCharacter.cpp) | Command bounds, movement results, capture behavior, session checks, and stopping. |
| Client | [player.py](../client/player.py) | Matching requests to results, timeout behavior, and capture metadata validation. |
| Conversation | [bridge.py](../bridge/bridge.py) and [provider contract](../bridge/PROTOCOL.md) | Human event → provider → action → measured result → reply; stale responses and uncertain delivery. |
| Provider | [Diagnostic example](../examples/mock_agent.py) and [optional Codex adapter](../adapters/README.md) | Which behavior is deterministic, what a model receives, and where account/model access begins. |

Check whether the documentation's promises match those paths. A successful command submission alone is not proof that the agent moved or that the model saw an image.

## Try it without Unreal or a model

From the repository root, with Python installed:

```text
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s adapters/tests -v
python -B tools/test_tools.py
```

The recorded result is 31 passing Python tests. These exercise transport, subprocess, provider, and installation contracts using synthetic fixtures and mocked provider decisions. They do not establish physics, rendering, or live model behavior.

## Try a fresh Unreal project

Follow the [quickstart](QUICKSTART.md) in your own C++ project. The release was built with Unreal Engine 5.8.2 on Windows; record your own engine and toolchain versions.

1. Compile the plugin and set up a blocking floor, PlayerStart, game mode, and one agent actor.
2. Request an observation and open the actual image. Turn the agent and request another image to confirm the viewpoint changes.
3. Make a short move, inspect its result, and try a stop during movement. Check that the human player remains independently controllable.
4. Start the diagnostic bridge, send a new message in the Unreal chat, and look for a corresponding reply. Record whether keyboard input works in your play mode; that remains an unverified release path.
5. If useful, attach your own character and repeat the checks. Mesh, eye height, and animation need your project's setup; arbitrary character compatibility is not established.

Live model testing is optional. The [Codex adapter](../adapters/README.md) uses your own authenticated CLI and usage allowance. Record whether image input was enabled; a path in text is not an image supplied to the model.

## Feedback that helps most

- The first instruction that was missing, ambiguous, or incorrect.
- A claim that goes beyond the evidence or a capability that was harder to find than it should be.
- A reproducible failure, especially around stopping, session changes, stale actions, or duplicate delivery.
- Whether the boundaries between plugin, client, bridge, and provider make extension understandable.
- One concrete improvement that would help you use the project yourself.

Open a repository issue with your setup, exact steps, expected and actual behavior, and a small relevant error excerpt. Remove private paths, conversations, account details, and credentials before sharing. Screenshots of your own neutral test scene are useful when they show the result being discussed.

## Evidence boundary

The native build, runtime, diagnostic conversation, and camera checks are recorded in [VALIDATION.md](VALIDATION.md). Live Codex inference, keyboard chat, custom character/animation integration, other engines/operating systems, packaged-game cooking, and multiplayer remain unverified. This review should help establish those facts where practical, with each new result tied to its actual environment.
