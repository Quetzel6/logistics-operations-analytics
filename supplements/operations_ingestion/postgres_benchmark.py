"""Disposable PostgreSQL 16 lab via Docker; no host ports or existing databases."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import secrets
import statistics
import subprocess
import time
import uuid

MODEL='''
CREATE TABLE orders (
 order_id bigint PRIMARY KEY,
 due_date date NOT NULL,
 quantity integer NOT NULL CHECK (quantity>0));
CREATE TABLE events (
 event_id bigint PRIMARY KEY,
 order_id bigint NOT NULL REFERENCES orders(order_id),
 timestamp_utc timestamptz NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('dispatched','delivered','exception')));
CREATE TABLE notes (
 note_id bigint PRIMARY KEY,
 order_id bigint NOT NULL REFERENCES orders(order_id),
 raw_text text NOT NULL);
'''
LOAD='''
INSERT INTO orders
 SELECT i, DATE '2026-10-01'+(i%28)::integer, (i%100+1)::integer
 FROM generate_series(1,50000) i;
INSERT INTO events
 SELECT i, ((i-1)%50000)+1,
 TIMESTAMPTZ '2026-10-01 00:00:00+00'+i*INTERVAL '1 second',
 CASE WHEN i%17=0 THEN 'exception' WHEN i%3=0 THEN 'delivered' ELSE 'dispatched' END
 FROM generate_series(1,200000) i;
INSERT INTO notes SELECT i,i,'SYNTHETIC: operator review requested.' FROM generate_series(1,1000) i;
ANALYZE;
'''
QUERY="SELECT event_id,timestamp_utc,event_type FROM events WHERE order_id=12345 ORDER BY timestamp_utc DESC,event_id DESC LIMIT 20"
INDEX='CREATE INDEX event_order_recent ON events(order_id,timestamp_utc DESC,event_id DESC); ANALYZE events;'

class BenchmarkError(Exception):pass

def run(output,image='postgres:16-alpine'):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    name='operations-pg-lab-'+uuid.uuid4().hex[:12]
    password=secrets.token_hex(24)
    def docker(args,data=None):
        try:
            r=subprocess.run(['docker',*args],input=data,text=True,capture_output=True,timeout=180)
        except (OSError,subprocess.TimeoutExpired):raise BenchmarkError('docker_unavailable_or_timeout') from None
        if r.returncode:raise BenchmarkError('docker_command_failed')
        return r.stdout.strip()
    def sql(text):
        return docker(['exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','lab','-d','operations_lab','-Atq'],text)
    started=False
    report=dict(status='failed',execution_platform=platform.system(),api_calls=0,
        started_utc=datetime.now(timezone.utc).isoformat(),
        scope='synthetic PostgreSQL microbenchmark in disposable local Docker; not production, warehouse scale, or SQLite migration')
    try:
        docker(['run','--detach','--rm','--name',name,'--label','portfolio.lab=operations-m4',
            '-e','POSTGRES_USER=lab','-e','POSTGRES_DB=operations_lab','-e','POSTGRES_PASSWORD='+password,image]);started=True
        for attempt in range(45):
            try:
                docker(['exec',name,'pg_isready','-h','127.0.0.1','-U','lab','-d','operations_lab']);break
            except BenchmarkError:
                if attempt==44:raise BenchmarkError('postgres_not_ready')
                time.sleep(1)
        report['postgres_version']=sql('SELECT version();')
        report['image_id']=docker(['inspect','--format','{{.Image}}',name])
        sql('SET standard_conforming_strings=on;'+MODEL+LOAD)
        report['counts']=json.loads(sql("SELECT json_build_object('orders',(SELECT COUNT(*) FROM orders),'events',(SELECT COUNT(*) FROM events),'notes',(SELECT COUNT(*) FROM notes),'quantity_total',(SELECT SUM(quantity) FROM orders));"))
        assert report['counts']==dict(orders=50000,events=200000,notes=1000,quantity_total=2525000)
        # Warm each arm once; seven measurements per arm. SQL plan execution times exclude Docker/client overhead.
        def measure():
            sql(QUERY+';')
            plans=[json.loads(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+QUERY+';'))[0] for _ in range(7)]
            result=sql(QUERY+';')
            return dict(execution_ms=[p['Execution Time'] for p in plans],
                median_execution_ms=statistics.median(p['Execution Time'] for p in plans),
                representative_plan=plans[3],result_sha256=hashlib.sha256(result.encode()).hexdigest(),result_rows=len(result.splitlines()))
        report['before']=measure();sql(INDEX);report['after']=measure()
        expected="SELECT event_id,timestamp_utc,event_type FROM events WHERE event_id IN (12345,62345,112345,162345) ORDER BY timestamp_utc DESC,event_id DESC"
        expected_hash=hashlib.sha256(sql(expected+';').encode()).hexdigest()
        if report['before']['result_sha256']!=expected_hash or report['after']['result_sha256']!=expected_hash:
            raise BenchmarkError('query_result_mismatch')
        # Only the expected SQLSTATE is accepted; connection failures cannot pass this check.
        sql("""DO $block$ BEGIN
          BEGIN INSERT INTO orders VALUES(999999,'2026-10-01',0);
            RAISE EXCEPTION 'constraint_not_enforced';
          EXCEPTION WHEN check_violation THEN NULL; END;
          BEGIN INSERT INTO events VALUES(999999,999999,now(),'exception');
            RAISE EXCEPTION 'constraint_not_enforced';
          EXCEPTION WHEN foreign_key_violation THEN NULL; END;
          BEGIN INSERT INTO events VALUES(999999,1,now(),'invented');
            RAISE EXCEPTION 'constraint_not_enforced';
          EXCEPTION WHEN check_violation THEN NULL; END;
        END $block$;""")
        report.update(status='passed_local',results_match_expected=True,constraint_rejections=3,
            query=QUERY,index=INDEX,
            timing_limitations='Warm-cache arms always before then after; seven repetitions each, no randomized crossover, no concurrency. No general speedup claim.')
        return report
    finally:
        if started:
            try:docker(['rm','--force',name]);report['container_removed']=True
            except BenchmarkError:report['container_removed']=False
        (out/'postgres_benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'schema_and_load.sql').write_text(MODEL+LOAD+'\n-- Measured query\n'+QUERY+';\n'+INDEX+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--image',default='postgres:16-alpine');a=p.parse_args()
    try:
        r=run(a.output,a.image)
    except (BenchmarkError,OSError,AssertionError,ValueError) as e:
        p.exit(1,('Benchmark failed: '+str(e)+'\n') if isinstance(e,BenchmarkError) else 'Benchmark failed; inspect report.\n')
    print(json.dumps(dict(status=r['status'],counts=r['counts'],before_median_ms=r['before']['median_execution_ms'],after_median_ms=r['after']['median_execution_ms'],results_match_expected=r['results_match_expected'],container_removed=r['container_removed']),indent=2))
