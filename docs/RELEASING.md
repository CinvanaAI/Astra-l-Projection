# Preparing a source release

The repository is named Astra-l-Projection. The public launch package is
`0.1.0-preview.2`; it adds launch presentation and validation documentation.
Its native plugin remains byte-identical to the verified `0.1.0` checkpoint.
A proposed chat-status change was excluded because its native rebuild did not
finish within the validation window.

Run the three Python suites listed in [validation](VALIDATION.md), followed by:

```text
python -B tools/check_repository.py
python -B tools/build_release.py --output ../release-files
python -B tools/check_package.py
```

The output directory must be outside the checkout. The builder uses a source
allowlist, regenerates `MANIFEST.json`, and writes a ZIP and SHA-256 checksum.
It checks source syntax, local documentation links and the recorded native
source hashes. Review the actual inventory for privacy and provenance before
publishing; an allowlist is not a credential scanner.

Commit the updated inventory alongside the release source. Publish the archive
from that exact commit as a GitHub **prerelease**. Do not include local build
hosts, runtime queues, recordings, credentials or private project assets.

The CI workflow checks Python on Windows and Linux without calling a model or
installing Unreal. It does not enforce the whole-release manifest on every PR;
ordinary edits necessarily change those hashes. Native source changes require
fresh build/runtime evidence and an updated plugin verification record. For a
new release, update `VERSION` in the builder, the changelog and validation notes,
then regenerate the inventory after all other edits are complete.
