# Build on the starter

Start by reproducing a single observation and a short movement in your map. Keep that working path while adding your next capability.

## Your character and environment

The plugin supplies a native Character class. Your project supplies the map, floor/collision, spawn locations, optional mesh, material and animation class. A Blueprint subclass is the simplest place to set your own mesh transform and eye height. Recheck captures from the agent's actual eyes after every camera or mesh change.

The collision capsule and rendered mesh serve different purposes. Collision results do not prove skin contact. An imported skeletal mesh does not automatically supply a walking animation or appropriate proportions. Use your own animation pipeline as needed.

## Another agent host

Keep the bridge's provider JSON contract and replace the configured provider executable. The provider receives the human event and current observation, then proposes bounded actions and text. The bridge validates and runs the supported actions through the command client. Consult the bridge README for exact request/response fields, failure behavior and state files.

The included Codex adapter is one provider example. You can instead wrap another hosted model, a local model or an existing agent service. Host selection is independent of Unreal rendering and body motion. Add your own conversation memory deliberately; the starter does not distribute a persona or memory archive.

## New actions

Add an action to the native plugin's request handler, enforce its limits at that boundary, and return the actual result. Add the corresponding client command/validation and bridge allowlist entry. Then add a meaningful test for the new behavior and a real Unreal check before advertising it.

Examples of extensions a developer could implement include navigation to a named waypoint, animation-state selection, an additional sensor, or interaction with an actor interface. These are extension ideas, not features claimed by this release.

## Keep observations useful

The command result and the image belong to a particular action and runtime session. Preserve those identities when adding sensors or asynchronous behavior. If an image is unavailable, report that absence. Do not substitute an old screenshot and label it current.

## Keep interruption local

F10 and the native stop command can stop movement without waiting for model reasoning. Preserve this property when adding routines. Timeouts are uncertain delivery outcomes, not permission to repeat an action. Reobserve before deciding what to do next.

## Deliberate limits

This starter has one agent actor, one local human player, and a small action vocabulary. It does not implement physical hands, universal rig retargeting, multiplayer, speech audio, continuous perception, autonomous planning, or general save/load of dynamic world state. Build one of those deliberately if your project needs it.
