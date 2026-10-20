"""Local sequential orchestration; no API calls and no Airflow dependency."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import sqlite3
import time
import uuid
from assistant import brief
from ingest import ingest, read_bundle

STAGES=('ingest','reconcile','replay_check','report')
OWNER='operations-pipeline-v1'

class PipelineError(Exception):pass


def now():return datetime.now(timezone.utc).isoformat()


def open_readonly(db):
    conn=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True)
    conn.execute('PRAGMA query_only=ON')
    return conn


def reconcile(bundle,db):
    tables,fingerprint=read_bundle(bundle)
    columns={'orders':('order_id','due_date','quantity'),
             'events':('event_id','order_id','timestamp_utc','event_type'),
             'notes':('note_id','order_id','raw_text','content_sha256')}
    with open_readonly(db) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise PipelineError('sqlite_integrity_failed')
        if c.execute('PRAGMA foreign_key_check').fetchall():raise PipelineError('foreign_keys_failed')
        matched={}
        for table,rows in tables.items():
            fields=columns[table]
            for row in rows:
                observed=c.execute(f"SELECT {','.join(fields)} FROM {table} WHERE {fields[0]}=?",(row[0],)).fetchone()
                if observed!=row:raise PipelineError('source_database_mismatch')
            matched[table]=len(rows)
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in columns}
    return dict(fingerprint=fingerprint,matched_bundle_rows=matched,database_rows=counts,
                validation='exact input-bundle rows, integrity and foreign keys; not real-world correctness')


def business_snapshot(db):
    with open_readonly(db) as c:
        return {t:c.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in ('orders','events','notes')}


def replay(bundle,db):
    before=business_snapshot(db)
    result=ingest(bundle,db)
    if result['status']!='duplicate' or business_snapshot(db)!=before:
        raise PipelineError('replay_changed_business_rows')
    return dict(status='duplicate',business_rows_unchanged=True,audit_entry_added=True)


def report_data(db):
    # Separate aggregates avoid multiplying quantity through event/note joins.
    with open_readonly(db) as c:
        total=c.execute('SELECT COUNT(*),COALESCE(SUM(quantity),0) FROM orders').fetchone()
        rows=c.execute('''SELECT o.order_id,o.due_date,o.quantity,
            (SELECT COUNT(*) FROM events e WHERE e.order_id=o.order_id),
            (SELECT COUNT(*) FROM notes n WHERE n.order_id=o.order_id)
            FROM orders o ORDER BY o.order_id''').fetchall()
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('events','notes')}
    briefs=[brief(db,row[0],mode='baseline') for row in rows[:25]]
    return dict(order_count=total[0],quantity_total=total[1],event_count=counts['events'],note_count=counts['notes'],
        orders=[dict(zip(('order_id','due_date','quantity','events','notes'),row)) for row in rows],
        brief_sample=[dict(order_id=r['order_id'],record_status=r['record_status'],warnings=r['warnings']) for r in briefs],
        briefing_scope='first 25 order IDs only; deterministic baseline, not GenAI')


def render_report(data,run_id):
    esc=lambda x:html.escape(str(x),quote=True)
    rows=''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in ('order_id','due_date','quantity','events','notes'))+'</tr>' for r in data['orders'])
    sample=''.join('<tr><td>'+esc(r['order_id'])+'</td><td>'+esc(r['record_status'])+'</td><td>'+esc(', '.join(r['warnings']) or 'None')+'</td></tr>' for r in data['brief_sample'])
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Operations pipeline report</title>
<style>body{font:16px/1.5 system-ui,sans-serif;color:#183c4c;background:#f1f5f6;margin:0}main{max-width:1050px;margin:auto;padding:36px 24px}h1{font-size:32px;line-height:1.2}.cards{display:flex;flex-wrap:wrap;gap:12px}.card{background:white;padding:18px;flex:1;min-width:140px;border-top:4px solid #168187}.card strong{display:block;font-size:30px}section{background:white;padding:20px;margin-top:22px;overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #dce5e7}small{color:#4c6470}code{overflow-wrap:anywhere}</style><main>
<p>LOCAL PIPELINE / REVIEW REPORT</p><h1>From mixed files to reconciled operations data</h1>
<p>CSV orders, JSONL events and original text notes. No API calls. Generated report for human review.</p>
<div class="cards">'''+''.join('<div class="card"><strong>'+esc(data[k])+'</strong>'+label+'</div>' for k,label in [('order_count','Orders'),('quantity_total','Ordered units'),('event_count','Events'),('note_count','Text notes')])+'''</div>
<section><h2>Database snapshot</h2><p>All accumulated orders in this pipeline database. Events and notes are counted separately to preserve quantity totals.</p><table><thead><tr><th>Order</th><th>Due date</th><th>Quantity</th><th>Events</th><th>Notes</th></tr></thead><tbody>'''+rows+'''</tbody></table></section>
<section><h2>Baseline review sample</h2><p>First 25 order IDs. Status describes recorded evidence, not confirmed recipient acceptance or root cause.</p><table><thead><tr><th>Order</th><th>Record status</th><th>Warnings</th></tr></thead><tbody>'''+sample+'''</tbody></table></section>
<section><h2>Evidence and limits</h2><p>See pipeline_run.json for stage outcomes and source hashes. See data_report.json for exact values. Input rows reconcile with storage; this does not prove external data truth or operational benefit. Notes remain untrusted. No ML, GenAI, remote CI or Airflow execution is implied.</p><small>Run: <code>'''+esc(run_id)+'''</code></small></section></main></html>'''


def run_pipeline(bundle,output):
    bundle=Path(bundle).resolve();root=Path(output).resolve()
    if root==bundle or root in bundle.parents or bundle in root.parents:
        raise PipelineError('input_output_paths_overlap')
    root.mkdir(parents=True,exist_ok=True)
    marker=root/'.pipeline-owner'
    if marker.exists():
        if marker.is_symlink() or marker.read_text()!=OWNER:raise PipelineError('unrecognized_output_directory')
    else:
        if any(root.iterdir()):raise PipelineError('output_directory_not_empty')
        marker.write_text(OWNER)
    db=root/'pipeline.sqlite'
    if db.is_symlink():raise PipelineError('database_symlink_not_allowed')
    rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    dest=root/'runs'/rid;dest.mkdir(parents=True)
    metadata=dict(run_id=rid,status='running',started_utc=now(),python=platform.python_version(),
        platform=platform.system(),api_calls=0,orchestrator='custom local sequential runner; not Airflow',
        input_label='caller-supplied; bundled fixtures are synthetic',
        stages=[dict(name=s,status='pending') for s in STAGES],
        source_sha256={p:hashlib.sha256((Path(__file__).parent/p).read_bytes()).hexdigest() for p in ('pipeline.py','ingest.py','assistant.py')})
    failed=False
    for stage in metadata['stages']:
        if failed:stage['status']='skipped';continue
        start=time.monotonic();stage.update(status='running',started_utc=now())
        try:
            if stage['name']=='ingest':
                result=ingest(bundle,db)
                if result['status']=='rejected':
                    stage['issues']=result['issues'];raise PipelineError('ingestion_rejected')
            elif stage['name']=='reconcile':result=reconcile(bundle,db)
            elif stage['name']=='replay_check':result=replay(bundle,db)
            else:
                result=report_data(db)
                (dest/'data_report.json').write_text(json.dumps(result,indent=2)+'\n')
                (dest/'report.html').write_text(render_report(result,rid))
                result=dict(order_count=result['order_count'],quantity_total=result['quantity_total'],report='report.html')
            stage.update(status='passed',result=result)
        except Exception as exc:
            # Do not publish arbitrary exception strings, paths, SQL or note content.
            allowed={'ingestion_rejected','source_database_mismatch','sqlite_integrity_failed','foreign_keys_failed','replay_changed_business_rows'}
            code=str(exc) if isinstance(exc,PipelineError) and str(exc) in allowed else 'stage_failed'
            stage.update(status='failed',error_code=code);failed=True
        stage.update(finished_utc=now(),duration_ms=round((time.monotonic()-start)*1000,2))
        (dest/'pipeline_run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    metadata.update(status='failed' if failed else 'passed_local',finished_utc=now())
    (dest/'pipeline_run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata,dest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result,path=run_pipeline(args.bundle,args.output)
        print(json.dumps(dict(status=result['status'],run_dir=str(path),api_calls=0,
            stages=[dict(name=s['name'],status=s['status']) for s in result['stages']]),indent=2))
        raise SystemExit(0 if result['status']=='passed_local' else 1)
    except (PipelineError,OSError):
        print(json.dumps(dict(status='failed',error_code='output_unavailable_or_not_owned')))
        raise SystemExit(2)
