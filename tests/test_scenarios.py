import sqlite3
import unittest
from datetime import date
from project import SCHEMA, capacity_scenarios

class ScenarioTests(unittest.TestCase):
    def fixture(self):
        c=sqlite3.connect(':memory:');c.executescript(SCHEMA)
        c.executemany('INSERT INTO trips VALUES(?,?,?,?,?)',[
            ('FULL','DC-A','Metro','2026-10-15',100),
            ('SPARE','DC-B','Outer','2026-10-15',100)])
        c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',[
            ('A','FULL','2026-10-16','2026-10-16',130,100,'Capacity shortfall'),
            ('B','SPARE','2026-10-16','2026-10-16',10,10,'None')])
        return c
    def results(self,c):return capacity_scenarios(c,date(2026,10,19))
    def test_no_spare_capacity_pooling(self):
        r=self.results(self.fixture())['capacity_scenarios'][0]
        self.assertEqual(r['recoverable_units_upper_bound'],0)
        self.assertEqual(r['remaining_short_units'],30)
    def test_hand_calculated_increment(self):
        rows=self.results(self.fixture())['capacity_scenarios']
        r=next(r for r in rows if r['scope']=='All network' and r['capacity_increment_pct']==10)
        self.assertEqual(r['added_capacity_units'],20)
        self.assertEqual(r['incremental_recoverable_units'],10)
        self.assertEqual(r['unused_added_capacity_units'],10)
        target=next(r for r in rows if r['scope']=='DC-A / Metro' and r['capacity_increment_pct']==10)
        self.assertEqual(target['incremental_recoverable_units'],10)
        self.assertEqual(target['added_capacity_units'],10)
    def test_recovery_bounded_and_monotonic(self):
        rows=[r for r in self.results(self.fixture())['capacity_scenarios'] if r['scope']=='All network']
        self.assertEqual([r['remaining_short_units'] for r in rows],[30,20,10])
        for r in rows:
            self.assertLessEqual(r['incremental_recoverable_units'],r['added_capacity_units'])
            self.assertGreaterEqual(r['unused_added_capacity_units'],0)
    def test_stress_hand_calculation(self):
        r=next(r for r in self.results(self.fixture())['capacity_stress'] if r['demand_growth_pct']==10 and r['capacity_increment_pct']==10)
        self.assertEqual(r['modeled_demand_units'],154)
        self.assertEqual(r['capacity_shortfall_units'],33)
    def test_future_due_shortage_not_recovered(self):
        c=self.fixture();c.execute("UPDATE orders SET due_date='2026-10-21',delivered_date=NULL WHERE order_id='A'")
        rows=self.results(c)['capacity_scenarios']
        self.assertTrue(all(r['due_short_units']==0 and r['recoverable_units_upper_bound']==0 for r in rows))
if __name__=='__main__':unittest.main()
