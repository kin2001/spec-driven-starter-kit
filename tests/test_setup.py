import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.agents/skills/spec-team/scripts/setup.py'


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.kit = self.base / 'kit'
        self.project = self.base / 'project'
        self.project.mkdir()
        self.skill = self.kit / '.agents/skills/spec-team'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('kit')
        (self.kit / '.codex/agents').mkdir(parents=True)
        for role in ('spark', 'atlas', 'relay', 'muse', 'pixel', 'forge', 'lens', 'dock'):
            (self.kit / f'.codex/agents/{role}.toml').write_text('role')
        (self.kit / 'docs').mkdir()
        (self.kit / 'docs/MEMORY.md').write_text('initial memory')
        (self.kit / 'README.md').write_text('readme')
        (self.kit / 'AGENTS.md').write_text('agents')
        self.archive({'dep/SKILL.md': b'dep'})

    def archive(self, files):
        (self.skill / 'bundles').mkdir(exist_ok=True)
        p = self.skill / 'bundles/dep.zip'
        with zipfile.ZipFile(p, 'w') as z:
            for name, data in files.items():
                z.writestr(name, data)
        self.lock = {'schema_version': 1, 'families': [{'name': 'dep', 'repository': 'https://github.com/example/dep', 'revision': 'a' * 40, 'license': 'MIT', 'archive': 'bundles/dep.zip', 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'skills': {'dep': 'dep'}}]}
        self.save_lock()

    def save_lock(self):
        (self.skill / 'dependencies.lock.json').write_text(json.dumps(self.lock))

    def module(self):
        self.assertTrue(SCRIPT.is_file(), 'offline setup implementation is missing')
        spec = importlib.util.spec_from_file_location('kit_setup', SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_plan_apply_and_idempotence(self):
        m = self.module()
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertFalse(plan['conflicts'])
        self.assertEqual(list(self.project.iterdir()), [])
        m.apply_setup(plan)
        self.assertEqual((self.project / '.agents/skills/dep/SKILL.md').read_bytes(), b'dep')
        self.assertEqual(m.plan_setup(self.kit, self.project, [])['operations'], [])

    def test_installed_kit_license_preserves_product_license(self):
        m = self.module()
        (self.project / 'LICENSE').write_bytes(b'existing product license')
        m.apply_setup(m.plan_setup(ROOT, self.project, []))
        installed = self.project / '.agents/skills/spec-team/LICENSE'
        self.assertTrue(installed.is_file(), 'installed kit must retain its own MIT notice')
        self.assertEqual(installed.read_bytes(), (ROOT / 'LICENSE').read_bytes())
        self.assertEqual((self.project / 'LICENSE').read_bytes(), b'existing product license')

    def test_preserves_agents_memory_and_reuses_dependency(self):
        m = self.module()
        original = b'owner instructions\r\n'
        (self.project / 'AGENTS.md').write_bytes(original)
        (self.project / 'docs').mkdir()
        (self.project / 'docs/MEMORY.md').write_bytes(b'private memory')
        user = self.base / 'user-skills'
        (user / 'dep').mkdir(parents=True)
        (user / 'dep/SKILL.md').write_text('custom')
        plan = m.plan_setup(self.kit, self.project, [user])
        self.assertEqual(plan['reused'][0]['status'], 'present-unverified')
        m.apply_setup(plan)
        self.assertTrue((self.project / 'AGENTS.md').read_bytes().startswith(original))
        self.assertEqual((self.project / 'docs/MEMORY.md').read_bytes(), b'private memory')
        self.assertFalse((self.project / '.agents/skills/dep').exists())

    def test_existing_readme_and_consumer_content_do_not_propagate(self):
        m = self.module()
        (self.project / 'README.md').write_bytes(b'product readme')
        (self.skill / 'templates').mkdir()
        (self.skill / 'templates/memory.md').write_bytes(b'inert memory template')
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertFalse(plan['conflicts'])
        m.apply_setup(plan)
        self.assertEqual((self.project / 'README.md').read_bytes(), b'product readme')
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), m.POINTER)
        self.assertEqual((self.project / 'docs/MEMORY.md').read_bytes(), b'inert memory template')
        (self.project / 'AGENTS.md').write_bytes(b'private owner instructions' + m.POINTER)
        (self.project / 'docs/MEMORY.md').write_bytes(b'private consumer memory')
        (self.project / '.codex/agents/custom.toml').write_bytes(b'private custom role')
        private = ['.spec-team/local/environment.json', '.env.local', '.npmrc']
        for relative in private:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'FAKE_PRIVATE_SETUP_VALUE')
        other = self.base / 'other-project'
        second = m.plan_setup(self.project, other, [])
        self.assertFalse(second['conflicts'])
        m.apply_setup(second)
        self.assertEqual((other / 'AGENTS.md').read_bytes(), m.POINTER)
        self.assertEqual((other / 'docs/MEMORY.md').read_bytes(), b'inert memory template')
        self.assertFalse((other / 'README.md').exists())
        self.assertFalse((other / '.codex/agents/custom.toml').exists())
        for relative in private:
            self.assertFalse((other / relative).exists())
            self.assertEqual((self.project / relative).read_bytes(), b'FAKE_PRIVATE_SETUP_VALUE')

    def test_fresh_bootstrap_ignores_private_runtime_in_git(self):
        m = self.module()
        subprocess.run(['git', 'init', '--quiet', str(self.project)], check=True, capture_output=True)
        m.apply_setup(m.plan_setup(self.kit, self.project, []))
        for relative in ['.spec-team/run.json', '.superpowers/checkpoint', '.worktrees/worker/file']:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'private runtime')
            result = subprocess.run(['git', 'check-ignore', '--', relative], cwd=self.project, capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, f'{relative} is not ignored: {result.stdout} {result.stderr}')
        visible = subprocess.run(['git', 'check-ignore', '--', '.agents/skills/spec-team/SKILL.md'], cwd=self.project, capture_output=True)
        self.assertEqual(visible.returncode, 1)

    def test_existing_ignore_preserved_idempotent_and_not_propagated(self):
        m = self.module()
        original = b'# product rules\r\nnode_modules/\r\n!keep-me.txt'
        (self.project / '.gitignore').write_bytes(original)
        (self.kit / '.gitignore').write_bytes(b'private-source-rule')
        m.apply_setup(m.plan_setup(self.kit, self.project, []))
        installed = (self.project / '.gitignore').read_bytes()
        self.assertTrue(installed.startswith(original))
        self.assertIn(b'/.spec-team/', installed)
        self.assertNotIn(b'private-source-rule', installed)
        self.assertEqual(m.plan_setup(self.kit, self.project, [])['operations'], [])
        other = self.base / 'other'
        m.apply_setup(m.plan_setup(self.project, other, []))
        copied = (other / '.gitignore').read_bytes()
        self.assertNotIn(original, copied)
        self.assertIn(b'/.spec-team/', copied)

    def test_ignore_conflict_blocks_setup_and_append_rolls_back(self):
        m = self.module()
        ignore = self.project / '.gitignore'
        ignore.write_bytes(b'# spec-team:start\ncustom-conflicting-rules\n')
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertTrue(plan['conflicts'])
        with self.assertRaises(ValueError):
            m.apply_setup(plan)
        original = b'product-rules\r\n'
        ignore.write_bytes(original)
        (self.project / 'AGENTS.md').write_bytes(b'owner instructions')
        plan = m.plan_setup(self.kit, self.project, [])
        writer = m._write_new
        def fail_late(path, data):
            if path.name == 'MEMORY.md':
                self.assertNotEqual(ignore.read_bytes(), original)
                raise OSError('interrupt after managed appends')
            writer(path, data)
        with patch.object(m, '_write_new', fail_late):
            with self.assertRaises(OSError):
                m.apply_setup(plan)
        self.assertEqual(ignore.read_bytes(), original)
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), b'owner instructions')
        self.assertEqual(sorted(path.name for path in self.project.iterdir()), ['.gitignore', 'AGENTS.md'])

    def test_conflict_blocks_all_writes(self):
        m = self.module()
        (self.project / '.codex/agents').mkdir(parents=True)
        target = self.project / '.codex/agents/relay.toml'
        target.write_bytes(b'custom')
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertTrue(plan['conflicts'])
        with self.assertRaises(ValueError):
            m.apply_setup(plan)
        self.assertEqual(target.read_bytes(), b'custom')
        self.assertFalse((self.project / '.agents').exists())

    def test_corrupt_missing_and_unsafe_archives(self):
        m = self.module()
        for name in ['../escape', '/absolute', 'C:/drive', 'dep/a', 'dep/A']:
            with self.subTest(name=name):
                files = {name: b'x'}
                if name.startswith('dep/'):
                    files = {'dep/a': b'a', 'dep/A': b'A'}
                self.archive(files)
                self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        self.archive({'dep/SKILL.md': b'dep'})
        self.lock['families'][0]['sha256'] = '0' * 64
        self.save_lock()
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        (self.skill / 'bundles/dep.zip').unlink()
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])

    def test_link_archive(self):
        m = self.module()
        p = self.skill / 'bundles/dep.zip'
        with zipfile.ZipFile(p, 'w') as z:
            i = zipfile.ZipInfo('dep/SKILL.md')
            i.create_system = 3
            i.external_attr = 0o120777 << 16
            z.writestr(i, 'elsewhere')
        self.lock['families'][0]['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        self.save_lock()
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])

    def test_archive_directory_case_collision(self):
        m = self.module()
        self.archive({'dep/SKILL.md': b'dep', 'dep/Data/one': b'1', 'dep/data/two': b'2'})
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])

    def test_limits_duplicates_and_malformed_manifest(self):
        m = self.module()
        for payload in [{}, {'schema_version': 2, 'families': []}, {'schema_version': 1, 'families': [None]}, {'schema_version': 1, 'families': self.lock['families'] * 2}]:
            with self.subTest(payload=payload):
                (self.skill / 'dependencies.lock.json').write_text(json.dumps(payload))
                self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        self.save_lock()
        self.archive({'dep/SKILL.md': b'dep', **{f'dep/{n}': b'' for n in range(2001)}})
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        self.archive({'dep/SKILL.md': b'dep', 'dep/too-big': b'x' * (50 * 1024 * 1024)})
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])

    def test_missing_or_differing_existing_kit_skill_conflicts(self):
        m = self.module()
        (self.project / '.agents/skills/spec-team').mkdir(parents=True)
        path = self.project / '.agents/skills/spec-team/SKILL.md'
        path.write_bytes(b'custom spec-team')
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertTrue(plan['conflicts'])
        with self.assertRaises(ValueError):
            m.apply_setup(plan)
        self.assertEqual(path.read_bytes(), b'custom spec-team')

    def test_protected_home_and_overlap_rejected(self):
        m = self.module()
        for target in [Path.home(), Path.home() / '.agents/skills/installed', self.kit / 'nested']:
            with self.subTest(target=target):
                self.assertTrue(m.plan_setup(self.kit, target, [])['conflicts'])

    def test_explicit_managed_worktree_allowed_but_adjacent_global_storage_rejected(self):
        m = self.module()
        home = self.base / 'fake-home'
        home.mkdir()
        with patch.object(m.Path, 'home', return_value=home):
            target = home / '.codex/worktrees/example/project'
            plan = m.plan_setup(self.kit, target, [])
            self.assertFalse(plan['conflicts'])
            m.apply_setup(plan)
            self.assertTrue((target / '.agents/skills/spec-team/SKILL.md').is_file())
            for name in ['.codex', '.codex/skills/target', '.codex/agents/target', '.codex/plugins/target', '.codex/memories/target', '.agents', '.agents/skills/target', '.claude', '.claude/skills/target']:
                with self.subTest(name=name):
                    self.assertTrue(m.plan_setup(self.kit, home / name, [])['conflicts'])

    def test_runtime_imports_no_network_or_process_module(self):
        import ast
        tree = ast.parse(SCRIPT.read_text())
        imports = {n.names[0].name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
        self.assertFalse(imports & {'socket', 'urllib', 'requests', 'subprocess'})

    def test_incomplete_source_or_memory_directory_rejected(self):
        m = self.module()
        (self.kit / '.codex/agents/lens.toml').unlink()
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        (self.kit / '.codex/agents/lens.toml').write_text('role')
        (self.project / 'docs/MEMORY.md').mkdir(parents=True)
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])

    def test_shipped_bundles_install_and_ui_search_offline(self):
        m = self.module()
        shipped = ROOT / '.agents/skills/spec-team'
        shutil.copyfile(shipped / 'dependencies.lock.json', self.skill / 'dependencies.lock.json')
        shutil.copytree(shipped / 'bundles', self.skill / 'bundles', dirs_exist_ok=True)
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertFalse(plan['conflicts'], plan['conflicts'])
        m.apply_setup(plan)
        rerun = m.plan_setup(self.kit, self.project, [])
        self.assertEqual(rerun['operations'], [])
        self.assertEqual(len(rerun['reused']), 22)
        self.assertTrue(all(s['status'] == 'matching-pin' for s in rerun['reused']))
        self.assertTrue((self.project / '.agents/skills/ponytail-gain/benchmarks/results/2026-10-07-agentic.md').is_file())
        search = self.project / '.agents/skills/ui-ux-pro-max/scripts/search.py'
        runner = 'import runpy,sys; sys.path.insert(0,str(__import__("pathlib").Path(sys.argv[1]).parent)); sys.addaudithook(lambda event,args: (_ for _ in ()).throw(RuntimeError("network forbidden")) if event.startswith("socket.") else None); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")'
        for arguments, expected in [(['keyboard focus visible', '--domain', 'ux'], 'Focus'), (['restaurant', '--design-system'], 'DESIGN SYSTEM'), (['responsive layout', '--stack', 'nextjs'], 'nextjs')]:
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', runner, str(search), *arguments], cwd=self.base, capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(expected.lower(), result.stdout.lower())

    def test_stale_or_injected_plan_is_rejected(self):
        m = self.module()
        plan = m.plan_setup(self.kit, self.project, [])
        plan['operations'][0]['path'] = str(self.base / 'outside')
        with self.assertRaises(ValueError):
            m.apply_setup(plan)
        self.assertFalse((self.base / 'outside').exists())
        plan = m.plan_setup(self.kit, self.project, [])
        (self.project / '.codex/agents').mkdir(parents=True)
        (self.project / '.codex/agents/relay.toml').write_text('new owner work')
        with self.assertRaises(ValueError):
            m.apply_setup(plan)

    def test_partial_copy_rolls_back_new_paths_and_agents(self):
        m = self.module()
        (self.project / 'AGENTS.md').write_bytes(b'owner')
        plan = m.plan_setup(self.kit, self.project, [])
        original = m._write_new
        count = 0
        def fail(path, data):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError('interrupted')
            return original(path, data)
        with patch.object(m, '_write_new', fail):
            with self.assertRaises(OSError):
                m.apply_setup(plan)
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['AGENTS.md'])
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), b'owner')

    def test_redirected_destination(self):
        m = self.module()
        outside = self.base / 'outside'
        outside.mkdir()
        link = self.project / '.agents'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if sys.platform == 'win32':
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
            else:
                raise
        self.assertTrue(m.plan_setup(self.kit, self.project, [])['conflicts'])
        self.assertEqual(list(outside.iterdir()), [])

    def test_hardlinked_agents_rejected_without_touching_external_bytes(self):
        m = self.module()
        external = self.base / 'external-instructions'
        external.write_bytes(b'external owner instructions')
        os.link(external, self.project / 'AGENTS.md')
        plan = m.plan_setup(self.kit, self.project, [])
        self.assertTrue(plan['conflicts'])
        with self.assertRaises(ValueError):
            m.apply_setup(plan)
        self.assertEqual(external.read_bytes(), b'external owner instructions')

    def test_cli_plan_does_not_write(self):
        self.module()
        local = self.skill / 'scripts/setup.py'
        local.parent.mkdir()
        local.write_bytes(SCRIPT.read_bytes())
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(local), '--project', str(self.project), '--skills-root', str(self.base / 'empty')], capture_output=True, encoding='utf-8')
        self.assertIn('SPEC_TEAM_SETUP_PLANNED', result.stdout)
        self.assertEqual(list(self.project.iterdir()), [])
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(local), '--project', str(self.project), '--skills-root', str(self.base / 'empty'), '--apply'], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SPEC_TEAM_SETUP_APPLIED', result.stdout)
        self.assertTrue((self.project / '.agents/skills/spec-team/scripts/setup.py').is_file())


if __name__ == '__main__':
    unittest.main()
