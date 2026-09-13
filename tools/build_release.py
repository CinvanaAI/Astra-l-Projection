"""Build the source-only preview and its SHA-256 inventory. No model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from check_repository import ROOT, check
from check_package import check as check_package

VERSION = '0.1.0-preview.1'
TOP_FILES = {'README.md', 'AGENTS.md', 'LICENSE', 'THIRD-PARTY-NOTICES.md',
             'CONTRIBUTING.md', 'CHANGELOG.md', '.gitignore', '.gitattributes',
             '.editorconfig'}
DIRECTORIES = {'Plugins', 'client', 'bridge', 'adapters', 'examples', 'tests',
               'tools', 'docs', 'assets', '.github'}
EXTENSIONS = {'.py', '.md', '.json', '.cpp', '.h', '.cs', '.uplugin', '.svg',
              '.yml', '.yaml', '.txt'}


def build(output: Path) -> Path:
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Choose an output directory outside this checkout')
    result = check()
    if not result['ok']:
        raise ValueError(json.dumps(result))
    inventory = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(p in {'.git', '__pycache__'} for p in relative.parts) or path.suffix == '.pyc':
            continue
        name = relative.as_posix()
        if name == 'MANIFEST.json':
            continue
        allowed = (name in TOP_FILES or (len(relative.parts) > 1
                   and relative.parts[0] in DIRECTORIES and path.suffix in EXTENSIONS))
        if not allowed:
            raise ValueError('File outside release allowlist: ' + name)
        data = path.read_bytes()
        inventory.append({'path': name, 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'package': 'Astra-l-Projection', 'version': VERSION,
                'distribution': 'source-only developer preview', 'files': inventory}
    (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    result = check_package(ROOT)
    if not result['ok']:
        raise ValueError(json.dumps(result))
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('Astra-l-Projection-v' + VERSION + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in [entry['path'] for entry in inventory] + ['MANIFEST.json']:
            bundle.write(ROOT / name, 'Astra-l-Projection/' + name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'files': len(inventory)}, indent=2))
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Directory outside the checkout')
    build(parser.parse_args().output)
