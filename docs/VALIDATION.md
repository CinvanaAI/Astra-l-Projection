# Release validation — native 0.1.0 / repository 0.1.0-preview.1

This record concerns the extracted starter package. Prior private prototype demonstrations are not counted as tests of this release.

The public Astra-l-Projection preview preserves the native source recorded below and adds repository documentation, review templates, CI and release tooling. See [release preparation](RELEASING.md). CI reports its own Python platform results separately; it does not run Unreal.

## Environment

- Native build: Unreal Engine 5.8.2, Win64 Development Editor, Visual Studio 2022 C++ toolchain.
- Python checks: Python 3.13.5 on Windows. Source utilities require Python 3.10 or newer; other Python/OS combinations have not been exercised here.
- The native host is a separate scratch C++ project. It uses engine diagnostic geometry and lights, with no original character or map dependency. It is not included in the distribution.

## Verified software checks

| Check | Result and scope |
| --- | --- |
| Native source build | Passed: the plugin's reflected classes, implementation and module compiled and linked in the isolated host. |
| Native runtime logic | 11 checks passed in a real Unreal session using NullRHI. Measured movement was 102.07 cm; view changed by 30 degrees yaw and 10 degrees pitch. Stop interrupted an active move, a wall blocked progress, and stale/expired/duplicate commands were rejected. |
| Native conversation round trip | Passed: a human event injected through the public native method reached the real Python bridge and diagnostic provider subprocess, then returned as a correlated native text reply. This did not use keyboard input or a live model. |
| Rendered eye observations | Passed in a separate rendered Unreal run: two fresh 640x360 first-person PNGs, with the second taken after a 90-degree turn. Both images were opened and inspected; floor/horizon changed with the view. The diagnostic scene was dark, so this establishes camera operation rather than presentation quality. |
| Client and bridge | 18 tests passed. Includes actual provider subprocess execution against a synthetic native peer, paths with spaces, relocated files, action bounds, identity checks, interruption, duplicate prevention and uncertain-delivery handling. |
| Optional Codex adapter | 11 tests passed. Provider decisions are mocked; native CLI help was checked for required flags without calling a model. |
| Installer | Two tests passed. A project path with spaces installs correctly; dry-run is read-only, the project file stays unchanged, and an existing plugin is not overwritten. |
| Source and documentation | Python syntax, JSON parsing and relative documentation links are checked before packaging. |
| Distribution | The archive is allowlisted to source/documentation, scanned for original-project references, and verified against a SHA-256 file inventory. |

The Python tests exercise the transport and provider contracts. They do not simulate Unreal physics, prove rendered image contents, or certify model behavior. Native runtime findings are recorded separately in the [plugin verification record](../Plugins/AgentEmbodiment/verification.json).

The NullRHI run deliberately disables graphics. Its image request correctly returned `renderer_unavailable`, with no fabricated capture. Camera rendering was checked separately in the rendered run above. Both scratch runtime processes subsequently exited normally.

## Reproduce the portable checks

Run these from the extracted package root:

```text
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s adapters/tests -v
python -B tools/test_tools.py
python -B adapters/codex_provider.py --check
python -B tools/check_package.py
```

The adapter compatibility check requires a local Codex CLI installation; the three test suites do not require model access. The integrity check is intended for the unmodified release. Changes you make to the source will appropriately change its hashes.

To reproduce native behavior in your own map, follow [the quickstart](QUICKSTART.md): compile, start one local Play session, observe, turn, make one short move, stop, and send a diagnostic conversation message. Inspect the actual image and movement rather than relying only on a successful command submission.

## Explicit gaps

No live Codex model request was made during packaging. Account authentication, model access, live structured-output acceptance and model-selected actions still require your own check. The optional adapter is documented and tested at its subprocess/JSON boundary; it is not described as a completed live-model demonstration.

Keyboard chat interaction, user-defined mesh/animation setup, packaged-game cooking, other engine versions, Linux/macOS and multiplayer remain unverified. This is a source developer starter, not a precompiled game or a production readiness certificate.

The [build provenance](PROVENANCE.md), [native plugin notes](../Plugins/AgentEmbodiment/README.md), and [provider verification](../adapters/verification.json) explain which implementation was extracted and which portability work was added.
