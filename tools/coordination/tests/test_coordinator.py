import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import socket
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

MODULE = Path(__file__).resolve().parents[1] / 'coordinator.py'
spec = importlib.util.spec_from_file_location('coordinator',MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = c.Store(self.root/'state.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return self.store.create('Kaynak indeksi', 'Kullanıcı sınırları içinde seçenekleri karşılaştır.')

    def test_four_stage_discussion_then_user_review_no_execution(self):
        job = self.create()
        roles = []
        for n in range(4):
            claimed = self.store.claim()
            roles.append(c.ROLES[claimed['stage']])
            self.assertEqual(claimed['stage'],n)
            self.assertTrue(self.store.finish(claimed, f'{n}: araştırma kanıtı'))
        self.assertEqual(roles,['cursor','codex','cursor','codex'])
        self.assertIsNone(self.store.claim())
        finished=self.store.get(job['id'])
        self.assertEqual(finished['status'],'READY_FOR_USER_REVIEW')
        self.assertIsNone(finished['approved_at'])
        approved=self.store.approve(job['id'])
        self.assertIsNotNone(approved['approved_at'])
        self.assertEqual(approved['status'],'READY_FOR_USER_REVIEW')
        self.assertIsNone(self.store.claim())

    def test_claim_atomic_between_concurrent_workers(self):
        self.create()
        self.create()
        barrier=threading.Barrier(6)
        results=[]
        def claim():
            barrier.wait()
            results.append(self.store.claim())
        threads=[threading.Thread(target=claim) for _ in range(6)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sum(r is not None for r in results),1)

    def test_cancel_invalidates_late_agent_completion(self):
        job=self.create()
        claimed=self.store.claim()
        self.store.cancel(job['id'])
        self.assertFalse(self.store.finish(claimed,'late output'))
        self.assertEqual(self.store.get(job['id'])['messages'],[])
        self.assertEqual(self.store.get(job['id'])['status'],'CANCELLED')

    def test_restart_does_not_repeat_paid_request(self):
        job=self.create()
        claimed=self.store.claim()
        self.store.recover()
        self.assertEqual(self.store.get(job['id'])['status'],'INTERRUPTED')
        self.assertFalse(self.store.finish(claimed,'stale output'))
        self.assertIsNone(self.store.claim())

    def test_daily_call_budget_is_persistent(self):
        self.create()
        first=self.store.claim(daily_limit=1)
        self.store.finish(first,'one response')
        restarted=c.Store(self.store.path)
        self.assertIsNone(restarted.claim(daily_limit=1))

    def test_pause_queue_and_input_limits(self):
        self.create()
        self.store.paused(True)
        self.assertIsNone(self.store.claim())
        self.store.paused(False)
        self.assertIsNotNone(self.store.claim())
        for title,prompt in [('', 'test'),('test',None),('test','a'*16001)]:
            with self.assertRaises(c.Invalid): self.store.create(title,prompt)

    def test_prompt_carries_previous_critique_and_preserves_approval_gate(self):
        self.create()
        first=self.store.claim()
        self.store.finish(first,'REVIEW-MARKER: use keyed deltas')
        second=self.store.claim()
        prompt=c.build_prompt(self.store,second)
        self.assertIn('REVIEW-MARKER',prompt)
        self.assertIn('Kullanıcı ortak planı',prompt)
        self.assertIn('UYGULAMA KODUNU',prompt)

    def test_worker_failure_terminal_not_retried(self):
        job=self.create()
        def broken(*_): raise RuntimeError('login required')
        worker=c.Worker(self.store,{'state_dir':str(self.root)},threading.Event(),runner=broken)
        self.assertTrue(worker.tick())
        self.assertFalse(worker.tick())
        self.assertEqual(self.store.get(job['id'])['status'],'FAILED')

    def test_missing_login_keeps_job_queued_without_agent_call(self):
        job=self.create()
        def forbidden(*_):raise AssertionError('Agent must not start before authentication')
        worker=c.Worker(self.store,{},threading.Event(),runner=forbidden,ready=lambda:False)
        self.assertFalse(worker.tick())
        self.assertEqual(self.store.get(job['id'])['status'],'QUEUED')

    def test_worker_relay_exports_all_stages(self):
        job=self.create()
        prompts=[]
        def fake(config,role,prompt,output,cancelled):
            prompts.append((role,prompt))
            return f'{role} response #{len(prompts)}'
        worker=c.Worker(self.store,{'state_dir':str(self.root)},threading.Event(),runner=fake)
        for _ in range(4):self.assertTrue(worker.tick())
        self.assertFalse(worker.tick())
        self.assertIn('cursor response #1',prompts[1][1])
        self.assertIn('codex response #2',prompts[2][1])
        export=(self.root/'discussions'/job['id']/'discussion.md').read_text(encoding='utf-8')
        self.assertIn('codex response #4',export)

    def test_queue_limit(self):
        for _ in range(10):self.create()
        with self.assertRaises(c.Invalid):self.create()

    def test_read_only_agent_flags(self):
        config=dict(repo=str(self.root),cursor_node='node',cursor_index='agent.js',codex='codex')
        cursor=c.agent_command(config,'cursor',self.root/'out')
        codex=c.agent_command(config,'codex',self.root/'out')
        self.assertEqual(cursor[cursor.index('--mode')+1],'plan')
        self.assertEqual(codex[codex.index('--sandbox')+1],'read-only')
        self.assertNotIn('--force',cursor)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',codex)

    def test_context_snapshot_stays_fixed_between_stages(self):
        (self.root/'AGENTS.md').write_text('BASELINE-CONTEXT',encoding='utf-8')
        self.create()
        prompts=[]
        def fake(config,role,prompt,output,cancelled):
            prompts.append(prompt)
            return 'response'
        worker=c.Worker(self.store,{'repo':str(self.root),'state_dir':str(self.root/'state')},threading.Event(),runner=fake)
        worker.tick()
        (self.root/'AGENTS.md').write_text('CHANGED-CONTEXT',encoding='utf-8')
        worker.tick()
        self.assertIn('BASELINE-CONTEXT',prompts[1])
        self.assertNotIn('CHANGED-CONTEXT',prompts[1])

    def test_real_process_cancel_stops_cli(self):
        script=self.root/'fake_agent.py'
        script.write_text('import time\nprint("started",flush=True)\ntime.sleep(30)\n',encoding='utf-8')
        config=dict(repo=str(self.root),cursor_node=sys.executable,cursor_index=str(script),
                    cursor_config_dir=str(self.root/'cursor'),timeout_seconds=10)
        started=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'iptal'):
            c.run_agent(config,'cursor','test',self.root/'result.txt',lambda:time.monotonic()-started>.4)
        self.assertLess(time.monotonic()-started,12)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        c.Store(cls.root/'coordination.sqlite3').paused(True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            cls.port=sock.getsockname()[1]
        cls.url=f'http://127.0.0.1:{cls.port}'
        config=dict(repo=str(cls.root),state_dir=str(cls.root),cursor_config_dir=str(cls.root/'cursor'),
                    cursor_node=sys.executable,cursor_index=str(MODULE),codex=sys.executable,port=cls.port)
        path=cls.root/'config.json'
        path.write_text(json.dumps(config),encoding='utf-8')
        cls.proc=subprocess.Popen([sys.executable,str(MODULE),'--config',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urlopen(cls.url+'/health',timeout=1) as response:
                    if response.status==200:break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Test HTTP service did not start')
        cls.token=(cls.root/'service.token').read_text().strip()

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.temp.cleanup()

    def request(self,path,body=None,auth=True,extra=None):
        headers={'Authorization':'Bearer '+self.token} if auth else {}
        if extra:headers.update(extra)
        request=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
        except HTTPError as exc:return exc.code,json.loads(exc.read())

    def test_health_does_not_expose_tasks(self):
        status,data=self.request('/health',auth=False)
        self.assertEqual(status,200)
        self.assertNotIn('jobs',data)

    def test_queue_requires_authentication(self):
        self.assertEqual(self.request('/api/state',auth=False)[0],401)

    def test_foreign_origin_rejected(self):
        self.assertEqual(self.request('/api/jobs',{'title':'x','prompt':'y'},extra={'Origin':'https://foreign.invalid'})[0],403)

    def test_foreign_host_rejected(self):
        self.assertEqual(self.request('/api/state',extra={'Host':'foreign.invalid'})[0],403)

    def test_create_read_cancel(self):
        status,job=self.request('/api/jobs',{'title':'HTTP task','prompt':'Research only'})
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/jobs/'+job['id'])[1]['status'],'QUEUED')
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/cancel',{})[1]['status'],'CANCELLED')

    def test_early_approval_rejected(self):
        job=self.request('/api/jobs',{'title':'Not ready','prompt':'Research'})[1]
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{})[0],400)

    def test_invalid_body_rejected(self):
        self.assertEqual(self.request('/api/jobs',{'title':'empty'})[0],400)


if __name__=='__main__':unittest.main()
