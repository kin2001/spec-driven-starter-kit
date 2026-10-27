"""Publish/check a local context cache. Matching bytes never prove live authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from ownership import check_owner
from setup import _check_path
from validate import validate_run

SECTIONS = ('Last completed delivery', 'Relevant contracts and decisions', 'Next task',
            'Unresolved carryover', 'Ownership at checkpoint', 'Verification boundary', 'Evidence')
PREFIX = '<!-- spec-team-handoff: '
LIMIT = 16384


def _read(path, limit=LIMIT):
    _check_path(path)
    if limit is not None and path.stat().st_size > limit:
        raise ValueError('handoff input: exceeds 16 KiB')
    return path.read_bytes()


def _state(root):
    root = Path(os.path.abspath(root))
    _check_path(root)
    root = root.resolve(strict=True)
    raw = _read(root / '.spec-team/run.json', limit=None)
    run = json.loads(raw)
    if validate_run(run, root) or not run.get('run_id'):
        raise ValueError('run: invalid binding or approved bytes; reconcile normally')
    return root, raw, run


def _body(text):
    for section in SECTIONS:
        match = re.search(r'^## ' + re.escape(section) + r'\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        if not match or not match[1].strip():
            raise ValueError('handoff: missing/nonempty section required: ' + section)
    if text.startswith(PREFIX):
        raise ValueError('source: use body only, not an old metadata header')
    return text


def _binding(root, raw, run):
    return {'schema_version': 1, 'controller_root': str(root),
            'repository_id': run['repository_id'], 'run_id': run['run_id'],
            'run_sha256': hashlib.sha256(raw).hexdigest()}


def check(root):
    root, raw, run = _state(root)
    text = _read(root / '.spec-team/HANDOFF.md').decode('utf-8')
    first, body = text.split('\n', 1)
    if not first.startswith(PREFIX) or not first.endswith(' -->'):
        raise ValueError('handoff: malformed binding')
    binding = json.loads(first[len(PREFIX):-4])
    if binding != _binding(root, raw, run):
        raise ValueError('handoff: identity or run changed; reconcile affected context')
    _body(body)
    return binding


def publish(root, claim_id, run_id, source):
    root, raw, run = _state(root)
    check_owner(root, claim_id, run_id)
    if run['owner_claim_id'] != claim_id or run['run_id'] != run_id:
        raise ValueError('run: current owner mismatch')
    body = _body(_read(Path(source)).decode('utf-8'))
    data = (PREFIX + json.dumps(_binding(root, raw, run), ensure_ascii=True) + ' -->\n' + body).encode('utf-8')
    if len(data) > LIMIT:
        raise ValueError('handoff: exceeds 16 KiB')
    target = root / '.spec-team/HANDOFF.md'
    _check_path(target)
    old = _read(target) if target.exists() else None
    if old is not None:
        archive = root / '.spec-team/reports/handoffs' / (hashlib.sha256(old).hexdigest() + '.md')
        _check_path(archive)
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            if _read(archive) != old: raise ValueError('handoff archive: content mismatch')
        else:
            with archive.open('xb') as stream:
                stream.write(old)
                stream.flush()
                os.fsync(stream.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        check_owner(root, claim_id, run_id)
        _check_path(target)
        if _read(root / '.spec-team/run.json', limit=None) != raw or (target.read_bytes() if target.exists() else None) != old:
            raise ValueError('handoff: state changed during publication; reconcile')
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists(): temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('check', 'publish'):
        command = sub.add_parser(action)
        command.add_argument('--root', type=Path, required=True)
        if action == 'publish':
            command.add_argument('--claim-id', required=True)
            command.add_argument('--run-id', required=True)
            command.add_argument('--source', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'publish': publish(args.root, args.claim_id, args.run_id, args.source)
        else: check(args.root)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print('HANDOFF_RECONCILE: missing, stale, unsafe or inconsistent local context; use normal reconciliation')
        return 1
    print('HANDOFF_PUBLISHED' if args.action == 'publish' else 'HANDOFF_BOUND: local run bytes only; check current ownership, target issue and relevant Git state')
    return 0


if __name__ == '__main__': raise SystemExit(main())
