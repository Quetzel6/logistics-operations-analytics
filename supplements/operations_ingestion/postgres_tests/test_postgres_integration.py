"""Requires an explicitly disposable database named operations_test_*; never use employer data."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from postgres_ingest import (connect,ingest_postgres,reconcile_postgres,report_postgres,
                             snapshot_postgres,StorageError)
from postgres_pipeline import run_pipeline,render_report

ROOT=Path(__file__).resolve().parents[1]
DSN=os.environ.get('OPERATIONS_TEST_DSN','')

@unittest.skipUnless(DSN,'Requires explicitly disposable OPERATIONS_TEST_DSN')
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect(DSN) as c:
            if not c.execute('SELECT current_database()').fetchone()[0].startswith('operations_test_'):
                raise RuntimeError('Refusing database without operations_test_ prefix')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bundle=self.root/'bundle'
        shutil.copytree(ROOT/'fixtures',self.bundle)
        with connect(DSN) as c:c.execute('DROP SCHEMA IF EXISTS ops_ingestion_lab CASCADE')
    def tearDown(self):
        with connect(DSN) as c:c.execute('DROP SCHEMA IF EXISTS ops_ingestion_lab CASCADE')
    def load(self,**kwargs):return ingest_postgres(self.bundle,DSN,**kwargs)
    def counts(self):
        with connect(DSN) as c:
            return {t:c.execute(f'SELECT COUNT(*) FROM ops_ingestion_lab.{t}').fetchone()[0] for t in ('orders','events','notes','runs')}
    def test_load_exact_source_reconciliation_and_replay(self):
        first=self.load();before=snapshot_postgres(DSN);second=self.load()
        self.assertEqual((first['status'],second['status']),('committed','duplicate'))
        self.assertEqual(second['original_run_id'],first['run_id'])
        self.assertEqual(snapshot_postgres(DSN),before)
        self.assertEqual(self.counts(),dict(orders=3,events=3,notes=2,runs=2))
        self.assertEqual(reconcile_postgres(self.bundle,DSN)['matched_bundle_rows'],dict(orders=3,events=3,notes=2))
    def test_report_has_no_join_inflation(self):
        self.load();r=report_postgres(DSN)
        self.assertEqual((r['quantity_total'],r['order_count'],r['event_count'],r['note_count']),(225,3,3,2))
        self.assertEqual(r['orders'][0]['events'],2)
    def test_invalid_bundle_has_only_rejection_audit(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace(',100',',-1'))
        r=self.load();self.assertEqual(r['status'],'rejected')
        self.assertEqual(self.counts(),dict(orders=0,events=0,notes=0,runs=1))
    def test_unknown_order_rolls_back_all_business_rows(self):
        p=self.bundle/'events.jsonl';p.write_text(p.read_text().replace('O001','UNKNOWN'))
        self.assertEqual(self.load()['status'],'rejected')
        self.assertEqual(self.counts(),dict(orders=0,events=0,notes=0,runs=1))
    def test_injected_failure_audit_and_retry(self):
        failed=self.load(fail_after=4)
        self.assertEqual(failed['issues'][0]['code'],'injected_failure')
        self.assertEqual(self.counts(),dict(orders=0,events=0,notes=0,runs=1))
        self.assertEqual(self.load()['status'],'committed')
        self.assertEqual(self.counts(),dict(orders=3,events=3,notes=2,runs=2))
    def test_changed_id_rolls_back_new_rows_and_preserves_old_rows(self):
        self.load();before=snapshot_postgres(DSN)
        p=self.bundle/'orders.csv';lines=p.read_text().splitlines()
        p.write_text(lines[0]+'\nNEW,2026-10-20,9\n'+'\n'.join(lines[1:]).replace(',100',',101')+'\n')
        r=self.load();self.assertEqual(r['issues'][0]['code'],'existing_id_content_conflict')
        self.assertEqual(snapshot_postgres(DSN),before)
    def test_logical_replay_with_new_bundle_hash_skips_entities(self):
        self.load();p=self.bundle/'orders.csv';p.write_text(p.read_text()+'\n')
        r=self.load();self.assertEqual(r['status'],'committed')
        self.assertEqual(r['inserted'],dict(orders=0,events=0,notes=0))
        self.assertEqual(r['unchanged'],dict(orders=3,events=3,notes=2))
    def test_note_quotes_sql_like_text_and_unicode_preserved(self):
        p=self.bundle/'notes/N001.txt';value="SYNTHETIC: O'Brien; DROP TABLE orders; สวัสดี\n";p.write_text(value)
        self.load();reconcile_postgres(self.bundle,DSN)
        with connect(DSN) as c:
            self.assertEqual(c.execute("SELECT raw_text FROM ops_ingestion_lab.notes WHERE note_id='N001'").fetchone()[0],value)
    def test_audit_never_copies_raw_note(self):
        self.load()
        with connect(DSN) as c:
            reports=c.execute('SELECT report_json FROM ops_ingestion_lab.runs').fetchall()
        self.assertNotIn('Receiving slot',json.dumps(reports))
    def test_timestamp_is_normalized_and_date_types_reconcile(self):
        p=self.bundle/'events.jsonl';p.write_text(p.read_text().replace('2026-10-19T02:00:00Z','2026-10-19T09:00:00+07:00'))
        self.load();reconcile_postgres(self.bundle,DSN)
        with connect(DSN) as c:
            self.assertEqual(c.execute("SELECT timestamp_utc FROM ops_ingestion_lab.events WHERE event_id='E001'").fetchone()[0].isoformat(),'2026-10-19T02:00:00+00:00')
    def test_reconciliation_detects_tampering(self):
        self.load()
        with connect(DSN) as c:c.execute("UPDATE ops_ingestion_lab.orders SET quantity=999 WHERE order_id='O001'")
        with self.assertRaisesRegex(StorageError,'source_database_mismatch'):reconcile_postgres(self.bundle,DSN)
    def test_concurrent_exact_replay_commits_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.load(),range(2)))
        self.assertEqual(sorted(r['status'] for r in results),['committed','duplicate'])
        self.assertEqual(self.counts(),dict(orders=3,events=3,notes=2,runs=2))
    def test_unowned_schema_is_not_modified(self):
        with connect(DSN) as c:
            c.execute('CREATE SCHEMA ops_ingestion_lab')
            c.execute('CREATE TABLE ops_ingestion_lab.keep_me (value text)')
        with self.assertRaisesRegex(StorageError,'postgres_schema_not_owned'):self.load()
        with connect(DSN) as c:
            self.assertIsNotNone(c.execute("SELECT to_regclass('ops_ingestion_lab.keep_me')").fetchone()[0])
            self.assertIsNone(c.execute("SELECT to_regclass('ops_ingestion_lab.orders')").fetchone()[0])
    def test_pipeline_repeat_no_network_no_credential_leak(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network forbidden')):
            first,p1=run_pipeline(self.bundle,self.root/'out',DSN)
            second,p2=run_pipeline(self.bundle,self.root/'out',DSN)
        self.assertEqual(first['status'],'passed_local');self.assertEqual(second['status'],'passed_local')
        self.assertEqual(second['stages'][0]['result']['status'],'duplicate')
        self.assertNotEqual(p1,p2)
        self.assertEqual(json.loads((p1/'data_report.json').read_text())['quantity_total'],225)
        self.assertNotIn(DSN,(p1/'pipeline_run.json').read_text())
        data=report_postgres(DSN);data['orders'][0]['order_id']='<script>bad</script>'
        rendered=render_report(data,'<bad>');self.assertNotIn('<script>',rendered)
        self.assertIn('&lt;script&gt;',rendered)
    def test_invalid_data_skips_later_stages(self):
        (self.bundle/'events.jsonl').write_text('{bad')
        r,p=run_pipeline(self.bundle,self.root/'out',DSN)
        self.assertEqual([s['status'] for s in r['stages']],['failed','skipped','skipped','skipped'])
        self.assertFalse((p/'report.html').exists())
    def test_downstream_failure_does_not_undo_commit(self):
        with patch('postgres_pipeline.reconcile_postgres',side_effect=StorageError('source_database_mismatch')):
            r,p=run_pipeline(self.bundle,self.root/'out',DSN)
        self.assertEqual([s['status'] for s in r['stages']],['passed','failed','skipped','skipped'])
        self.assertEqual(self.counts()['orders'],3)
        self.assertFalse((p/'report.html').exists())

if __name__=='__main__':unittest.main()
