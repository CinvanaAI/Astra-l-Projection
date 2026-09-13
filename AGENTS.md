# Working on Agent Embodiment

This is a source-only Unreal developer starter. Read README.md, docs/QUICKSTART.md and docs/VALIDATION.md before changing or describing its behavior.

## Keep the parts distinct

- Plugins/AgentEmbodiment owns native movement, observation, camera capture, human controls, chat events and the session-bound file queue.
- client/player.py owns command submission, receipts and validation of matching results.
- bridge/bridge.py owns event routing and the bounded provider action loop.
- adapters/ contains an optional Codex CLI provider; examples/ contains a deterministic diagnostic provider.
- The recipient's Unreal project owns maps, character assets, animation and model/provider credentials. Do not add those to this source distribution by accident.

## When extending

Preserve session IDs, request IDs, reply correlation, stop revisions, atomic file publication and no automatic retry of uncertain actions. Keep local stop independent of provider latency. Do not call a requested move a completed move; inspect its result. A file path is not visual observation unless the corresponding image was actually loaded.

Changes to the action contract require corresponding native, client, bridge and provider changes. Start with a bounded action and a clear rejection path. Do not advertise arbitrary rig compatibility, new physical interaction or new provider support from source inspection alone.

## Validation

From the package root, run the suites relevant to the changed components:

```text
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s adapters/tests -v
python -B tools/test_tools.py
```

The Python fixtures are not Unreal simulations. Native changes require compilation in an isolated C++ host project and a real runtime check. Use a scratch project with generic diagnostic geometry; do not modify an unrelated active project to test this kit.

The diagnostic provider makes no model requests. The optional Codex provider does. Use the diagnostic path for routine transport tests, and clearly label whether live provider inference was exercised.

## Distribution

Preserve the MIT license and dependency notices. Ship source and documentation; exclude Binaries, Intermediate, Saved, caches, credentials and runtime logs. MANIFEST.json describes the original release; regenerate an inventory for a new release instead of treating hashes from this one as evidence for modified code.
