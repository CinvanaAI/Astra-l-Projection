"""Check source consistency without invoking Unreal, an account, or a model."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '__pycache__'}
FORBIDDEN_DIRS = {'Binaries', 'Intermediate', 'Saved', '.vs', 'bridge-state'}
FORBIDDEN_EXTENSIONS = {'.uasset', '.umap', '.fbx', '.blend', '.dll', '.exe',
                        '.pdb', '.dmp', '.log', '.png', '.jpg', '.mp4', '.zip'}


def check(root: Path = ROOT) -> dict:
    root = root.resolve()
    failures = []
    files = [p for p in root.rglob('*') if p.is_file()
             and not any(part in SKIP for part in p.relative_to(root).parts)
             and p.suffix != '.pyc']
    for path in files:
        relative = path.relative_to(root)
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('redirected source file')
            if (any(part in FORBIDDEN_DIRS for part in relative.parts)
                    or path.suffix.lower() in FORBIDDEN_EXTENSIONS
                    or path.name == '.env' or path.name.endswith('.local.json')):
                raise ValueError('runtime data, local configuration or binary in source inventory')
            if path.suffix == '.py':
                ast.parse(path.read_text(encoding='utf-8'), filename=str(relative))
            elif path.suffix in {'.json', '.uplugin'}:
                json.loads(path.read_text(encoding='utf-8'))
            elif path.suffix == '.svg':
                ET.fromstring(path.read_text(encoding='utf-8'))
            elif path.suffix == '.md':
                content = path.read_text(encoding='utf-8')
                for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)', content):
                    target = match.group(1).strip().strip('<>')
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    resolved = (path.parent / unquote(parsed.path)).resolve()
                    if not resolved.is_relative_to(root) or not resolved.exists():
                        raise ValueError('missing or external local link: ' + target)
        except (OSError, ValueError, SyntaxError, ET.ParseError) as error:
            failures.append(str(relative.as_posix()) + ': ' + str(error))
    plugin = root / 'Plugins' / 'AgentEmbodiment'
    try:
        record = json.loads((plugin / 'verification.json').read_text(encoding='utf-8'))
        expected = record['source_sha256']
        actual = {p.relative_to(plugin).as_posix()
                  for p in (plugin / 'Source').rglob('*') if p.is_file()}
        actual.add('AgentEmbodiment.uplugin')
        if actual != set(expected):
            failures.append('Native source inventory differs from its verification record')
        for name, digest in expected.items():
            target = (plugin / name).resolve()
            if not target.is_relative_to(plugin.resolve()):
                raise ValueError('unsafe native verification path')
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                failures.append('Native source needs renewed build verification: ' + name)
    except (OSError, ValueError, KeyError) as error:
        failures.append('Native verification: ' + str(error))
    return {'ok': not failures, 'source_files': len(files), 'failures': failures}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['ok'] else 1)
