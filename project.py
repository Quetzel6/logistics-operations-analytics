"""Synthetic logistics decision-support demo. Python 3.10+, standard library only."""
from dashboard_view import enhance
from decision_report import decision_summary, markdown
import argparse
import csv
import html
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

AS_OF = date(2026, 10, 19)
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE trips(trip_id TEXT PRIMARY KEY, warehouse TEXT NOT NULL,
 route TEXT NOT NULL, dispatch_date TEXT NOT NULL, capacity_units INTEGER NOT NULL CHECK(capacity_units>0));
CREATE TABLE orders(order_id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips,
 due_date TEXT NOT NULL, delivered_date TEXT, ordered_units INTEGER NOT NULL CHECK(ordered_units>0),
 shipped_units INTEGER NOT NULL CHECK(shipped_units>=0 AND shipped_units<=ordered_units),
 issue TEXT NOT NULL);
'''

def generate(seed=42):
    rng = random.Random(seed)
    trips, orders = [], []
    for day in range(28):
        dispatch = AS_OF - timedelta(days=30-day)
        for warehouse in ('DC-A','DC-B','DC-C'):
            for route in ('Metro','Outer'):
                tid=f'T{len(trips)+1:04d}'
                trips.append((tid,warehouse,route,dispatch.isoformat(),1000))
                available=1000
                for _ in range(rng.randint(6,10)):
                    units=rng.randint(75,140)
                    shipped=min(units,available)
                    available-=shipped
                    due=dispatch+timedelta(days=1 if route=='Metro' else 2)
                    # Explicitly planted demonstration pattern, not a discovered real-world cause.
                    delay_prob=0.42 if warehouse=='DC-B' and route=='Outer' else 0.09
                    late=rng.random()<delay_prob
                    delivered=due+timedelta(days=rng.randint(1,3) if late else 0)
                    pending=delivered>AS_OF or rng.random()<0.025
                    issue='Dispatch exception' if late else ('Capacity shortfall' if shipped<units else 'None')
                    orders.append((f'O{len(orders)+1:05d}',tid,due.isoformat(),None if pending else delivered.isoformat(),units,shipped,issue))
    return trips,orders

METRICS_SQL='''
SELECT t.warehouse, t.route,
 COUNT(*) due_orders,
 SUM(CASE WHEN o.delivered_date IS NOT NULL AND o.delivered_date<=:as_of AND o.delivered_date<=o.due_date THEN 1 ELSE 0 END) on_time_orders,
 SUM(CASE WHEN o.delivered_date IS NOT NULL AND o.delivered_date<=:as_of AND o.delivered_date<=o.due_date
   AND o.shipped_units=o.ordered_units THEN 1 ELSE 0 END) otif_orders,
 SUM(CASE WHEN (o.delivered_date IS NULL OR o.delivered_date>:as_of) THEN 1 ELSE 0 END) overdue_open,
 SUM(o.ordered_units) ordered_units,SUM(o.shipped_units) shipped_units
FROM orders o JOIN trips t USING(trip_id)
WHERE o.due_date<=:as_of
GROUP BY t.warehouse,t.route ORDER BY t.warehouse,t.route
'''

def detail_report(conn, as_of):
    conn.row_factory=sqlite3.Row
    due=[]
    for row in conn.execute("SELECT o.*,t.warehouse,t.route FROM orders o JOIN trips t USING(trip_id) WHERE due_date<=? ORDER BY due_date,order_id",(as_of.isoformat(),)):
        r=dict(row)
        delivered=r['delivered_date'] if r['delivered_date'] and r['delivered_date']<=as_of.isoformat() else None
        r['delivered_date']=delivered
        r['on_time']=bool(delivered and delivered<=r['due_date'])
        r['otif']=r['on_time'] and r['shipped_units']==r['ordered_units']
        r['short_units']=r['ordered_units']-r['shipped_units']
        r['late_days']=max(0,((date.fromisoformat(delivered) if delivered else as_of)-date.fromisoformat(r['due_date'])).days)
        flags=[]
        if not delivered:flags.append('Overdue open')
        elif not r['on_time']:flags.append('Delivered late')
        if r['short_units']:flags.append('Short shipment')
        r['flags']=flags
        due.append(r)
    days={}
    for r in due:
        d=days.setdefault((r['due_date'],r['warehouse'],r['route']),{'due_date':r['due_date'],'warehouse':r['warehouse'],'route':r['route'],'due_orders':0,'on_time_orders':0,'otif_orders':0,'overdue_open':0})
        d['due_orders']+=1;d['on_time_orders']+=int(r['on_time']);d['otif_orders']+=int(r['otif']);d['overdue_open']+=int(r['delivered_date'] is None)
    return {'exceptions':sorted([r for r in due if r['flags']],key=lambda r:(-r['late_days'],r['order_id'])),'daily':list(days.values())}

def capacity_scenarios(conn, as_of):
    """Static per-trip upper bounds; no re-routing, delivery-time or cost inference."""
    conn.row_factory=sqlite3.Row
    trips=[dict(r) for r in conn.execute("""
        SELECT t.trip_id,t.warehouse,t.route,t.capacity_units,
          COALESCE(SUM(o.shipped_units),0) loaded_units,
          COALESCE(SUM(CASE WHEN o.due_date<=:as_of THEN o.ordered_units-o.shipped_units ELSE 0 END),0) due_short_units
        FROM trips t LEFT JOIN orders o USING(trip_id)
        WHERE t.dispatch_date<=:as_of
        GROUP BY t.trip_id,t.warehouse,t.route,t.capacity_units
        ORDER BY t.trip_id
    """,{'as_of':as_of.isoformat()})]
    def evaluate(rows, increment):
        capacity=sum(t['capacity_units'] for t in rows)
        extra=sum(t['capacity_units']*increment//100 for t in rows)
        recoverable=sum(min(t['due_short_units'],max(0,t['capacity_units']+t['capacity_units']*increment//100-t['loaded_units'])) for t in rows)
        return {'baseline_capacity_units':capacity,'added_capacity_units':extra,
                'due_short_units':sum(t['due_short_units'] for t in rows),
                'recoverable_units_upper_bound':recoverable,
                'remaining_short_units':sum(t['due_short_units'] for t in rows)-recoverable,
                'unused_added_capacity_units':extra-(recoverable-sum(min(t['due_short_units'],max(0,t['capacity_units']-t['loaded_units'])) for t in rows))}

    # Compare network-wide and cohort-targeted capacity without pooling capacity across trips.
    scopes=[('All network',trips)]+[(w+' / '+r,[t for t in trips if t['warehouse']==w and t['route']==r]) for w,r in sorted({(t['warehouse'],t['route']) for t in trips})]
    results=[]
    for scope,rows in scopes:
        base=evaluate(rows,0)['recoverable_units_upper_bound']
        for increment in (0,10,20):
            item=evaluate(rows,increment)
            item.update({'scope':scope,'capacity_increment_pct':increment,'incremental_recoverable_units':item['recoverable_units_upper_bound']-base})
            results.append(item)
    stress=[]
    for demand_pct in (0,10,20):
        demand=sum((t['loaded_units']+t['due_short_units'])*(100+demand_pct)//100 for t in trips)
        for increment in (0,10,20):
            short=sum(max(0,(t['loaded_units']+t['due_short_units'])*(100+demand_pct)//100-(t['capacity_units']+t['capacity_units']*increment//100)) for t in trips)
            stress.append({'demand_growth_pct':demand_pct,'capacity_increment_pct':increment,'modeled_demand_units':demand,'capacity_shortfall_units':short})
    return {'capacity_scenarios':results,'capacity_stress':stress}

def analyze(conn, as_of=AS_OF):
    conn.row_factory=sqlite3.Row
    violations=[]
    if conn.execute('PRAGMA foreign_key_check').fetchall():violations.append('foreign keys')
    overloaded=conn.execute('SELECT t.trip_id FROM trips t JOIN orders o USING(trip_id) GROUP BY t.trip_id HAVING SUM(o.shipped_units)>t.capacity_units').fetchall()
    if overloaded:violations.append('trip capacity')
    bad=conn.execute('SELECT COUNT(*) FROM orders o JOIN trips t USING(trip_id) WHERE due_date<dispatch_date OR (delivered_date IS NOT NULL AND delivered_date<dispatch_date)').fetchone()[0]
    if bad:violations.append('date sequence')
    if violations:raise ValueError('Data quality failed: '+', '.join(violations))
    cohorts=[]
    for row in conn.execute(METRICS_SQL,{'as_of':as_of.isoformat()}):
        r=dict(row)
        r['on_time_rate']=r['on_time_orders']/r['due_orders']
        r['otif_rate']=r['otif_orders']/r['due_orders']
        r['unit_fill_rate']=r['shipped_units']/r['ordered_units']
        # Capacity measured once per trip, never once per joined order.
        cap=conn.execute('SELECT SUM(capacity_units) FROM trips WHERE warehouse=? AND route=? AND dispatch_date<=?',(r['warehouse'],r['route'],as_of.isoformat())).fetchone()[0]
        load=conn.execute('SELECT SUM(shipped_units) FROM orders JOIN trips USING(trip_id) WHERE warehouse=? AND route=? AND dispatch_date<=?',(r['warehouse'],r['route'],as_of.isoformat())).fetchone()[0]
        r['trip_capacity_utilization']=load/cap if cap else None
        cohorts.append(r)
    totals={k:sum(r[k] for r in cohorts) for k in ('due_orders','on_time_orders','otif_orders','overdue_open','ordered_units','shipped_units')}
    totals['on_time_rate']=totals['on_time_orders']/totals['due_orders'] if totals['due_orders'] else None
    totals['otif_rate']=totals['otif_orders']/totals['due_orders'] if totals['due_orders'] else None
    totals['unit_fill_rate']=totals['shipped_units']/totals['ordered_units'] if totals['ordered_units'] else None
    # Threshold changes classify review workload; they do not simulate operational improvement.
    sensitivity=[]
    for threshold in (0.80,0.85,0.90,0.95):
        flagged=[r for r in cohorts if r['otif_rate']<threshold]
        sensitivity.append({'otif_threshold':threshold,'flagged_cohorts':len(flagged),'due_orders_in_flagged_cohorts':sum(r['due_orders'] for r in flagged)})
    return {'as_of':as_of.isoformat(),'data_type':'synthetic','totals':totals,'cohorts':cohorts,'threshold_sensitivity':sensitivity,'quality_gate':'passed',**detail_report(conn,as_of),**capacity_scenarios(conn,as_of)}

def render(report):
    esc=html.escape
    rows=''.join('<tr><td>'+esc(r['warehouse'])+'</td><td>'+esc(r['route'])+'</td><td>'+str(r['due_orders'])+'</td>'+''.join(f'<td>{r[k]:.1%}</td>' for k in ('on_time_rate','otif_rate','unit_fill_rate','trip_capacity_utilization'))+f"<td>{r['overdue_open']}</td></tr>" for r in report['cohorts'])
    worst=min(report['cohorts'],key=lambda r:r['otif_rate'])
    sensitivity=''.join(f"<tr><td>{r['otif_threshold']:.0%}</td><td>{r['flagged_cohorts']}</td><td>{r['due_orders_in_flagged_cohorts']}</td></tr>" for r in report['threshold_sensitivity'])
    t=report['totals']
    cards=''.join(f'<article><small>{label}</small><strong>{value}</strong></article>' for label,value in [('Due orders',str(t['due_orders'])),('On-time delivery',f"{t['on_time_rate']:.1%}"),('OTIF',f"{t['otif_rate']:.1%}"),('Overdue open',str(t['overdue_open']))])
    scenario_rows=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k in ('scope','capacity_increment_pct','added_capacity_units','incremental_recoverable_units','remaining_short_units','unused_added_capacity_units'))+'</tr>' for r in report['capacity_scenarios'])
    stress_rows=''.join('<tr>'+''.join('<td>'+str(r[k])+'</td>' for k in ('demand_growth_pct','capacity_increment_pct','modeled_demand_units','capacity_shortfall_units'))+'</tr>' for r in report['capacity_stress'])
    decision=decision_summary(report)
    decision_html='<section><h2>Decision brief: two different priorities</h2><p><b>Service investigation:</b> '+html.escape(decision['service_priority'])+' has the lowest observed OTIF ('+format(decision['service_otif'],'.1%')+'). Inspect dispatch and receiving evidence first.</p><p><b>Capacity candidate:</b> '+html.escape(decision['capacity_candidate'])+' has the highest modeled recovery per added capacity unit at +10%: '+str(decision['candidate_recoverable_upper_bound'])+' / '+str(decision['candidate_added_units'])+'. This is a retrospective upper-bound comparison, not ROI or evidence of delivery-time improvement.</p><p>Both selections use this synthetic snapshot. Validate on an independent period before changing policy. Full action register: <a href="decision_brief.md">decision_brief.md</a>.</p></section>'
    details=json.dumps({'exceptions':report['exceptions'],'daily':report['daily']}).replace('<','\\u003c')
    script=Path(__file__).with_name('dashboard.js').read_text()
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Logistics Operations Analytics</title>
<style>body{{font:16px system-ui;margin:auto;max-width:1150px;padding:32px;background:#f3f6fa;color:#17324d}}h1{{font-size:32px}}.tag{{color:#8b4612}}.cards{{display:flex;flex-wrap:wrap;gap:16px}}article{{background:white;padding:20px;min-width:170px;border-radius:12px}}strong{{display:block;font-size:30px}}section{{background:white;padding:24px;margin-top:24px;border-radius:12px;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dde4ed}}p{{line-height:1.6}}small{{color:#52677b}}</style>
<header><p class="tag">SYNTHETIC PORTFOLIO DEMO · NOT COMPANY DATA</p><h1>Logistics Operations Analytics</h1><p>Orders, delivery service and transport capacity · As of {report['as_of']} · Quality gate passed</p></header>
<div class="cards">{cards}</div>
<section><h2>Where should operations investigate first?</h2><p><b>{worst['warehouse']} / {worst['route']}</b> has the lowest observed OTIF ({worst['otif_rate']:.1%}). Review overdue orders and dispatch exceptions before changing vehicle capacity. This is a deliberately planted synthetic pattern, not evidence of real operational causation.</p></section>
<section><h2>Warehouse × route performance</h2><table><thead><tr><th>DC</th><th>Route</th><th>Due orders</th><th>On time</th><th>OTIF</th><th>Unit fill</th><th>Trip utilization</th><th>Overdue open</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>How sensitive is the review queue to the target?</h2><p>Changing the OTIF threshold changes the number of cohorts requiring review. It does not predict any delivery improvement.</p><table><thead><tr><th>Target</th><th>Flagged cohorts</th><th>Due orders covered</th></tr></thead><tbody>{sensitivity}</tbody></table></section>
<section><h2>Daily service and exception worklist</h2><p>Filters below affect this section only. Summary cards and cohort metrics above remain all-network. Daily rates are end-of-day snapshot outcomes grouped by promised date, not a historical daily snapshot.</p>
<label>Warehouse <select id="warehouse"><option value="">All</option><option>DC-A</option><option>DC-B</option><option>DC-C</option></select></label>
<label>Route <select id="route"><option value="">All</option><option>Metro</option><option>Outer</option></select></label>
<label>Exception <select id="issue"><option value="">All</option><option>Overdue open</option><option>Delivered late</option><option>Short shipment</option></select></label>
<p id="scope"></p><h3>Daily delivery performance</h3><p>Warehouse and route filters apply; exception filter applies only to the worklist. Rates use all due orders in the selected warehouse/route.</p>
<table><thead><tr><th>Due date</th><th>Due orders</th><th>On-time rate</th><th>OTIF rate</th><th>Overdue open</th></tr></thead><tbody id="daily"></tbody></table>
<h3>Exception worklist</h3><p>One row per order; multiple flags may apply. Recorded issue labels are synthetic, not verified root causes. Overdue age is measured at the snapshot; delivered-late age is actual lateness.</p><table><thead><tr><th>Order</th><th>DC / Route</th><th>Due / Delivered</th><th>Exception</th><th>Late days</th><th>Short units</th></tr></thead><tbody id="exceptions"></tbody></table>
</section><script id="detail-data" type="application/json">{details}</script><script>{script}</script>
<section><h2>Capacity scenarios: targeted versus network expansion</h2><p>Static upper bounds for recovering short-shipped units on the same trip. Scope applies to this table only. Every trip keeps its assigned orders; spare capacity cannot move between trips. Added capacity is rounded down per trip. Extra capacity is not the same as extra vehicles.</p><p><b>Assumptions:</b> stock, staff, loading time and receiving capacity are unconstrained; all due shortages can be reloaded onto their original trip. These are hypothetical pre-dispatch replays, not actions that can undo past shipments. No improvement in OTD/OTIF or monetary savings is estimated.</p><table><thead><tr><th>Scope</th><th>Capacity +%</th><th>Added units</th><th>Additional recoverable units</th><th>Remaining short units</th><th>Unused added units</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<h3>Stress test: higher demand on the same trips</h3><p>Modeled demand equals observed loaded units plus due shortages, then scales by 0/10/20%. This is not a demand forecast and does not model new trips, order deadlines or future-due shortages.</p><table><thead><tr><th>Demand +%</th><th>Capacity +%</th><th>Modeled units</th><th>Capacity shortfall</th></tr></thead><tbody>{stress_rows}</tbody></table>
<p><b>Decision guidance:</b> compare cohort-level recoverable units per added capacity unit before considering a network-wide change. Validate inventory, loading constraints, vehicle dimensions and actual operating costs first. A high upper bound identifies an investigation opportunity, not a guaranteed improvement.</p></section>
{decision_html}<section><h2>Definitions and limitations</h2><p>On-time and OTIF denominators include all orders due on or before the as-of date, including overdue undelivered orders. OTIF requires both on-time delivery and all ordered units shipped. Unit fill is shipped / ordered units for due orders. Trip utilization is shipped units / capacity summed once per dispatched trip; units are homogeneous capacity units, not weight or vehicle volume. The dispatch window is 28 days; no real GPS, labor, cost, inventory or causal evidence is included.</p></section></html>'''

    return enhance(page,report)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path('output'));ap.add_argument('--seed',type=int,default=42);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    trips,orders=generate(args.seed)
    db=args.output/'logistics.sqlite'
    if db.exists():db.unlink()
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.executemany('INSERT INTO trips VALUES(?,?,?,?,?)',trips)
        conn.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',orders)
        report=analyze(conn)
    for name,header,data in [('trips',['trip_id','warehouse','route','dispatch_date','capacity_units'],trips),('orders',['order_id','trip_id','due_date','delivered_date','ordered_units','shipped_units','issue'],orders)]:
        with (args.output/(name+'.csv')).open('w',newline='') as f:
            writer=csv.writer(f,lineterminator="\n");writer.writerow(header);writer.writerows(data)
    for name in ('exceptions','daily','capacity_scenarios','capacity_stress'):
        data=report[name]
        with (args.output/(name+'.csv')).open('w',newline='') as f:
            if data:
                writer=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator="\n")
                writer.writeheader()
                writer.writerows({k:('; '.join(v) if isinstance(v,list) else v) for k,v in row.items()} for row in data)
    (args.output/'decision_brief.md').write_text(markdown(report))
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    (args.output/'dashboard.html').write_text(render(report))
    print(json.dumps({'trips':len(trips),'orders':len(orders),'quality_gate':report['quality_gate'],'dashboard':str(args.output/'dashboard.html')},indent=2))

if __name__=='__main__':main()
