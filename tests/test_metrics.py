import sqlite3
import unittest
from project import SCHEMA, analyze, generate

class MetricsTests(unittest.TestCase):
    def fixture(self):
        c=sqlite3.connect(':memory:');c.executescript(SCHEMA)
        c.execute("INSERT INTO trips VALUES('T1','DC-A','Metro','2026-10-15',100)")
        c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',[
            ('A','T1','2026-10-16','2026-10-16',20,20,'None'),
            ('B','T1','2026-10-16',None,20,20,'Dispatch exception'),
            ('C','T1','2026-10-16','2026-10-17',20,10,'Capacity shortfall'),
            ('D','T1','2026-10-20',None,20,20,'None')])
        return c
    def test_due_denominator_includes_overdue_excludes_future(self):
        r=analyze(self.fixture())['totals'];self.assertEqual(r['due_orders'],3);self.assertEqual(r['overdue_open'],1);self.assertAlmostEqual(r['otif_rate'],1/3)
    def test_fill_uses_units_not_average_order_rates(self):
        self.assertAlmostEqual(analyze(self.fixture())['totals']['unit_fill_rate'],50/60)
    def test_capacity_once_per_trip_and_dispatch_window(self):
        self.assertAlmostEqual(analyze(self.fixture())['cohorts'][0]['trip_capacity_utilization'],.7)
    def test_overload_blocks_report(self):
        c=self.fixture();c.execute('UPDATE trips SET capacity_units=10')
        with self.assertRaises(ValueError):analyze(c)
    def test_on_time_partial_is_not_otif(self):
        c=self.fixture();c.execute("UPDATE orders SET shipped_units=10 WHERE order_id='A'")
        r=analyze(c)['totals'];self.assertEqual(r['on_time_orders'],1);self.assertEqual(r['otif_orders'],0)
    def test_details_reconcile_and_flags_overlap_without_duplicates(self):
        r=analyze(self.fixture())
        self.assertEqual(sum(d['due_orders'] for d in r['daily']),r['totals']['due_orders'])
        self.assertEqual(sum(d['otif_orders'] for d in r['daily']),r['totals']['otif_orders'])
        self.assertEqual(len(r['exceptions']),2)
        late=next(o for o in r['exceptions'] if o['order_id']=='C')
        self.assertEqual(late['flags'],['Delivered late','Short shipment'])
        self.assertEqual(late['late_days'],1)
    def test_future_recorded_delivery_is_open_at_snapshot(self):
        c=self.fixture();c.execute("UPDATE orders SET delivered_date='2026-10-21' WHERE order_id='B'")
        r=analyze(c);self.assertEqual(r['totals']['overdue_open'],1)
        self.assertIsNone(next(o for o in r['exceptions'] if o['order_id']=='B')['delivered_date'])
    def test_determinism(self):self.assertEqual(generate(42),generate(42))
    def test_full_generation_reconciles(self):
        trips,orders=generate();c=sqlite3.connect(':memory:');c.executescript(SCHEMA)
        c.executemany('INSERT INTO trips VALUES(?,?,?,?,?)',trips);c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',orders)
        r=analyze(c);self.assertEqual(sum(x['due_orders'] for x in r['cohorts']),r['totals']['due_orders'])
        self.assertTrue(all(0<=x['otif_rate']<=1 and 0<=x['trip_capacity_utilization']<=1 for x in r['cohorts']))

class TraceTests(unittest.TestCase):
    def test_trace_reconciles_and_demo_rejects_duplicate(self):
        from trace_demo import demo
        result=demo()
        self.assertIn('duplicate',result['rejection'])
        self.assertTrue(result['rejection_unchanged'])
        self.assertTrue(result['repeat_equal'])
        self.assertEqual((result['before']['otif_rate'],result['before']['unit_fill_rate']),(.5,.75))
        self.assertEqual((result['after']['otif_rate'],result['after']['unit_fill_rate']),(1,1))
        self.assertEqual(result['before']['exceptions'][0]['flags'],['Overdue open','Short shipment'])
        self.assertEqual(result['after']['exceptions'],[])
        for phase in ('before','after'):
            rows=result[phase]['trace']
            self.assertEqual(sum(r['otif'] for r in rows)/len(rows),result[phase]['otif_rate'])
            self.assertEqual(sum(r['shipped_units'] for r in rows)/sum(r['ordered_units'] for r in rows),result[phase]['unit_fill_rate'])

    def test_generated_trace_reconciles_each_cohort(self):
        trips, orders = generate()
        c=sqlite3.connect(':memory:'); c.executescript(SCHEMA)
        c.executemany('INSERT INTO trips VALUES(?,?,?,?,?)',trips)
        c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',orders)
        c.execute("INSERT INTO orders VALUES('FUTURE','T0001','2026-10-20','2026-10-21',1,0,'None')")
        report=analyze(c)
        self.assertNotIn('FUTURE',{r['order_id'] for r in report['kpi_trace']})
        for cohort in report['cohorts']:
            rows=[r for r in report['kpi_trace'] if (r['warehouse'],r['route']) == (cohort['warehouse'],cohort['route'])]
            self.assertEqual(len(rows),cohort['due_orders'])
            self.assertEqual(sum(r['otif'] for r in rows),cohort['otif_orders'])
            self.assertEqual(sum(r['shipped_units'] for r in rows),cohort['shipped_units'])
            self.assertEqual(sum(r['ordered_units'] for r in rows),cohort['ordered_units'])
            self.assertEqual({r['order_id'] for r in rows if r['flags']}, {r['order_id'] for r in report['exceptions'] if (r['warehouse'],r['route']) == (cohort['warehouse'],cohort['route'])})

if __name__=='__main__':unittest.main()
