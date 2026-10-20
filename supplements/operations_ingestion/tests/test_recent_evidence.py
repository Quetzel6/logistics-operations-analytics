import sqlite3
import tempfile
import unittest
from pathlib import Path
from assistant import brief, context
from ingest import ingest

ROOT=Path(__file__).resolve().parents[1]
class RecentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'test.sqlite';ingest(ROOT/'fixtures',self.db)
    def add_history(self):
        with sqlite3.connect(self.db) as c:
            run=c.execute('SELECT run_id FROM runs LIMIT 1').fetchone()[0]
            c.executemany('INSERT INTO events VALUES (?,?,?,?,?)',
                [(f'H{i:03}','O001',f'2026-10-21T00:{i:02}:00+00:00','dispatched',run) for i in range(25)])
            c.execute('INSERT INTO events VALUES (?,?,?,?,?)',('LATEST','O001','2026-10-22T00:00:00+00:00','exception',run))
    def test_latest_exception_survives_long_history_and_notes_are_visible(self):
        self.add_history();before=self.db.read_bytes();r=brief(self.db,'O001')
        ids={x['evidence_id'] for x in r['findings']}
        self.assertIn('event:LATEST',ids);self.assertIn('note:N001',ids)
        self.assertIn('retrieval_limit_reached',r['warnings'])
        self.assertEqual(r['record_status'],'exception_recorded')
        self.assertEqual(before,self.db.read_bytes())
    def test_event_window_is_recent_and_displayed_chronologically(self):
        self.add_history();ctx=context(self.db,'O001')
        events=[r for r in ctx['evidence'] if r['kind']=='event']
        self.assertEqual(len(events),20)
        self.assertEqual(events[-1]['evidence_id'],'event:LATEST')
        self.assertNotIn('event:E001',{r['evidence_id'] for r in events})
    def test_exception_retained_when_later_dispatches_fill_selection(self):
        with sqlite3.connect(self.db) as c:
            run=c.execute('SELECT run_id FROM runs LIMIT 1').fetchone()[0]
            c.executemany('INSERT INTO events VALUES (?,?,?,?,?)',
                [(f'AFTER{i}','O001',f'2026-10-21T00:0{i}:00+00:00','dispatched',run) for i in range(6)])
        r=brief(self.db,'O001');ids={f['evidence_id'] for f in r['findings']}
        self.assertIn('event:E002',ids);self.assertIn('event:AFTER5',ids);self.assertIn('note:N001',ids)
