"""Load validated mixed-format bundles into PostgreSQL and reconcile/report offline."""
import argparse
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import time
import uuid
from postgres_ingest import (ingest_postgres,reconcile_postgres,report_postgres,
                             snapshot_postgres,StorageError)

OWNER='operations-postgres-pipeline-v1'

def render_report(data,rid):
    esc=lambda value:html.escape(str(value),quote=True)
    rows=''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in ('order_id','due_date','quantity','events','notes'))+'</tr>' for r in data['orders'])
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>PostgreSQL operations pipeline</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:32px auto;padding:20px;color:#173e4b}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ccd}code{overflow-wrap:anywhere}</style>'
        '<h1>PostgreSQL operations pipeline</h1><p>CSV orders, JSONL events and original text notes. Contract validation, exact reconciliation and replay checks. No API or model calls.</p>'
        '<p>Orders: '+esc(data['order_count'])+' | Ordered units: '+esc(data['quantity_total'])+' | Events: '+esc(data['event_count'])+' | Notes: '+esc(data['note_count'])+'</p>'
        '<table><tr><th>Order</th><th>Due date</th><th>Quantity</th><th>Events</th><th>Notes</th></tr>'+rows+'</table>'
        '<h2>Scope</h2><p>Counts describe stored source records, not actual delivery or verified root cause. Quantities are aggregated at order grain. This PostgreSQL report does not invoke the separate SQLite assistant.</p>'
        '<p><a href="pipeline_run.json">Stage results</a> | <a href="data_report.json">Exact values</a></p><p>Run: <code>'+esc(rid)+'</code></p></html>')


def run_pipeline(bundle,output,dsn=None):
    bundle=Path(bundle).resolve();root=Path(output).resolve()
    if root==bundle or root in bundle.parents or bundle in root.parents:raise StorageError('input_output_paths_overlap')
    root.mkdir(parents=True,exist_ok=True);marker=root/'.postgres-pipeline-owner'
    if marker.exists():
        if marker.is_symlink() or marker.read_text()!=OWNER:raise StorageError('output_not_owned')
    else:
        if any(root.iterdir()):raise StorageError('output_not_empty')
        marker.write_text(OWNER)
    rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    dest=root/'runs'/rid;dest.mkdir(parents=True)
    metadata=dict(run_id=rid,status='running',backend='postgresql',api_calls=0,
        python=platform.python_version(),platform=platform.system(),
        scope='Contract-validated local PostgreSQL lab; custom sequential runner, no Airflow or model calls',
        source_sha256={p:hashlib.sha256((Path(__file__).parent/p).read_bytes()).hexdigest() for p in ('ingest.py','postgres_ingest.py','postgres_pipeline.py')},
        stages=[dict(name=n,status='pending') for n in ('ingest','reconcile','replay_check','report')])
    failed=False
    for stage in metadata['stages']:
        if failed:stage['status']='skipped';continue
        start=time.monotonic()
        try:
            if stage['name']=='ingest':
                result=ingest_postgres(bundle,dsn)
                if result['status']=='rejected':
                    stage['issues']=result['issues'];raise StorageError('ingestion_rejected')
            elif stage['name']=='reconcile':result=reconcile_postgres(bundle,dsn)
            elif stage['name']=='replay_check':
                before=snapshot_postgres(dsn);again=ingest_postgres(bundle,dsn)
                if again['status']!='duplicate' or before!=snapshot_postgres(dsn):raise StorageError('replay_changed_business_rows')
                result=dict(status='duplicate',business_rows_unchanged=True)
            else:
                report=report_postgres(dsn)
                (dest/'data_report.json').write_text(json.dumps(report,indent=2)+'\n')
                (dest/'report.html').write_text(render_report(report,rid))
                result=dict(order_count=report['order_count'],quantity_total=report['quantity_total'],report='report.html')
            stage.update(status='passed',result=result)
        except Exception as exc:
            allowed={'ingestion_rejected','source_database_mismatch','replay_changed_business_rows','postgres_connection_failed','postgres_storage_failed','postgres_dsn_missing','postgres_driver_missing','postgres_schema_not_owned'}
            stage.update(status='failed',error_code=str(exc) if isinstance(exc,StorageError) and str(exc) in allowed else 'stage_failed');failed=True
        stage['duration_ms']=round((time.monotonic()-start)*1000,2)
        (dest/'pipeline_run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    metadata['status']='failed' if failed else 'passed_local'
    (dest/'pipeline_run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata,dest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        r,path=run_pipeline(a.bundle,a.output)
    except (OSError,StorageError):
        print(json.dumps(dict(status='failed',error_code='output_unavailable_or_not_owned')));raise SystemExit(2)
    print(json.dumps(dict(status=r['status'],run_dir=str(path),api_calls=0,stages=[dict(name=s['name'],status=s['status']) for s in r['stages']]),indent=2))
    raise SystemExit(0 if r['status']=='passed_local' else 1)
