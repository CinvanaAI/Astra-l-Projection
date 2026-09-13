# Agent Embodiment plugin

A source-only Unreal runtime plugin. It connects a local agent process to a body in a world you supply. No avatar, map, authored material, conversation history, or model weights are included.

## Minimal setup

1. Copy this folder into a C++ Unreal project's `Plugins` directory, then compile that project's Development Editor target. The plugin is enabled by default. The tested engine is Unreal 5.8.2 on Windows.
2. Open your own map. It needs a collidable floor and a `PlayerStart` with clear space above it.
3. Set World Settings > GameMode Override to `AgentEmbodimentGameMode`.
4. Place one `AgentEmbodimentCharacter` in the map, separate from PlayerStart. Its capsule half-height is 88 cm, so place its actor origin about 90 cm above the floor.
5. Press Play. The local player controls a separate `EmbodimentHumanCharacter`. Click the viewport to capture mouse input. WASD and mouse move the human; T opens chat; Enter sends; Esc cancels chat; F10 stops the agent.
6. Use the package's Python client and bridge with this project's `Saved/AgentEmbodiment` directory. See the package README for exact commands.

The supplied GameMode is optional integration code. In an existing game, place the agent character and use your own human pawn/UI. Send human text through `ReceiveHumanMessage(Text, Error)` and wire your stop button to `LocalEmergencyStop()`. Both are Blueprint-callable. `GetChatTranscript()` exposes the latest 12 displayed messages; complete events persist in `chat-events` for the active session.

## Use your own body

Create a Blueprint subclass of `AgentEmbodimentCharacter`. On the inherited Mesh component, select your skeletal mesh and optional Animation Blueprint, then adjust the mesh's relative transform, capsule dimensions, and EyeCamera position. Place that subclass in your map. The engine cylinder proxy hides automatically when Mesh has a skeletal asset; you can also disable `Show Diagnostic Proxy`.

This starter does not retarget skeletons, generate locomotion animation, solve hand placement, or guarantee arbitrary avatar alignment. A body without an Animation Blueprint can move as a rigid reference pose. The default camera hides the inherited Mesh and diagnostic cylinder from its own scene capture. Hide any additional body attachments in EyeCapture if needed.

## Native interface

- `observe`: current position, velocity, view angles, motion/grounded status, stop revision, chat event pointers, and optional 640x360 first-person PNG.
- `move`: local forward/right input in [-1,1], duration 0.05-2 seconds, speed 1-300 cm/s. CharacterMovement supplies collision and gravity. The result reports completion, interrupted movement, or stopped forward progress; this is not pathfinding.
- `look`: relative yaw up to 90 degrees and pitch up to 60 degrees per command, with total pitch limited to 80 degrees. Rejected while moving.
- `stop`: stop movement, increment stop revision, and invalidate commands based on the previous revision.
- `say`: persist agent text with optional correlation to a human event in this session.

The JSON transport, capture encoder, movement bounds, event persistence, and separate-human pattern were extracted and simplified from a working embodiment project. Portable integration, explicit freshness checks, and neutral defaults were added for this starter.

The queue defaults to `Saved/AgentEmbodiment`. Set Queue Directory on the placed agent, or launch Unreal with `-AgentQueue="absolute/path"`, to override it. Run one agent and one Play instance per queue. The module uses local files and opens no network listener. The bridge/provider may use network access depending on what you configure.

The queue publishes a one-second heartbeat and a fresh session UUID on each Play. It accepts only expiring, session-matched commands; body actions require the expected stop revision. Claims precede execution. Already claimed IDs cannot run again, even if their result is missing. A missing reply remains an uncertain delivery and is not retried automatically. Queue files are a local trust boundary: any process that can write them can request supported actions.

To extend the action set, edit `ParseCommand` and `ExecuteCommand` in `AgentEmbodimentCharacter.cpp`, add measured state/result fields, and update the Python client and bridge allowlists. Keep each action bounded and preserve stop/session checks. No special model, desktop conversation identifier, authored room, or character bone naming scheme is required by the plugin.

## Validation

See `verification.json` for this extracted source's measured checks. The isolated native test host is separate from the distributed plugin and uses only Engine primitives. UI keyboard behavior and arbitrary user avatar/animation integration require validation in your own project. No packaged game build, marketplace submission, Linux/macOS runtime, multiplayer replication, or production readiness is claimed.
