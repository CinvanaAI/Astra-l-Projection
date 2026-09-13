# Build origin and release boundary

The underlying local prototype was developed collaboratively with Astra: implementing Unreal runtime controls, a command/observation interface, local conversation routing, and repeated checks of actions against native results and rendered observations. Human direction, scope, evaluation and corrections guided that work.

This release extracts the portion useful to another developer. It retains the core model: an independently controlled human, an agent body, bounded native actions, first-person observations, local session identities, durable text events, and correlated replies.

The original source had accumulated specialized body calibration and room interaction code. The starter adapts the general runtime core into a small plugin with no original map or character dependency. The command client is adapted from the working client. The portable subprocess bridge and optional Codex provider replace installation-specific conversation routing. Those portable adaptations receive their own tests; prior private demonstrations are not used as proof that an unchanged public kit was already working.

No original avatar, room, texture, conversation, account state, session transcript or original rendered evidence is included. Diagnostic fixtures in the package are synthetic and identified as such. The runtime source uses the recipient's own installed engine; it does not include engine code or engine assets.

This is a starting implementation for builders, not a claim of new model training, general robotics, physical dexterity, a complete companion, or a universal character importer. The contribution being shared is inspectable software connecting conversational decisions to a controllable presence in an Unreal environment.

See [validation](VALIDATION.md) for release-specific evidence and remaining gaps.
