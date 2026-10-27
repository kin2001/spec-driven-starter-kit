import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / '.agents/skills/spec-team/scripts'


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with mock.patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            spec = importlib.util.spec_from_file_location('operations', SCRIPTS / 'operations.py')
            self.o = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.o)
        self.source = self.root / 'artifacts'; self.source.mkdir()
        (self.source / 'one.txt').write_bytes(b'one')
        (self.source / 'nested').mkdir()
        (self.source / 'nested/two.txt').write_bytes(b'two')
        self.controller = self.root / 'controller'; self.controller.mkdir()
        import uuid
        with mock.patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            from ownership import claim_owner
        self.run = str(uuid.uuid4())
        self.claim = claim_owner(self.controller, 'relay', self.run)
        self.destination = self.controller / '.spec-team/local/preserved/task'

    def preserve(self, record):
        return self.o.preserve(self.source, self.destination, record, self.controller, self.claim['claim_id'], self.run)

    def test_snapshot_and_preserve_exact_content_without_source_changes(self):
        record = self.o.snapshot(self.source)
        self.assertEqual(2, len(record['files']))
        self.assertEqual(6, sum(f['size'] for f in record['files']))
        self.preserve(record)
        self.o.verify(self.destination, record, relocated=True)
        self.o.verify(self.source, record)
        self.assertEqual(b'two', (self.destination / 'nested/two.txt').read_bytes())
        with self.assertRaises(ValueError): self.preserve(record)
        with self.assertRaises(ValueError): self.o.verify(self.destination, record)

    def test_drift_and_unsafe_manifest_rejected_before_copy(self):
        original = self.o.snapshot(self.source)
        for path in ('../escape', '/absolute', 'nested/../../escape'):
            bad = copy.deepcopy(original); bad['files'][0]['path'] = path
            with self.assertRaises(ValueError): self.preserve(bad)
        bad = copy.deepcopy(original); bad['files'].append(bad['files'][0])
        with self.assertRaises(ValueError): self.preserve(bad)
        (self.source / 'one.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.preserve(original)
        self.assertFalse(self.destination.exists())

    def test_wrong_claim_and_destination_boundary_rejected(self):
        record = self.o.snapshot(self.source)
        import uuid
        with self.assertRaises(ValueError):
            self.o.preserve(self.source, self.destination, record, self.controller, str(uuid.uuid4()), self.run)
        self.destination = self.source / 'recursive-copy'
        with self.assertRaises(ValueError): self.preserve(record)
        self.destination = self.root / 'outside'
        with self.assertRaises(ValueError): self.preserve(record)

    def test_partial_failure_keeps_source_and_partial_destination(self):
        record = self.o.snapshot(self.source)
        with mock.patch.object(self.o.shutil, 'copyfileobj', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.preserve(record)
        self.o.verify(self.source, record)
        self.assertTrue(self.destination.exists())
        with self.assertRaises(ValueError): self.preserve(record)

    def test_changed_during_copy_not_reported_as_pass(self):
        record = self.o.snapshot(self.source); real = self.o.shutil.copyfileobj
        def changing(src, dest):
            result = real(src, dest)
            (self.source / 'one.txt').write_bytes(b'changed')
            return result
        with mock.patch.object(self.o.shutil, 'copyfileobj', side_effect=changing):
            with self.assertRaises(ValueError): self.preserve(record)
        self.assertTrue(self.destination.exists())

    def test_compact_cli_receipt_is_exclusive_and_failure_visible(self):
        receipt = self.root / 'inventory.json'
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, self.o.main(['snapshot', '--source', str(self.source), '--receipt', str(receipt)]))
        self.assertLess(len(output.getvalue()), 500)
        self.assertIn('OPS_SNAPSHOT', output.getvalue())
        original = receipt.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, self.o.main(['snapshot', '--source', str(self.source), '--receipt', str(receipt)]))
        self.assertEqual(original, receipt.read_bytes())
        self.assertEqual(2, len(json.loads(original)['files']))

    def test_links_and_repository_metadata_rejected(self):
        record = self.o.snapshot(self.source)
        link = self.source / 'alias'
        try: os.link(self.source / 'one.txt', link)
        except OSError: self.skipTest('hardlinks unavailable')
        with self.assertRaises(ValueError): self.o.snapshot(self.source)
        link.unlink()
        (self.source / '.git').mkdir()
        with self.assertRaises(ValueError): self.o.snapshot(self.source)

    def test_unreadable_subtree_never_becomes_complete_inventory(self):
        record = self.o.snapshot(self.source); scandir = self.o.os.scandir
        def denied(path):
            if Path(path).resolve() == (self.source / 'nested').resolve(): raise PermissionError('unreadable subtree')
            return scandir(path)
        with mock.patch.object(self.o.os, 'scandir', side_effect=denied):
            with self.assertRaises(OSError): self.o.snapshot(self.source)
            with self.assertRaises(OSError): self.o.verify(self.source, record)
            with self.assertRaises(OSError): self.preserve(record)
        self.assertFalse(self.destination.exists())

    def test_git_metadata_root_ancestry_and_case_variants_rejected(self):
        metadata = self.source / '.GIT'; metadata.mkdir()
        objects = metadata / 'objects'; objects.mkdir()
        (objects / 'config').write_bytes(b'metadata')
        for source in (self.source, metadata, objects):
            with self.subTest(source=source):
                with self.assertRaises(ValueError): self.o.snapshot(source)

    @unittest.skipUnless(os.name == 'nt', 'Windows short-path alias regression')
    def test_preservation_accepts_canonical_destination_with_short_controller_path(self):
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(str(self.controller), buffer, len(buffer))
        if not result or Path(buffer.value) == self.controller.resolve():
            self.skipTest('short path alias unavailable')
        alias = Path(buffer.value)
        destination = alias / '.spec-team/local/preserved/alias-test'
        self.o.preserve(self.source, destination, self.o.snapshot(self.source), alias, self.claim['claim_id'], self.run)
        self.assertTrue(destination.is_dir())


if __name__ == '__main__': unittest.main()
