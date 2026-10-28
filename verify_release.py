"""Build in temp folders and write output/release_verification.json; Python 3.10+."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent

def main():
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-q'],cwd=ROOT,check=True)
    with tempfile.TemporaryDirectory() as folder:
        a,b=Path(folder)/'a',Path(folder)/'b'
        for out in (a,b):
            subprocess.run([sys.executable,str(ROOT/'project.py'),'--output',str(out)],cwd=folder,check=True,capture_output=True,text=True)
        files=('orders.csv','trips.csv','report.json','daily.csv','exceptions.csv','capacity_scenarios.csv','capacity_stress.csv','dashboard.html','decision_brief.md','kpi_trace.csv')
        digests={}
        for name in files:
            left=(a/name).read_bytes();right=(b/name).read_bytes()
            if left!=right:raise ValueError('Non-reproducible artifact: '+name)
            digests[name]=hashlib.sha256(left).hexdigest()
        r=json.loads((a/'report.json').read_text())
        with (a/'orders.csv').open() as f:orders=list(csv.DictReader(f))
        due=[o for o in orders if o['due_date']<=r['as_of']]
        ontime=sum(bool(o['delivered_date']) and o['delivered_date']<=o['due_date'] and o['delivered_date']<=r['as_of'] for o in due)
        otif=sum(bool(o['delivered_date']) and o['delivered_date']<=o['due_date'] and o['delivered_date']<=r['as_of'] and int(o['ordered_units'])==int(o['shipped_units']) for o in due)
        if (len(due),ontime,otif)!=(r['totals']['due_orders'],r['totals']['on_time_orders'],r['totals']['otif_orders']):raise ValueError('CSV/SQL KPI mismatch')
        with (a/'kpi_trace.csv').open() as f:trace=list(csv.DictReader(f))
        if len({o['order_id'] for o in trace})!=len(trace):raise ValueError('Duplicate trace order')
        if {o['order_id'] for o in trace}!={o['order_id'] for o in due}:raise ValueError('Trace due-order scope mismatch')
        for scope in [r['totals'],*r['cohorts']]:
            rows=trace if 'warehouse' not in scope else [o for o in trace if (o['warehouse'],o['route'])==(scope['warehouse'],scope['route'])]
            counts={'due_orders':len(rows),'otif_orders':sum(o['otif']=='True' for o in rows),
                    'ordered_units':sum(int(o['ordered_units']) for o in rows),'shipped_units':sum(int(o['shipped_units']) for o in rows)}
            if any(scope[k]!=v for k,v in counts.items()):raise ValueError('Trace KPI contribution mismatch')
        if {o['order_id'] for o in trace if o['flags']}!={o['order_id'] for o in r['exceptions']}:raise ValueError('Trace exception mismatch')
        network=next(x for x in r['capacity_scenarios'] if x['scope']=='All network' and x['capacity_increment_pct']==10)
        cohort=[x for x in r['capacity_scenarios'] if x['scope']!='All network' and x['capacity_increment_pct']==10]
        for key in ('added_capacity_units','incremental_recoverable_units','remaining_short_units'):
            if sum(c[key] for c in cohort)!=network[key]:raise ValueError('Scenario scope mismatch: '+key)
        evidence={'status':'passed','checks':['Python tests','two isolated clean builds','byte-identical report artifacts','raw CSV to SQL KPI reconciliation','trace CSV scope, cohort contributions and exceptions','scenario scope reconciliation'],'artifact_sha256':digests}
        (ROOT/'output').mkdir(exist_ok=True)
        (ROOT/'output'/'release_verification.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps({'status':'passed','checks':evidence['checks']},indent=2))
if __name__=='__main__':main()
