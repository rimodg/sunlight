"""Read-only route and HTML tests using a synthetic journal and local TestClient."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from watch_api import router
from watch_engine import WatchEngine
from watch_journal import Journal
from test_watch_loop import CF, release, response, reader


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.j = Journal(Path(self.temp.name)/'journal.sqlite3')
        engine = WatchEngine(self.j,{'schema':'sunlight.watch-source-policy.v1','sources':[CF]},
                             transport=lambda u:response({'releases':[release()]}),
                             clock=lambda:'2026-01-02T00:00:00Z',reader=reader)
        self.result = engine.tick()
        self.env = patch.dict(os.environ,{'SUNLIGHT_WATCH_DATA_DIR':self.temp.name}); self.env.start()
        app = FastAPI(); app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.env.stop(); self.j.close(); self.temp.cleanup()

    def test_health_is_ledger_state_and_overdue_is_visible(self):
        before = self.j.verify()
        value = self.client.get('/watch-engine/status').json()
        self.assertEqual(value['journal_head'],before)
        self.assertTrue(value['health']['scheduler']['overdue'])
        html = self.client.get('/watch-engine/ui')
        self.assertEqual(html.status_code,200)
        self.assertIn('Watch health: Overdue',html.text)
        self.assertIn(value['health']['scheduler']['receipt'],html.text)
        self.assertEqual(self.j.verify(),before)

    def test_subject_trace_and_exact_frozen_document(self):
        sid = self.result['subjects'][0]['id']
        data = self.client.get('/watch-engine/subjects/'+sid).json()
        obs = data['observations'][0]
        capture = self.client.get('/watch-engine/captures/'+obs['evidence']['capture'])
        self.assertEqual(capture.headers['x-content-sha256'],obs['evidence']['sha256'])
        self.assertEqual(capture.content,self.j.capture(obs['evidence']['capture'])['body'].encode())
        html = self.client.get('/watch-engine/ui?subject='+sid).text
        self.assertIn(obs['evidence']['sha256'],html)
        self.assertIn(obs['evidence']['locator'],html)
        self.assertIn('normalised_value',html)
        self.assertIn('00123456',html)

    def test_no_mutating_routes_and_missing_state_is_not_zero(self):
        self.assertEqual(self.client.post('/watch-engine/status').status_code,405)
        self.assertEqual(self.client.get('/watch-engine/events/absent').status_code,404)
        with patch.dict(os.environ,{'SUNLIGHT_WATCH_DATA_DIR':''}):
            value = self.client.get('/watch-engine/status')
            self.assertEqual(value.status_code,503)
            self.assertIn('No observations claimed',value.text)

    def test_historical_examination_is_a_direct_journal_view(self):
        eid=self.j.events(kind='examination')[-1]['id']
        index=self.client.get('/watch-engine/examinations').json()
        self.assertEqual(index['examinations'][0]['id'],eid)
        page=self.client.get('/watch-engine/ui?examination='+eid)
        self.assertEqual(page.status_code,200)
        self.assertIn('examination='+eid,page.text)
        self.assertEqual(self.client.get('/watch-engine/ui?examination=absent').status_code,404)


if __name__=='__main__':
    unittest.main()
