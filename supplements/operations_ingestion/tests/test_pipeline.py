import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pipeline import PipelineError,run_pipeline,render_report,reconcile

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.bundle=self.root/'input';self.out=self.root/'out'
        shutil.copytree(Path(__file__).resolve().parents[1]/'fixtures',self.bundle)
    def test_full_pipeline_no_network_and_no_quantity_join_inflation(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network forbidden')):
            r,path=run_pipeline(self.bundle,self.out)
        self.assertEqual(r['status'],'passed_local')
        self.assertEqual([s['status'] for s in r['stages']],['passed']*4)
        d=json.loads((path/'data_report.json').read_text())
        self.assertEqual((d['order_count'],d['quantity_total'],d['event_count'],d['note_count']),(3,225,3,2))
        self.assertTrue((path/'report.html').is_file())
    def test_repeated_pipeline_retains_rows_and_separate_run_reports(self):
        _,p1=run_pipeline(self.bundle,self.out);r,p2=run_pipeline(self.bundle,self.out)
        self.assertNotEqual(p1,p2);self.assertEqual(r['stages'][0]['result']['status'],'duplicate')
        with sqlite3.connect(self.out/'pipeline.sqlite') as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],3)
    def test_invalid_data_stops_later_stages(self):
        p=self.bundle/'orders.csv';p.write_text(p.read_text().replace(',100',',-1'))
        r,path=run_pipeline(self.bundle,self.out)
        self.assertEqual(r['status'],'failed')
        self.assertEqual([s['status'] for s in r['stages']],['failed','skipped','skipped','skipped'])
        self.assertFalse((path/'report.html').exists())
    def test_downstream_failure_is_not_reported_as_load_rollback(self):
        with patch('pipeline.reconcile',side_effect=PipelineError('source_database_mismatch')):
            r,path=run_pipeline(self.bundle,self.out)
        self.assertEqual([s['status'] for s in r['stages']],['passed','failed','skipped','skipped'])
        with sqlite3.connect(self.out/'pipeline.sqlite') as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],3)
        self.assertFalse((path/'report.html').exists())
    def test_reconciliation_detects_changed_storage(self):
        run_pipeline(self.bundle,self.out)
        with sqlite3.connect(self.out/'pipeline.sqlite') as c:c.execute("UPDATE orders SET quantity=101 WHERE order_id='O001'")
        with self.assertRaisesRegex(PipelineError,'source_database_mismatch'):reconcile(self.bundle,self.out/'pipeline.sqlite')
    def test_existing_unowned_output_is_rejected(self):
        self.out.mkdir();(self.out/'important.txt').write_text('keep')
        with self.assertRaises(PipelineError):run_pipeline(self.bundle,self.out)
        self.assertEqual((self.out/'important.txt').read_text(),'keep')
    def test_inputs_cannot_be_outputs(self):
        with self.assertRaises(PipelineError):run_pipeline(self.bundle,self.bundle/'out')
    def test_html_escapes_display_fields(self):
        r,p=run_pipeline(self.bundle,self.out)
        data=json.loads((p/'data_report.json').read_text());data['orders'][0]['order_id']='<script>alert(1)</script>'
        text=render_report(data,'test')
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)

if __name__=='__main__':unittest.main()
