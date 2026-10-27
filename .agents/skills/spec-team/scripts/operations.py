"""Bounded receipts for local inventory and preservation; no move/delete/merge authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from ownership import check_owner
from setup import _check_path, _safe_path


def _directory(path):
    path = Path(os.path.abspath(path))
    _check_path(path)
    if not path.is_dir(): raise ValueError('source: expected directory')
    path = path.resolve(strict=True)
    if any(part.casefold() == '.git' for part in path.parts):
        raise ValueError('source: select artifacts, not repository metadata')
    return path


def snapshot(source):
    source = _directory(source)
    files = []
    def unreadable(error): raise error
    for folder, directories, names in os.walk(source, followlinks=False, onerror=unreadable):
        for name in sorted(directories + names):
            path = Path(folder) / name
            if name.casefold() == '.git': raise ValueError('source: select artifacts, not repository metadata')
            _check_path(path)
            if path.is_dir(): continue
            before = path.stat()
            with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            _check_path(path)
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('source: changed during inventory')
            files.append({'path': path.relative_to(source).as_posix(), 'size': after.st_size, 'sha256': digest})
    return {'schema_version': 1, 'source': str(source), 'files': sorted(files, key=lambda f: f['path'])}


def _record(record):
    if not isinstance(record, dict) or set(record) != {'schema_version', 'source', 'files'} or type(record['schema_version']) is not int or record['schema_version'] != 1:
        raise ValueError('receipt: invalid shape')
    if not isinstance(record['source'], str) or not Path(record['source']).is_absolute() or not isinstance(record['files'], list):
        raise ValueError('receipt: invalid source/files')
    seen = set()
    for item in record['files']:
        if not isinstance(item, dict) or set(item) != {'path', 'size', 'sha256'}: raise ValueError('receipt: invalid entry')
        path = str(_safe_path(item['path']))
        key = os.path.normcase(path)
        if key in seen or any(part.casefold() == '.git' for part in Path(path).parts) or type(item['size']) is not int or item['size'] < 0 or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('receipt: duplicate or invalid entry')
        seen.add(key)
    return sorted(record['files'], key=lambda f: f['path'])


def verify(source, record, relocated=False):
    files = _record(record)
    current = snapshot(source)
    if not relocated and current['source'] != record['source']: raise ValueError('receipt: wrong source')
    if current['files'] != files: raise ValueError('receipt: file inventory changed')
    return current


def preserve(source, destination, record, controller_root, claim_id, run_id):
    controller = _directory(controller_root)
    def owner(): return check_owner(controller, claim_id, run_id)
    owner()
    source = _directory(source)
    destination = Path(os.path.abspath(destination)); _check_path(destination)
    destination = destination.resolve()
    allowed = controller / '.spec-team/local/preserved'
    if allowed not in destination.parents or source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('destination: outside preserved storage or overlaps source')
    if destination.exists(): raise ValueError('destination: must be new; reconcile partial copies')
    verify(source, record)
    destination.mkdir(parents=True, exist_ok=False)
    # Preserve partial copies on failure; never delete evidence or retry over existing bytes.
    for item in _record(record):
        owner()
        src = source / item['path']; dst = destination / item['path']
        _check_path(src); _check_path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists(): raise ValueError('destination: appeared during preservation')
        with src.open('rb') as incoming, dst.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush(); os.fsync(outgoing.fileno())
    verify(source, record)
    result = verify(destination, record, relocated=True)
    owner()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('snapshot', 'check', 'preserve'):
        command = sub.add_parser(action)
        command.add_argument('--source', required=True, type=Path)
        command.add_argument('--receipt', required=True, type=Path)
        if action == 'check': command.add_argument('--relocated', action='store_true')
        if action == 'preserve':
            command.add_argument('--destination', required=True, type=Path)
            command.add_argument('--controller-root', required=True, type=Path)
            command.add_argument('--claim-id', required=True)
            command.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    try:
        _check_path(args.receipt)
        if args.action == 'snapshot':
            source = _directory(args.source)
            receipt = Path(os.path.abspath(args.receipt))
            if source == receipt or source in receipt.parents: raise ValueError('receipt: must be outside inventoried directory')
            result = snapshot(source)
            receipt.parent.mkdir(parents=True, exist_ok=True)
            with receipt.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=True)
                stream.flush(); os.fsync(stream.fileno())
        else:
            record = json.loads(args.receipt.read_text(encoding='utf-8'))
            result = verify(args.source, record, args.relocated) if args.action == 'check' else preserve(args.source, args.destination, record, args.controller_root, args.claim_id, args.run_id)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print('OPS_RECONCILE: invalid input, changed files or unavailable storage; preserve source/partial evidence and inspect')
        return 1
    print('OPS_' + args.action.upper() + ' ' + json.dumps({'files': len(result['files']), 'bytes': sum(f['size'] for f in result['files'])}) + '; local bytes only, no cleanup/merge permission')
    return 0


if __name__ == '__main__': raise SystemExit(main())
