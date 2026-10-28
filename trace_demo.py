"""Repeatable synthetic demonstration of quality rejection and KPI tracing."""
import json
import sqlite3
from project import SCHEMA, analyze


def demo():
    with sqlite3.connect(':memory:') as c:
        c.executescript(SCHEMA)
        c.execute("INSERT INTO trips VALUES('T1','DC-A','Metro','2026-10-15',100)")
        c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)', [
            ('A','T1','2026-10-16','2026-10-16',20,20,'None'),
            ('B','T1','2026-10-16',None,20,10,'Short shipment')])
        before=analyze(c)
        try:
            c.execute("INSERT INTO orders VALUES('B','T1','2026-10-16',NULL,20,10,'duplicate')")
        except sqlite3.IntegrityError:
            rejection='duplicate order_id rejected by primary key'
        else:
            raise AssertionError('duplicate order unexpectedly accepted')
        rejection_unchanged=before==analyze(c)
        # A corrected synthetic snapshot is explicitly supplied, not inferred from a note.
        c.execute("UPDATE orders SET delivered_date='2026-10-16', shipped_units=20 WHERE order_id='B'")
        after=analyze(c)
        def summary(r):
            return {'otif_rate':r['totals']['otif_rate'], 'unit_fill_rate':r['totals']['unit_fill_rate'],
                    'exceptions':[{k:o[k] for k in ('order_id','flags')} for o in r['exceptions']],
                    'trace':r['kpi_trace']}
        return {'rejection':rejection,'rejection_unchanged':rejection_unchanged,'before':summary(before),'after':summary(after),
                'repeat_equal':after==analyze(c)}

if __name__=='__main__':
    print(json.dumps(demo(),indent=2))
