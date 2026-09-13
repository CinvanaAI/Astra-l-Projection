# Start with one body in your own world

The first milestone is small: ask for an image, turn the agent, move a short distance, and show a text reply. You can do this before connecting a model or creating an avatar.

## 1. Prepare a C++ project

Use an Unreal C++ project with a native compiler/toolchain compatible with your engine. A Blank C++ project is enough. Install Python 3.10 or newer. This is a source distribution; it does not include a precompiled engine-specific plugin binary.

Close your project's editor while installing and compiling. Clone this repository or extract the developer-preview archive, then open a terminal in the folder containing `README.md`, `Plugins`, and `client`.

## 2. Install the plugin source

Replace the example project path with your own `.uproject` file:

```powershell
python tools/install_plugin.py --project "D:\UnrealProjects\MyProject\MyProject.uproject" --dry-run
python tools/install_plugin.py --project "D:\UnrealProjects\MyProject\MyProject.uproject"
```

The installer copies only `Plugins/AgentEmbodiment` and refuses to overwrite an existing plugin. It does not edit your project file or install the bridge inside your project. Keep this starter folder to run its Python tools.

Manual installation is also valid: copy `Plugins/AgentEmbodiment` into your project's `Plugins` directory. Generate/refresh your C++ project files as needed, then compile your project's **Development Editor** target. Open your project and check that Agent Embodiment is enabled in Plugins. This follows [Epic's source-plugin integration](https://dev.epicgames.com/documentation/unreal-engine/plugins-in-unreal-engine).

## 3. Set up your map

Use a map you own with a blocking floor and a PlayerStart. In World Settings, choose **AgentEmbodimentGameMode** as the GameMode Override. Place an **AgentEmbodimentCharacter** in the map, above the floor and away from PlayerStart. The game mode provides the separate human player; the placed character is the agent.

Start with exactly one agent actor and one local player. Keep the capsule clear of walls and floor at spawn. Start Play in a standalone local session or a single local Play-in-Editor session. The simple diagnostic shape uses engine primitives and requires no imported character.

Human controls: **WASD** and mouse; **T** opens chat, **Enter** submits it, **Escape** cancels chat; **F10** stops the agent. Input-focus details can differ between standalone and editor play; the command client offers an independent stop command.

The runtime writes a folder under your project:

```text
Saved/AgentEmbodiment/
```

## 4. Try the body without a model

In a terminal at the extracted starter folder, set the runtime path to your own project's folder:

```powershell
$queuePath = "D:\UnrealProjects\MyProject\Saved\AgentEmbodiment"
python client/player.py --root $queuePath observe
python client/player.py --root $queuePath look --yaw-delta-deg 15
python client/player.py --root $queuePath move --forward 1 --seconds 0.25 --speed-cm-s 80
python client/player.py --root $queuePath say --text "Hello from the embodiment interface."
python client/player.py --root $queuePath stop
```

`observe` returns JSON identifying a new eye-camera image. Open the returned image path and inspect it. `move` returns the actual result of the bounded move, including a blocked or interrupted result when applicable. A requested action is not proof that it completed.

Use `python client/player.py --help` for the exact client options. All global options go before the action. See [client instructions](../client/README.md) for captures, timeouts and result handling.

## 5. Connect a conversation

First run the [bridge diagnostic](../bridge/README.md) with the included example provider. Type a new message in the Unreal chat after the bridge begins watching. Confirm the reply appears in the world. This verifies message delivery without consuming model credits.

To change from the diagnostic provider to Codex, stop the diagnostic bridge, stop Play, and start Play again. Then start the Codex bridge. The example configurations have different agent identities; a fresh Unreal session prevents the new provider from inheriting the diagnostic provider's delivery state.

Follow the [optional Codex provider instructions](../adapters/README.md) to connect your own authenticated CLI, or implement the documented JSON provider interface for your own agent host. The bridge executes a configured program directly; human chat text is input data, never a shell command.

The diagnostic provider is not AI. The optional Codex provider makes model calls and uses your account's allowance. This starter does not connect to or copy an existing private conversation.

For visual model decisions, enable the Codex adapter's `--image-dir` option as documented there. Its default mode sends measured state and text; a capture's filename alone does not let the model see the world.

## 6. Attach your character and extend

Create a Blueprint subclass of AgentEmbodimentCharacter. Assign your own skeletal mesh and animation class on its inherited mesh component. Adjust the mesh transform and eye-camera position for that character. Replace the diagnostic actor in your map with your subclass, then repeat the short observation/movement checks.

Walking collision comes from the character capsule. Animation and mesh calibration remain your project's responsibility. [Extension notes](EXTENDING.md) explain where to add behavior.

## If the first check fails

| Symptom | Check |
| --- | --- |
| Plugin classes are missing | Build the C++ Editor target, enable the plugin and reopen the project. |
| `runtime.json` is missing | Confirm Play is running, one agent actor is placed, and the root points to this project. |
| Session mismatch | Stop issuing actions, inspect the current runtime, then start a fresh request. Do not replay an uncertain move. |
| Agent falls or is blocked | Check your floor's blocking collision, capsule spawn clearance and map coordinates. |
| No rendered image | Use a local rendered play session. A NullRHI/headless logic test cannot prove camera rendering. |
| No conversation reply | Confirm the bridge was started, a new human message was sent, the provider finished successfully, and both processes use the same runtime root. |

Keep the plugin and bridge in one trusted local user's workspace. This file queue is a local integration surface, not a network service or multiplayer protocol.
