# Preparing a source release

The repository is named Astra-l-Projection. The initial public version is
`0.1.0-preview.1`; its native plugin is the byte-identical verified `0.1.0`
implementation. The preview adds repository presentation and release tooling.

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
