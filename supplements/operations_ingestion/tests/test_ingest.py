import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from ingest import ingest

class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.bundle=self.root/'bundle'
        shutil.copytree(Path(__file__).resolve().parents[1]/'fixtures',self.bundle)
        self.db=self.root/'lab.sqlite'
    def counts(self):
        with sqlite3.connect(self.db) as c:
            return [c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('orders','events','notes')]
    def test_mixed_sources_and_exact_replay(self):
        r=ingest(self.bundle,self.db)
        self.assertEqual(r['status'],'committed')
        self.assertEqual(self.counts(),[3,3,2])
        self.assertEqual(ingest(self.bundle,self.db)['status'],'duplicate')
        self.assertEqual(self.counts(),[3,3,2])
    def test_raw_note_preserved_and_query_join(self):
        ingest(self.bundle,self.db)
        with sqlite3.connect(self.db) as c:
            row=c.execute("SELECT o.quantity,n.raw_text FROM orders o JOIN notes n USING(order_id) WHERE note_id='N001'").fetchone()
        self.assertEqual(row,(100,(self.bundle/'notes/N001.txt').read_text()))
    def test_bad_quantity_is_rejected_with_no_business_rows(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace(',100',',-1'))
        r=ingest(self.bundle,self.db)
        self.assertEqual(r['issues'][0]['row'],2)
        self.assertEqual(self.counts(),[0,0,0])
    def test_invalid_calendar_date(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace('2026-10-20','2026-02-30'))
        self.assertEqual(ingest(self.bundle,self.db)['status'],'rejected')
    def test_timezone_required(self):
        p=self.bundle/'events.jsonl';p.write_text(p.read_text().replace('2026-10-19T02:00:00Z','2026-10-19T02:00:00'))
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'invalid_aware_timestamp')
    def test_unknown_order_rolls_back_all(self):
        p=self.bundle/'events.jsonl';p.write_text(p.read_text().replace('O001','O999'))
        self.assertEqual(ingest(self.bundle,self.db)['status'],'rejected')
        self.assertEqual(self.counts(),[0,0,0])
    def test_injected_failure_and_retry(self):
        self.assertEqual(ingest(self.bundle,self.db,fail_after=4)['status'],'rejected')
        self.assertEqual(self.counts(),[0,0,0])
        self.assertEqual(ingest(self.bundle,self.db)['status'],'committed')
        self.assertEqual(self.counts(),[3,3,2])
    def test_changed_id_is_not_silently_overwritten(self):
        ingest(self.bundle,self.db)
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace(',100',',101'))
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'existing_id_content_conflict')
        self.assertEqual(self.counts(),[3,3,2])
    def test_logical_duplicate_new_bundle_skips_entities(self):
        ingest(self.bundle,self.db)
        p=self.bundle/'orders.csv';p.write_text(p.read_text()+'\n')
        r=ingest(self.bundle,self.db)
        self.assertEqual(r['status'],'committed')
        self.assertEqual(r['inserted'],{'orders':0,'events':0,'notes':0})
    def test_duplicate_ids_inside_bundle(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text()+'O001,2026-10-20,100\n')
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'duplicate_id_in_bundle')
    def test_path_traversal(self):
        p=self.bundle/'manifest.json';m=json.loads(p.read_text());m['notes'][0]['path']='../private.txt';p.write_text(json.dumps(m))
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'path_outside_bundle')
    def test_schema_drift(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace('quantity','units'))
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'schema_mismatch')
    def test_invalid_json(self):
        (self.bundle/'events.jsonl').write_text('{broken')
        self.assertEqual(ingest(self.bundle,self.db)['issues'][0]['code'],'invalid_json')
    def test_audit_does_not_copy_note_text(self):
        ingest(self.bundle,self.db)
        with sqlite3.connect(self.db) as c:
            report=c.execute('SELECT report_json FROM runs').fetchone()[0]
        self.assertNotIn('Receiving slot',report)
        self.assertNotIn('Receiving slot',json.dumps(ingest(self.bundle,self.db)))

if __name__=='__main__': unittest.main()
