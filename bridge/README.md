# Connect a conversation to the world

Start the plugin in your own Unreal map first. From the extracted starter folder:

```powershell
python bridge/bridge.py --root "D:/UnrealProjects/MyProject/Saved/AgentEmbodiment" --config examples/mock-agent.json
```

Replace the runtime path with your own. Wait for the connected message, then type a **new** human message in the world's chat. The included provider is a deterministic connection diagnostic, not a model. It requires no account or network access.

The bridge watches new events, obtains a native observation, calls the configured provider, validates bounded actions, executes them through the client, and returns a correlated reply. Its results phase lets a provider describe actual outcomes after actions. An idle bridge makes no provider calls.

For a real model, use the [Codex adapter](../adapters/README.md) or implement your own provider using [the JSON contract](PROTOCOL.md). To switch between the included diagnostic and Codex configurations, stop the bridge and restart Unreal Play first: the configurations identify different agents.

This is a local subprocess adapter. No private desktop connection or existing conversation identifier is required. The configured provider is executable code you choose to run. Model/provider account setup is separate from Unreal and from the diagnostic path.

The [protocol reference](PROTOCOL.md) contains exact configuration, JSON fields, result handling, state files and recovery behavior. After an uncertain delivery, inspect its receipts before explicitly resuming. The bridge does not automatically repeat an uncertain action or replay old messages on first startup.
