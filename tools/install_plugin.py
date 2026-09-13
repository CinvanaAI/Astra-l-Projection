"""Copy the source plugin into an existing Unreal project without overwriting it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

PACKAGE = Path(__file__).resolve().parents[1]


def install(project: Path, dry_run: bool = False) -> dict:
    project = project.expanduser().resolve(strict=True)
    if project.suffix.lower() != '.uproject' or not project.is_file():
        raise ValueError('--project must name an existing .uproject file')
    json.loads(project.read_text(encoding='utf-8-sig'))
    source = PACKAGE / 'Plugins' / 'AgentEmbodiment'
    if not (source / 'AgentEmbodiment.uplugin').is_file():
        raise ValueError('Plugin source is missing; extract the complete archive first')
    for item in source.rglob('*'):
        if item.is_symlink():
            raise ValueError('Plugin source must not contain symbolic links')
    plugins = project.parent / 'Plugins'
    if plugins.is_symlink() or plugins.resolve() != project.parent / 'Plugins':
        raise ValueError('Refusing a redirected Plugins directory')
    destination = plugins / 'AgentEmbodiment'
    if destination.exists() or destination.is_symlink():
        raise ValueError('AgentEmbodiment already exists; nothing was overwritten')
    result = {'project': str(project), 'destination': str(destination),
              'dry_run': dry_run, 'project_file_modified': False}
    if dry_run:
        return result
    plugins.mkdir(exist_ok=True)
    staging = plugins / ('.AgentEmbodiment-staging-' + uuid.uuid4().hex)
    # No replacement/deletion of an existing plugin. A failed copy leaves a
    # uniquely named staging directory for inspection, never a partial install.
    shutil.copytree(source, staging, ignore=shutil.ignore_patterns(
        'Binaries', 'Intermediate', 'Saved', '__pycache__', '*.pyc'))
    if destination.exists():
        raise ValueError(f'Destination appeared during copy; staging retained: {staging.name}')
    staging.rename(destination)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.project, args.dry_run), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
