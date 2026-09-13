"""Verify the release inventory and SHA-256 hashes. Does not launch a model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def check(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    failures = []
    seen = set()
    for entry in manifest['files']:
        relative = PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative) or ':' in str(relative):
            raise ValueError('Unsafe manifest path')
        name = str(relative)
        if name in seen:
            raise ValueError('Duplicate manifest path')
        seen.add(name)
        target = root.joinpath(*relative.parts)
        if not target.resolve().is_relative_to(root) or target.is_symlink():
            failures.append({'path': name, 'error': 'redirected file'})
            continue
        if not target.is_file():
            failures.append({'path': name, 'error': 'missing'})
            continue
        data = target.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            failures.append({'path': name, 'error': 'modified'})
    extra = []
    for item in root.rglob('*'):
        if not item.is_file():
            continue
        relative = item.relative_to(root)
        if any(part in ('.git', '__pycache__') for part in relative.parts) or item.suffix == '.pyc':
            continue
        if relative.as_posix() not in seen and relative.as_posix() != 'MANIFEST.json':
            extra.append(relative.as_posix())
    return {'ok': not failures and not extra, 'version': manifest['version'],
            'verified_files': len(seen), 'failures': failures, 'extra_files': extra}


if __name__ == '__main__':
    try:
        result = check(Path(__file__).resolve().parents[1])
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['ok'] else 1)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
