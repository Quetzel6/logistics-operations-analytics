"""Real integration acceptance. Requires a disposable operations_test_* database."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from postgres_ingest import connect,StorageError
from postgres_pipeline import run_pipeline

ROOT=Path(__file__).resolve().parent

def verify(output):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    dsn=os.environ.get('OPERATIONS_TEST_DSN','')
    if not dsn:raise StorageError('postgres_test_dsn_missing')
    with connect(dsn) as c:
        if not c.execute('SELECT current_database()').fetchone()[0].startswith('operations_test_'):
            raise StorageError('refusing_non_test_database')
        version=c.execute('SELECT version()').fetchone()[0]
    result=dict(status='failed',backend='postgresql',python=platform.python_version(),platform=platform.system(),
        postgres_version=version,api_calls=0,scope='Actual integration on this host; dedicated test schema is reset by tests. No cloud, model or production verification.')
    # This subprocess receives a test DSN but emits no connection string itself.
    completed=subprocess.run([sys.executable,'-m','unittest','discover','-s','postgres_tests','-v'],
        cwd=ROOT,capture_output=True,text=True,timeout=240)
    log=(completed.stdout+completed.stderr).replace(dsn,'[test database URL]')
    (out/'postgres_tests.txt').write_text(log)
    match=re.search(r'Ran (\d+) tests?',log)
    result.update(integration_tests=int(match.group(1)) if match else 0,
        tests_success=completed.returncode==0,skipped_detected=bool(re.search(r'\bskipped\b',log)))
    try:
        if completed.returncode or result['integration_tests']<16 or result['skipped_detected']:
            raise StorageError('postgres_integration_tests_failed_or_skipped')
        first,p1=run_pipeline(ROOT/'fixtures',out/'demo',dsn)
        second,p2=run_pipeline(ROOT/'fixtures',out/'demo',dsn)
        if first['status']!='passed_local' or second['status']!='passed_local':raise StorageError('postgres_demo_failed')
        if second['stages'][0]['result']['status']!='duplicate':raise StorageError('postgres_demo_replay_failed')
        data=json.loads((p1/'data_report.json').read_text())
        if (data['order_count'],data['quantity_total'],data['event_count'],data['note_count'])!=(3,225,3,2):
            raise StorageError('postgres_demo_totals_failed')
        import psycopg
        result.update(status='passed_local',psycopg_version=psycopg.__version__,
            first_run_status=first['stages'][0]['result']['status'],second_run_status='duplicate',
            row_counts=dict(orders=3,events=3,notes=2),order_quantity_total=225,
            first_report=str(p1.relative_to(out)/'report.html'),second_report=str(p2.relative_to(out)/'report.html'))
        return result
    finally:
        (out/'postgres_acceptance.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:r=verify(a.output)
    except (StorageError,OSError,ImportError,subprocess.TimeoutExpired):
        print(json.dumps(dict(status='failed',error_code='postgres_acceptance_unavailable_or_failed')));raise SystemExit(1)
    print(json.dumps(r,indent=2))
