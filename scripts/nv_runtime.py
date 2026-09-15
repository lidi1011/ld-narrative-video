"""Host-independent subprocess commands; never interpolate through a shell."""
import json
import os
import shutil
from pathlib import Path

def executable(name, env=None):
    value = os.environ.get(env) if env else None
    resolved = shutil.which(value or name)
    if not resolved:
        raise ValueError(f"Missing {name}; install it or set {env or 'PATH'}")
    return resolved

def hyperframes_command(root, explicit=None):
    root = Path(root).resolve()
    if explicit:
        entry = Path(explicit).expanduser().resolve()
        if entry.is_dir():
            package = entry / 'package.json'
        elif entry.suffix.lower() in {'.mjs', '.cjs', '.js'}:
            if not entry.is_file():
                raise ValueError('HyperFrames JavaScript entry does not exist')
            return [executable('node', 'NARRATIVE_VIDEO_NODE'), str(entry)]
        else:
            # Unix symlinks resolve to .mjs above; npm Windows shims live in .bin.
            package = entry.parent.parent / 'hyperframes/package.json'
    else:
        package = root / 'node_modules/hyperframes/package.json'
    if not package.is_file():
        raise ValueError('Run npm ci in video/, or pass --hyperframes with a package directory or JS entry')
    data = json.loads(package.read_text(encoding='utf-8'))
    if data.get('name') != 'hyperframes' or data.get('version') != '0.8.35':
        raise ValueError('Expected pinned HyperFrames 0.8.35')
    relative = data['bin']['hyperframes']
    entry = (package.parent / relative).resolve()
    if not entry.is_relative_to(package.parent.resolve()) or not entry.is_file():
        raise ValueError('Invalid HyperFrames bin entry')
    return [executable('node', 'NARRATIVE_VIDEO_NODE'), str(entry)]
