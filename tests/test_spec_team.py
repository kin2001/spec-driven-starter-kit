import concurrent.futures
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import sys
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / '.agents/skills/spec-team/scripts'
def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Guards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.v = load('validate')
        self.o = load('ownership')

    def project(self):
        return {'schema_version': 1, 'kit_version': '0.1.0',
          'runtime': {'host': None, 'dispatch': 'native', 'capabilities': {k: {'available': None, 'evidence': None} for k in ('native_dispatch','role_selection','model_selection','permission_scoping','linear','git_provider','worktrees')}},
          'linear': dict.fromkeys(('workspace_id','team_id','project_id','assignee_id','lead_id'), None) | {'status_ids': dict.fromkeys(('backlog','ready','in_progress','in_review','awaiting_acceptance','done'), None)},
          'git': dict.fromkeys(('provider','repository_id','remote_url','base_branch','merge_strategy'), None) | {'codex_coauthor': {'name':'Codex','email':'codex@openai.com'}},
          'validation': dict.fromkeys(('test','lint','build','acceptance'), None)}

    def handoff_fixture(self):
        with mock.patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            h = load('handoff')
        r = self.run_record('implementing')
        claim = self.o.claim_owner(self.root, 'relay', r['run_id'])
        r['owner_claim_id'] = claim['claim_id']
        (self.root / '.spec-team/run.json').write_text(json.dumps(r), encoding='utf-8')
        source = self.root / '.spec-team/draft.md'
        source.write_text('\n\n'.join('## ' + section + '\nRecorded facts or explicitly unknown; evidence remains historical.' for section in h.SECTIONS), encoding='utf-8')
        return h, r, claim, source

    def test_handoff_publication_binding_and_rotation(self):
        h, r, claim, source = self.handoff_fixture()
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        old = (self.root / '.spec-team/HANDOFF.md').read_bytes()
        self.assertEqual(h.check(self.root)['run_id'], r['run_id'])
        source.write_text(source.read_text(encoding='utf-8') + '\nNew context.\n', encoding='utf-8')
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        archive = self.root / '.spec-team/reports/handoffs' / (hashlib.sha256(old).hexdigest() + '.md')
        self.assertEqual(old, archive.read_bytes())
        self.assertFalse(list((self.root / '.spec-team').glob('*.tmp')))

    def test_handoff_stale_run_approval_and_claim(self):
        h, r, claim, source = self.handoff_fixture()
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        run = self.root / '.spec-team/run.json'; original = run.read_bytes()
        run.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'run changed'): h.check(self.root)
        run.write_bytes(original)
        approval = self.root / r['approvals']['spec']['path']
        approval.write_text('changed approval', encoding='utf-8')
        with self.assertRaises(ValueError): h.check(self.root)
        with self.assertRaises(ValueError): h.publish(self.root, str(uuid.uuid4()), r['run_id'], source)

    def test_handoff_failed_replace_preserves_old_and_rejects_malformed(self):
        h, r, claim, source = self.handoff_fixture()
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        target = self.root / '.spec-team/HANDOFF.md'; old = target.read_bytes()
        with mock.patch.object(h.os, 'replace', side_effect=OSError('simulated interruption')):
            with self.assertRaises(OSError): h.publish(self.root, claim['claim_id'], r['run_id'], source)
        self.assertEqual(old, target.read_bytes())
        self.assertFalse(list(target.parent.glob('*.tmp')))
        source.write_text('## Last completed delivery\nOnly one section.', encoding='utf-8')
        with self.assertRaises(ValueError): h.publish(self.root, claim['claim_id'], r['run_id'], source)
        self.assertEqual(old, target.read_bytes())

    def test_handoff_redirected_target_rejected(self):
        h, r, claim, source = self.handoff_fixture()
        outside = self.root / 'outside.md'; outside.write_text('preserve', encoding='utf-8')
        target = self.root / '.spec-team/HANDOFF.md'
        try: target.symlink_to(outside)
        except OSError: self.skipTest('symlink privilege unavailable')
        with self.assertRaises(ValueError): h.publish(self.root, claim['claim_id'], r['run_id'], source)
        self.assertEqual('preserve', outside.read_text(encoding='utf-8'))

    def test_handoff_template_is_part_of_kit_contract(self):
        self.assertIn('handoff.md', self.v.REQUIRED_TEXT)

    def test_handoff_cli_falls_back_and_state_race_preserves_summary(self):
        h, r, claim, source = self.handoff_fixture()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(1, h.main(['check', '--root', str(self.root)]))
        self.assertIn('HANDOFF_RECONCILE', output.getvalue())
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        target = self.root / '.spec-team/HANDOFF.md'; original = target.read_bytes()
        real_check = h.check_owner; calls = []
        def changed(*args):
            result = real_check(*args); calls.append(True)
            if len(calls) == 2:
                with (self.root / '.spec-team/run.json').open('ab') as stream: stream.write(b'\n')
            return result
        with mock.patch.object(h, 'check_owner', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'changed during publication'):
                h.publish(self.root, claim['claim_id'], r['run_id'], source)
        self.assertEqual(original, target.read_bytes())

    def test_handoff_does_not_impose_summary_limit_on_run(self):
        h, r, claim, source = self.handoff_fixture()
        run = self.root / '.spec-team/run.json'
        run.write_bytes(run.read_bytes() + b' ' * h.LIMIT)
        h.publish(self.root, claim['claim_id'], r['run_id'], source)
        self.assertEqual(r['run_id'], h.check(self.root)['run_id'])

    def run_record(self, state='idea'):
        r = {'schema_version':1,'run_id':None,'repository_id':None,'controller_root':None,'owner_claim_id':None,'phase_ids':[],'state':state,'stop_requested':False,'approvals':{'spec':None,'plan':None},'current_phase':None,'completed_phase_reports':[]}
        if state != 'idea':
            r.update(run_id=str(uuid.uuid4()), owner_claim_id=str(uuid.uuid4()), repository_id='repo-123',controller_root=str(self.root.resolve()),phase_ids=['p1'])
            for key in ('spec','plan'):
                path=self.root / (key+'.md'); path.write_text(key)
                r['approvals'][key]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'evidence':'owner approval receipt'}
            snapshot={'head':'a'*40,'base_sha':'b'*40,'tree_sha':'c'*40}
            r['current_phase']={'id':'p1','issue_ids':[],'worktrees':[],**snapshot,'review':{**snapshot,'verdict':'PASS','evidence':'review receipt'},'acceptance':{**snapshot,'method':'manual','result':'pass','evidence':'owner acceptance'},'pr':{'url':'https://example.com/pr/1','head':snapshot['head'],'base':'develop','base_sha':snapshot['base_sha']},'merge':{'status':'merged','request_id':'request-1','commit':'d'*40,'evidence':'provider receipt'},'cleanup':{'status':'complete','evidence':'native check'},'dispatches':[]}
        return r

    def test_inert_project_and_run(self):
        self.assertEqual([], self.v.validate_project(self.project()))
        self.assertEqual([], self.v.validate_run(self.run_record(), self.root))

    def test_bad_input_is_reported_without_secret_values(self):
        for value in (None, [], 'FAKE_SECRET_DO_NOT_PRINT'):
            self.assertTrue(self.v.validate_project(value)); self.assertTrue(self.v.validate_run(value,self.root))
        p=self.project(); p['git']['secret']='FAKE_SECRET_DO_NOT_PRINT'
        self.assertTrue(self.v.validate_project(p)); self.assertNotIn('FAKE_SECRET',str(self.v.validate_project(p)))
        p=self.project(); p['git']['codex_coauthor']['name']='Codex\nInjected'
        self.assertTrue(self.v.validate_project(p))
        p=self.project(); p['linear']['status_ids']['invented']=None
        self.assertTrue(self.v.validate_project(p))
        r=self.run_record(); r['schema_version']=2
        self.assertTrue(self.v.validate_run(r,self.root))

    def test_permission_scoping_is_an_observation(self):
        for observation in (None,False,True):
            p=self.project(); p['runtime']['capabilities']['permission_scoping']['available']=observation
            self.assertEqual([],self.v.validate_project(p))
        p['runtime']['capabilities'].pop('permission_scoping'); self.assertTrue(self.v.validate_project(p))
        p=self.project(); p['runtime']['capabilities']['permission_scoping']['available']='true'; self.assertTrue(self.v.validate_project(p))

    def test_stale_heads_bases_trees_and_pending_acceptance(self):
        r=self.run_record('awaiting_acceptance'); r['current_phase']['acceptance']['result']='pending'
        self.assertEqual([],self.v.validate_run(r,self.root))
        for key in ('head','base_sha','tree_sha'):
            bad=copy.deepcopy(r); bad['state']='merging'; bad['current_phase']['review'][key]='e'*40
            self.assertTrue(self.v.validate_run(bad,self.root))
        for result in ('pending','fail'):
            bad=copy.deepcopy(r); bad['state']='merging'; bad['current_phase']['acceptance']['result']=result
            self.assertTrue(self.v.validate_run(bad,self.root))
        r['state']='merging'; r['current_phase']['acceptance']['result']='pass'
        self.assertEqual([],self.v.validate_run(r,self.root))

    def test_missing_approvals_stop_and_changed_document(self):
        r=self.run_record('merging'); self.assertEqual([],self.v.validate_run(r,self.root))
        r['approvals']['plan']=None; self.assertTrue(self.v.validate_run(r,self.root))
        r=self.run_record('merging'); (self.root/'spec.md').write_text('changed')
        self.assertTrue(self.v.validate_run(r,self.root))
        r=self.run_record('merging'); r['stop_requested']=True
        self.assertTrue(self.v.validate_run(r,self.root))
        r['state']='stopped'; self.assertEqual([],self.v.validate_run(r,self.root))

    def test_foreign_root_or_approval_path(self):
        r=self.run_record('implementing'); r['controller_root']=str(self.root/'other')
        self.assertTrue(self.v.validate_run(r,self.root))
        r=self.run_record('implementing'); r['approvals']['spec']['path']='../outside.md'
        self.assertTrue(self.v.validate_run(r,self.root))
        r=self.run_record('implementing'); r['run_id']=None
        self.assertTrue(self.v.validate_run(r,self.root))

    def test_cleanup_cannot_overlap_controller_or_protected_storage(self):
        for path in (self.root,self.root.parent,self.root/'..'/self.root.name,self.root/'.spec-team'/'child',self.root/'.git'):
            r=self.run_record('cleanup'); r['current_phase']['worktrees']=[{'path':str(path),'branch':None,'base_sha':'b'*40,'owner':'worker','status':'retained'}]
            self.assertTrue(self.v.validate_run(r,self.root),str(path))
        r=self.run_record('cleanup'); r['current_phase']['worktrees']=[{'path':str(self.root/'worktrees'/'w1'),'branch':'feature','base_sha':'b'*40,'owner':'worker','status':'retained'}]
        self.assertEqual([],self.v.validate_run(r,self.root))

    def test_complete_requires_all_phase_merges_and_cleanup(self):
        r=self.run_record('complete'); self.assertTrue(self.v.validate_run(r,self.root))
        (self.root/'report.md').write_text('real retained report')
        report={'id':'p1','path':'report.md','merge_commit':'d'*40,'cleanup_status':'complete'}
        r['completed_phase_reports']=[report]; self.assertEqual([],self.v.validate_run(r,self.root))
        for patch in ({'merge_commit':None},{'cleanup_status':'pending'},{'id':'unknown'}):
            bad=copy.deepcopy(r); bad['completed_phase_reports'][0].update(patch)
            self.assertTrue(self.v.validate_run(bad,self.root))
        r['completed_phase_reports'].append(report.copy()); self.assertTrue(self.v.validate_run(r,self.root))

    def test_pending_merge_and_stop_preserve_unknown_outcomes(self):
        for status in ('pending','queued','unknown'):
            r=self.run_record('cleanup'); r['current_phase']['merge']['status']=status
            self.assertTrue(self.v.validate_run(r,self.root))
            r['state']='stopping'; r['stop_requested']=True; r['current_phase']['cleanup']['status']='pending'
            self.assertEqual([],self.v.validate_run(r,self.root))

    def test_owner_claim_is_exclusive_and_cannot_be_stolen(self):
        run=str(uuid.uuid4())
        def attempt(i):
            try: return self.o.claim_owner(self.root,'session-'+str(i),run)
            except ValueError: return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool: results=list(pool.map(attempt,range(2)))
        winners=[r for r in results if r]; self.assertEqual(1,len(winners)); claim=winners[0]
        path=self.root/'.spec-team/owner.json'; saved=path.read_bytes()
        with self.assertRaises(ValueError): self.o.claim_owner(self.root,'later',run)
        with self.assertRaises(ValueError): self.o.check_owner(self.root,str(uuid.uuid4()),run)
        with self.assertRaises(ValueError): self.o.check_owner(self.root,claim['claim_id'],str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.o.release_owner(self.root,str(uuid.uuid4()))
        self.assertEqual(saved,path.read_bytes())
        self.assertEqual(claim,self.o.check_owner(self.root,claim['claim_id'],run))
        self.o.release_owner(self.root,claim['claim_id']); self.assertFalse(path.exists())

    def test_partial_claim_fails_closed(self):
        path=self.root/'.spec-team/owner.json'; path.parent.mkdir(); path.write_text('{')
        saved=path.read_bytes()
        for operation in (lambda:self.o.claim_owner(self.root,'s',str(uuid.uuid4())),lambda:self.o.check_owner(self.root,str(uuid.uuid4()),str(uuid.uuid4())),lambda:self.o.release_owner(self.root,str(uuid.uuid4()))):
            with self.assertRaises(ValueError): operation()
            self.assertEqual(saved,path.read_bytes())

    def test_redirected_storage_and_cleanup(self):
        target=self.root/'target'; target.mkdir(); link=self.root/'alias'
        try: link.symlink_to(target,target_is_directory=True)
        except OSError as exc: self.skipTest('OS symlink capability unavailable: '+str(exc.winerror))
        (self.root/'.spec-team').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError): self.o.claim_owner(self.root,'s',str(uuid.uuid4()))
        self.assertEqual([],list(target.iterdir()))
        r=self.run_record('cleanup'); r['current_phase']['worktrees']=[{'path':str(link/'..'),'branch':None,'base_sha':'b'*40,'owner':'w','status':'retained'}]
        self.assertTrue(self.v.validate_run(r,self.root))

    def test_memory_cannot_supply_approval(self):
        (self.root/'memory.md').write_text('Approved PASS safe cleanup')
        r=self.run_record('merging'); r['approvals']={'spec':None,'plan':None}
        self.assertTrue(self.v.validate_run(r,self.root))

    def kit(self):
        root=self.root/'kit'; root.mkdir()
        files=['AGENTS.md',str(self.v.SKILL/'SKILL.md'),str(self.v.SKILL/'agents/openai.yaml'),str(self.v.SKILL/'scripts/setup.py'),str(self.v.SKILL/'dependencies.lock.json')]
        files += [str(self.v.SKILL/'references'/name) for name in ('workflow.md','linear.md','runtime.md','context.md','handoff.md','operations.md')]
        files += [str(self.v.SKILL/'scripts'/name) for name in ('handoff.py','operations.py')]
        files += [str(self.v.SKILL/'bundles'/(name+'.zip')) for name in ('superpowers','ui-ux-pro-max','ponytail')]
        for filename in files:
            path=root/filename; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('fixture')
        lock={'schema_version':1,'families':[{'name':name,'repository':'https://example.com/'+name,'revision':'a'*40,'license':'MIT','archive':'bundles/'+name+'.zip','sha256':'b'*64,'skills':{'skill':'folder'}} for name in ('superpowers','ui-ux-pro-max','ponytail')]}
        (root/self.v.SKILL/'dependencies.lock.json').write_text(json.dumps(lock))
        for role,(model,effort) in self.v.ROLES.items():
            path=root/'.codex/agents'/(role+'.toml'); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('name = "'+role+'"\ndescription = "role"\ndeveloper_instructions = "read references"\nmodel = "'+model+'"\nmodel_reasoning_effort = "'+effort+'"\n')
        for name,fields in self.v.REQUIRED_TEXT.items():
            path=root/self.v.SKILL/'templates'/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('\n'.join('## '+field for field in fields))
        (root/self.v.SKILL/'templates/project.json').write_text(json.dumps(self.project()))
        (root/self.v.SKILL/'templates/run.json').write_text(json.dumps(self.run_record()))
        return root

    def test_shipped_kit_and_inert_templates_validate(self):
        root = Path(__file__).resolve().parents[1]
        templates = root / self.v.SKILL / 'templates'
        project = json.loads((templates / 'project.json').read_text(encoding='utf-8-sig'))
        record = json.loads((templates / 'run.json').read_text(encoding='utf-8-sig'))
        with self.subTest(contract='shipped kit'):
            self.assertEqual([], self.v.validate_kit(root))
        with self.subTest(contract='shipped project'):
            self.assertEqual([], self.v.validate_project(project))
        with self.subTest(contract='shipped run'):
            self.assertEqual([], self.v.validate_run(record, root))
        with self.subTest(contract='inert capability observations'):
            self.assertTrue(all(cap['available'] is None and cap['evidence'] is None
                                for cap in project['runtime']['capabilities'].values()))
        with self.subTest(contract='inert project identity'):
            self.assertIsNone(project['runtime']['host'])
            self.assertIsNone(project['git']['repository_id'])
        with self.subTest(contract='inert run identity and approvals'):
            for key in ('run_id', 'repository_id', 'controller_root', 'owner_claim_id', 'current_phase'):
                self.assertIsNone(record[key])
            self.assertEqual({'spec': None, 'plan': None}, record['approvals'])
            self.assertEqual([], record['phase_ids'])
            self.assertEqual([], record['completed_phase_reports'])

    def test_approved_kit_and_inert_templates_validate(self):
        root=self.kit(); self.assertEqual([],self.v.validate_kit(root))
        p=json.loads((root/self.v.SKILL/'templates/project.json').read_text())
        self.assertIsNone(p['git']['repository_id'])

    def test_economical_role_defaults_and_legacy_defaults_rejected(self):
        expected = {'relay': ('gpt-6.1-sol', 'medium'),
                    'atlas': ('gpt-6.1-sol', 'high'),
                    'lens': ('gpt-6.1-sol', 'high')}
        for role, pair in expected.items():
            with self.subTest(role=role):
                self.assertEqual(pair, self.v.ROLES[role])
        root = self.kit()
        for role, old_effort in (('relay', 'high'), ('atlas', 'xhigh'), ('lens', 'xhigh')):
            path = root / '.codex/agents' / (role + '.toml')
            saved = path.read_text()
            path.write_text(saved.replace('model_reasoning_effort = "' + expected[role][1] + '"',
                                          'model_reasoning_effort = "' + old_effort + '"'))
            self.assertTrue(any(role + '.toml.model_reasoning_effort' in e
                                for e in self.v.validate_kit(root)))
            path.write_text(saved)

    def test_issue_and_dispatch_require_actionable_validation(self):
        for name in ('linear-issue.md', 'dispatch.md'):
            for field in ('Pre-push readiness', 'Fixture isolation', 'Failure diagnosis'):
                with self.subTest(template=name, field=field):
                    self.assertIn(field, self.v.REQUIRED_TEXT[name])

    def test_wrong_role_model_or_effort_and_override_rejected(self):
        root=self.kit()
        for role,key,value in (('forge','model_reasoning_effort','high'),('atlas','model_reasoning_effort','max'),('pixel','model','gpt-6.1-sol'),('spark','model','unknown')):
            path=root/'.codex/agents'/(role+'.toml'); saved=path.read_text()
            path.write_text(saved.replace(key+' = "'+(self.v.ROLES[role][0] if key=='model' else self.v.ROLES[role][1])+'"',key+' = "'+value+'"'))
            self.assertTrue(any(role+'.toml.'+key in e for e in self.v.validate_kit(root)))
            path.write_text(saved)
        path=root/'.codex/agents/lens.toml'
        for key in ('sandbox_mode','approval_policy'):
            saved=path.read_text(); path.write_text(saved+'\n'+key+' = "override"')
            self.assertTrue(any(key in e for e in self.v.validate_kit(root))); path.write_text(saved)

    def test_missing_required_files_and_sections(self):
        root=self.kit()
        for name,fields in self.v.REQUIRED_TEXT.items():
            path=root/self.v.SKILL/'templates'/name; saved=path.read_text()
            for field in fields:
                path.write_text(saved.replace(field,'REMOVED'))
                self.assertTrue(any(name in e and field in e for e in self.v.validate_kit(root)),name+':'+field)
            path.write_text(saved)
        path=root/'.codex/agents/forge.toml'; path.unlink()
        self.assertTrue(any('forge.toml' in e for e in self.v.validate_kit(root)))
        (root/'AGENTS.md').write_text('Read .agents/skills/spec-team/references/missing.md')
        self.assertTrue(any('missing.md' in e for e in self.v.validate_kit(root)))

    def test_kit_source_and_controller_roots_and_readonly_cli(self):
        kit=self.kit(); record=self.run_record('merging'); project=self.project(); project['git']['repository_id']='repo-123'
        p=self.root/'settings.json'; p.write_text(json.dumps(project)); r=self.root/'record.json'; r.write_text(json.dumps(record))
        before={str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        args=['--root',str(kit),'--controller-root',str(self.root),'--project',str(p),'--run',str(r)]
        output=io.StringIO()
        with contextlib.redirect_stdout(output): result=self.v.main(args)
        self.assertEqual(0,result,output.getvalue()); self.assertIn('SPEC_TEAM_VALID',output.getvalue())
        self.assertEqual(before,{str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(1,self.v.main(args[:4]+args[6:]))
        project['git']['repository_id']='other'; p.write_text(json.dumps(project))
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(1,self.v.main(args))
        r.write_text('{"password": "FAKE_SECRET_DO_NOT_PRINT"')
        output=io.StringIO()
        with contextlib.redirect_stdout(output): self.assertEqual(1,self.v.main(args))
        self.assertNotIn('FAKE_SECRET',output.getvalue())

    def test_windows_junction_redirection_fails_closed(self):
        import os
        import subprocess
        if os.name != 'nt': self.skipTest('Windows junction fixture only')
        target=self.root/'target'; target.mkdir()
        storage=self.root/'.spec-team'
        result=subprocess.run(['cmd','/c','mklink','/J',str(storage),str(target)],capture_output=True)
        if result.returncode: self.skipTest('Windows junction creation unavailable')
        self.addCleanup(storage.rmdir)
        with self.assertRaises(ValueError): self.o.claim_owner(self.root,'s',str(uuid.uuid4()))
        self.assertEqual([],list(target.iterdir()))
        r=self.run_record('cleanup'); r['current_phase']['worktrees']=[{'path':str(storage),'branch':None,'base_sha':'b'*40,'owner':'w','status':'retained'}]
        self.assertTrue(self.v.validate_run(r,self.root))

    def test_lock_metadata_rejected_when_unpinned_or_malformed(self):
        root=self.kit(); path=root/self.v.SKILL/'dependencies.lock.json'
        for value in ({'schema_version':2,'families':[]},{'schema_version':1,'families':[]},None):
            path.write_text(json.dumps(value)); self.assertTrue(self.v.validate_kit(root))

    def test_headings_cannot_be_replaced_by_prose(self):
        root=self.kit()
        for name,heading in (('product-spec.md','Case coverage'),('technical-plan.md','Project quality profile'),('technical-plan.md','Stack recipe and integration'),('phase-report.md','Project quality evidence'),('phase-report.md','Delivery observations'),('memory.md','Entries')):
            path=root/self.v.SKILL/'templates'/name; saved=path.read_text()
            path.write_text(saved.replace('## '+heading,heading))
            self.assertTrue(any(name in e and heading in e for e in self.v.validate_kit(root)))
            path.write_text(saved)

    def test_phase_report_cannot_live_in_removable_worktree(self):
        r=self.run_record('complete'); folder=self.root/'worktrees/w1'; folder.mkdir(parents=True)
        path=folder/'report.md'; path.write_text('receipt')
        r['current_phase']['worktrees']=[{'path':str(folder),'branch':None,'base_sha':'b'*40,'owner':'worker','status':'retained'}]
        r['completed_phase_reports']=[{'id':'p1','path':str(path),'merge_commit':'d'*40,'cleanup_status':'complete'}]
        self.assertTrue(self.v.validate_run(r,self.root))

    def test_failed_claim_write_preserves_partial_state(self):
        from unittest.mock import patch
        def fail_write(claim, stream):
            stream.write('{'); stream.flush(); raise OSError('simulated write failure')
        run=str(uuid.uuid4())
        with patch.object(self.o.json,'dump',side_effect=fail_write):
            with self.assertRaises(ValueError): self.o.claim_owner(self.root,'session',run)
        path=self.root/'.spec-team/owner.json'; self.assertEqual('{',path.read_text())
        with self.assertRaises(ValueError): self.o.check_owner(self.root,str(uuid.uuid4()),run)
        self.assertEqual('{',path.read_text())

    def test_broken_relative_reference_is_reported(self):
        root=self.kit(); path=root/self.v.SKILL/'SKILL.md'
        path.write_text('[required procedure](references/missing.md)')
        self.assertTrue(any('missing.md' in e for e in self.v.validate_kit(root)))

    def test_owner_cli_markers_and_errors(self):
        run=str(uuid.uuid4()); output=io.StringIO()
        with contextlib.redirect_stdout(output): self.assertEqual(0,self.o.main(['claim','--root',str(self.root),'--session-id','session','--run-id',run]))
        self.assertTrue(output.getvalue().startswith('OWNER_CLAIMED '))
        claim=json.loads((self.root/'.spec-team/owner.json').read_text())
        for command,marker in (('check','OWNER_OK'),('release','OWNER_RELEASED')):
            args=[command,'--root',str(self.root),'--claim-id',claim['claim_id']]
            if command=='check': args += ['--run-id',run]
            output=io.StringIO()
            with contextlib.redirect_stdout(output): self.assertEqual(0,self.o.main(args))
            self.assertEqual(marker,output.getvalue().strip())
        output=io.StringIO()
        with contextlib.redirect_stdout(output): self.assertEqual(1,self.o.main(['claim','--root',str(self.root),'--session-id','s','--run-id','FAKE_SECRET_DO_NOT_PRINT']))
        self.assertNotIn('FAKE_SECRET',output.getvalue())

    def dispatch(self, role='forge'):
        return {'role': role, 'requested_model': 'gpt-6.1-sol',
                'requested_effort': 'medium', 'observed_model': None,
                'observed_effort': None, 'worker_id': None, 'retries': 0, 'usage': None}

    def test_dispatch_escalation_requires_reason_scope_and_evidence(self):
        record = self.run_record('implementing')
        d = self.dispatch('lens')
        d.update(requested_effort='xhigh', escalation={
            'reason': 'Diagnosed cross-tenant authorization ambiguity',
            'scope': 'Review the changed permission contract',
            'evidence': 'retained diagnosis reference'})
        record['current_phase']['dispatches'] = [d]
        self.assertEqual([], self.v.validate_run(record, self.root))
        for bad in (None, {}, {'reason': 'risk'},
                    {'reason': 'risk', 'scope': [], 'evidence': 'reference'}):
            d['escalation'] = bad
            self.assertTrue(self.v.validate_run(record, self.root))
        d['escalation'] = {'reason': 'risk', 'scope': 'contract', 'evidence': 'reference'}
        for model, effort in (('gpt-6-astra', 'xhigh'), ('gpt-6.1-sol', 'max')):
            d.update(requested_model=model, requested_effort=effort)
            self.assertTrue(self.v.validate_run(record, self.root))
        d.update(role='pixel', requested_model='gpt-6.1-sol', requested_effort='xhigh')
        self.assertEqual([], self.v.validate_run(record, self.root))

    def test_dispatch_role_wrong_json_types_are_field_errors(self):
        record = self.run_record('merging')
        record['current_phase']['dispatches'] = [self.dispatch()]
        self.assertEqual([], self.v.validate_run(record, self.root))
        for role in ([], {}, ['forge'], {'name': 'forge'}, None, False, 1, ''):
            with self.subTest(role=role):
                record['current_phase']['dispatches'] = [self.dispatch(role)]
                errors = self.v.validate_run(record, self.root)
                self.assertTrue(any('dispatch.role:' in error for error in errors), errors)

    def test_dispatch_role_wrong_types_exit_cleanly_in_cli(self):
        import subprocess
        import sys
        kit = self.kit()
        project = self.project()
        project['git']['repository_id'] = 'repo-123'
        settings_path = self.root / 'project.json'
        settings_path.write_text(json.dumps(project), encoding='utf-8')
        record = self.run_record('merging')
        record_path = self.root / 'record.json'
        for role in ([], {}):
            with self.subTest(role=role):
                record['current_phase']['dispatches'] = [self.dispatch(role)]
                record_path.write_text(json.dumps(record), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, '-B', str(SCRIPTS / 'validate.py'), '--root', str(kit),
                     '--controller-root', str(self.root), '--project', str(settings_path),
                     '--run', str(record_path)], capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(1, result.returncode)
                self.assertIn('dispatch.role:', result.stdout)
                self.assertNotIn('SPEC_TEAM_VALID', result.stdout)
                self.assertEqual('', result.stderr)
                self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_phase_hash_boundaries_reject_wrong_json_types(self):
        for value in ([], {}, ['p1'], {'id': 'p1'}, None, False, 1):
            with self.subTest(value=value):
                record = self.run_record('complete')
                record['phase_ids'] = [value]
                self.assertTrue(any('phase_ids:' in error for error in self.v.validate_run(record, self.root)))
                record = self.run_record('complete')
                record['completed_phase_reports'] = [
                    {'id': value, 'path': 'report.md', 'merge_commit': 'd' * 40,
                     'cleanup_status': 'complete'}]
                self.assertTrue(any('phase_report.id:' in error for error in self.v.validate_run(record, self.root)))

    def test_nested_bad_types_never_raise(self):
        for value in (None,[],{},1,True):
            p=self.project(); p['git']['codex_coauthor']['name']=value
            self.assertTrue(self.v.validate_project(p))
            for key in ('review','acceptance','pr','merge','cleanup','worktrees','dispatches'):
                r=self.run_record('merging'); r['current_phase'][key]=value
                errors=self.v.validate_run(r,self.root)
                self.assertIsInstance(errors,list)

if __name__ == '__main__': unittest.main()
