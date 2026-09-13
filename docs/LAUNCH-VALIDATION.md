# Launch validation addendum

The source in `0.1.0-preview.2` retains the native runtime verified for the first preview. Its recorded native source hashes still match. The existing 31 Python tests remain the baseline; hosted CI checks the release separately.

## Walkthrough and images

The 32-second video is an edited product walkthrough. It includes static explanatory graphics and two real native camera captures from the original isolated generic test world. The two captures were produced by direct client commands, including a 90-degree turn. They are not footage of a live model interaction. The captions make this distinction explicit.

The generic diagnostic scene is dark. The images establish camera operation; they do not demonstrate a polished environment, a finished avatar or continuous animation. The two primary launch gallery cards explain the reusable software rather than presenting the diagnostic world as a shipped game.

## Connection-status UI

The current chat panel does not display bridge connection, thinking or failure status. Inspect the bridge terminal when no reply arrives. A proposed status label and heartbeat change passed its portable checks, but its isolated native rebuild did not finish within the bounded validation window. Those changes were excluded from this release; the earlier verified runtime is preserved.

## Bounded launch-day check attempt

A later isolated startup did not produce a runtime heartbeat before its cutoff, so the planned provider/native check was not executed. No model call was made. The owned probe and build processes were stopped. This attempt adds no successful runtime or model evidence and does not replace the earlier successful checkpoint. The [machine-readable attempt record](launch-attempt.json) reports this outcome explicitly.

## Remaining boundaries

Human keyboard chat, a full keyboard-to-live-model-to-native-action conversation, arbitrary imported rigs, packaged games, other native platforms and multiplayer are not validated by this walkthrough. Consult [the original validation record](VALIDATION.md) for the tested plugin and diagnostic bridge behavior.
