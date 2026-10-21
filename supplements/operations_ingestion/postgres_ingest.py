"""Transactional PostgreSQL backend for the existing operations-bundle-v1 contract."""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import uuid
from ingest import Invalid, VERSION, read_bundle

SCHEMA_NAME = 'ops_ingestion_lab'
OWNER = 'operations-postgres-lab-v1'
LOCK_ID = 861034271
FIELDS = {'orders': ('order_id', 'due_date', 'quantity'),
          'events': ('event_id', 'order_id', 'timestamp_utc', 'event_type'),
          'notes': ('note_id', 'order_id', 'raw_text', 'content_sha256')}
DDL = '''
CREATE SCHEMA ops_ingestion_lab;
CREATE TABLE ops_ingestion_lab.metadata (
 singleton boolean PRIMARY KEY CHECK(singleton), owner_marker text NOT NULL);
INSERT INTO ops_ingestion_lab.metadata VALUES(true,'operations-postgres-lab-v1');
CREATE TABLE ops_ingestion_lab.runs (
 run_id text PRIMARY KEY, contract text NOT NULL, fingerprint text NOT NULL,
 status text NOT NULL CHECK(status IN ('committed','rejected','duplicate')),
 started_utc timestamptz NOT NULL, finished_utc timestamptz NOT NULL,
 report_json jsonb NOT NULL);
CREATE UNIQUE INDEX ops_committed_bundle ON ops_ingestion_lab.runs(contract,fingerprint)
 WHERE status='committed';
CREATE TABLE ops_ingestion_lab.orders (
 order_id text PRIMARY KEY, due_date date NOT NULL,
 quantity bigint NOT NULL CHECK(quantity>0),
 source_run text NOT NULL REFERENCES ops_ingestion_lab.runs(run_id));
CREATE TABLE ops_ingestion_lab.events (
 event_id text PRIMARY KEY, order_id text NOT NULL REFERENCES ops_ingestion_lab.orders(order_id),
 timestamp_utc timestamptz NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('dispatched','delivered','exception')),
 source_run text NOT NULL REFERENCES ops_ingestion_lab.runs(run_id));
CREATE TABLE ops_ingestion_lab.notes (
 note_id text PRIMARY KEY, order_id text NOT NULL REFERENCES ops_ingestion_lab.orders(order_id),
 raw_text text NOT NULL, content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 source_run text NOT NULL REFERENCES ops_ingestion_lab.runs(run_id));
CREATE INDEX ops_event_order_recent ON ops_ingestion_lab.events(order_id,timestamp_utc DESC,event_id DESC);
CREATE INDEX ops_note_order ON ops_ingestion_lab.notes(order_id);
'''

class StorageError(Exception):
    """Safe machine code only; never include connection strings or server messages."""

class InjectedFailure(Exception):
    pass


def connect(dsn=None):
    try:
        import psycopg
    except ImportError:
        raise StorageError('postgres_driver_missing') from None
    value=dsn if dsn is not None else os.environ.get('OPERATIONS_DATABASE_URL','')
    if not value:
        raise StorageError('postgres_dsn_missing')
    try:
        conn=psycopg.connect(value,autocommit=True,connect_timeout=10)
        conn.execute("SET timezone='UTC'")
        conn.execute("SET statement_timeout='30s'")
        conn.execute("SET lock_timeout='10s'")
        return conn
    except psycopg.Error:
        raise StorageError('postgres_connection_failed') from None


def owned(conn):
    exists=conn.execute("SELECT to_regclass('ops_ingestion_lab.metadata')").fetchone()[0]
    if exists is None:
        raise StorageError('postgres_schema_not_owned')
    rows=conn.execute('SELECT singleton,owner_marker FROM ops_ingestion_lab.metadata').fetchall()
    if rows != [(True,OWNER)]:
        raise StorageError('postgres_schema_not_owned')


def initialize(conn):
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
        exists=conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',(SCHEMA_NAME,)).fetchone()
        if exists:
            owned(conn)
        else:
            conn.execute(DDL)


def typed(table,row):
    values=list(row)
    if table=='orders':values[1]=date.fromisoformat(values[1])
    if table=='events':values[2]=datetime.fromisoformat(values[2])
    return tuple(values)


def audit(conn, report, fingerprint, started):
    conn.execute('INSERT INTO ops_ingestion_lab.runs VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)',
        (report['run_id'],VERSION,fingerprint,report['status'],started,
         datetime.now(timezone.utc),json.dumps(report,sort_keys=True)))


def ingest_postgres(bundle,dsn=None,fail_after=None):
    import psycopg
    if fail_after is not None and (type(fail_after) is not int or fail_after<1):
        raise ValueError('invalid_failure_injection')
    started=datetime.now(timezone.utc)
    report=dict(contract=VERSION,backend='postgresql',run_id=uuid.uuid4().hex,
        data_class='caller-supplied; bundled fixtures are synthetic',status='rejected',
        issues=[],inserted={},unchanged={})
    fingerprint='validation_failed'
    try:
        tables,fingerprint=read_bundle(bundle)
    except Invalid as exc:
        tables=None;report['issues']=[exc.issue]
    report['fingerprint']=fingerprint
    try:
        with connect(dsn) as conn:
            initialize(conn)
            try:
                with conn.transaction():
                    # Serializes this backend's writers and replay/conflict decisions.
                    conn.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
                    owned(conn)
                    duplicate=None if tables is None else conn.execute(
                        "SELECT run_id FROM ops_ingestion_lab.runs WHERE contract=%s AND fingerprint=%s AND status='committed'",
                        (VERSION,fingerprint)).fetchone()
                    if duplicate:
                        report.update(status='duplicate',original_run_id=duplicate[0]);audit(conn,report,fingerprint,started)
                    elif tables is None:
                        audit(conn,report,fingerprint,started)
                    else:
                        # Placeholder and all entities are inside the SAME business transaction.
                        placeholder=dict(report,status='committed');audit(conn,placeholder,fingerprint,started)
                        inserted=0
                        for table,rows in tables.items():
                            fields=FIELDS[table];report['inserted'][table]=0;report['unchanged'][table]=0
                            for raw in rows:
                                row=typed(table,raw)
                                previous=conn.execute(f"SELECT {','.join(fields)} FROM ops_ingestion_lab.{table} WHERE {fields[0]}=%s",(row[0],)).fetchone()
                                if previous is not None:
                                    if previous!=row:raise Invalid('existing_id_content_conflict',table)
                                    report['unchanged'][table]+=1;continue
                                conn.execute(f"INSERT INTO ops_ingestion_lab.{table} VALUES ({','.join(['%s']*(len(row)+1))})",(*row,report['run_id']))
                                inserted+=1;report['inserted'][table]+=1
                                if fail_after is not None and inserted>=fail_after:raise InjectedFailure()
                        report['status']='committed'
                        conn.execute('UPDATE ops_ingestion_lab.runs SET finished_utc=%s,report_json=%s::jsonb WHERE run_id=%s',
                            (datetime.now(timezone.utc),json.dumps(report,sort_keys=True),report['run_id']))
            except (Invalid,psycopg.IntegrityError,psycopg.DataError,InjectedFailure) as exc:
                # Business transaction already rolled back. Preserve only a rejection audit.
                report.update(status='rejected',inserted={},unchanged={})
                report['issues']=[exc.issue if isinstance(exc,Invalid) else dict(
                    code='injected_failure' if isinstance(exc,InjectedFailure) else 'database_constraint_or_value_failed',source='database',row=None)]
                with conn.transaction():
                    conn.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,));owned(conn)
                    audit(conn,report,fingerprint,started)
    except psycopg.Error:
        raise StorageError('postgres_storage_failed') from None
    return report


def snapshot(conn):
    return {t:conn.execute(f'SELECT * FROM ops_ingestion_lab.{t} ORDER BY 1').fetchall() for t in FIELDS}


def snapshot_postgres(dsn=None):
    import psycopg
    try:
        with connect(dsn) as c, c.transaction():
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');owned(c)
            return snapshot(c)
    except psycopg.Error:
        raise StorageError('postgres_storage_failed') from None


def reconcile_postgres(bundle,dsn=None):
    import psycopg
    tables,fingerprint=read_bundle(bundle)
    try:
        with connect(dsn) as c, c.transaction():
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');owned(c)
            for table,rows in tables.items():
                fields=FIELDS[table]
                for raw in rows:
                    row=typed(table,raw)
                    observed=c.execute(f"SELECT {','.join(fields)} FROM ops_ingestion_lab.{table} WHERE {fields[0]}=%s",(row[0],)).fetchone()
                    if observed!=row:raise StorageError('source_database_mismatch')
            return dict(fingerprint=fingerprint,matched_bundle_rows={t:len(r) for t,r in tables.items()},
                database_rows={t:c.execute(f'SELECT COUNT(*) FROM ops_ingestion_lab.{t}').fetchone()[0] for t in FIELDS},
                scope='Exact bundle rows in one read-only snapshot; not external data truth')
    except psycopg.Error:
        raise StorageError('postgres_storage_failed') from None


def report_postgres(dsn=None):
    import psycopg
    try:
        with connect(dsn) as c, c.transaction():
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');owned(c)
            total=c.execute('SELECT COUNT(*),COALESCE(SUM(quantity),0) FROM ops_ingestion_lab.orders').fetchone()
            rows=c.execute('''SELECT o.order_id,o.due_date::text,o.quantity,
              (SELECT COUNT(*) FROM ops_ingestion_lab.events e WHERE e.order_id=o.order_id),
              (SELECT COUNT(*) FROM ops_ingestion_lab.notes n WHERE n.order_id=o.order_id)
              FROM ops_ingestion_lab.orders o ORDER BY o.order_id''').fetchall()
            counts={t:c.execute(f'SELECT COUNT(*) FROM ops_ingestion_lab.{t}').fetchone()[0] for t in ('events','notes')}
            version=c.execute('SELECT version()').fetchone()[0]
        return dict(backend='postgresql',postgres_version=version,order_count=total[0],quantity_total=int(total[1]),
            event_count=counts['events'],note_count=counts['notes'],
            orders=[dict(zip(('order_id','due_date','quantity','events','notes'),r)) for r in rows],
            brief_sample=[],briefing_scope='PostgreSQL report only; no assistant or model invoked')
    except psycopg.Error:
        raise StorageError('postgres_storage_failed') from None

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);a=parser.parse_args()
    try:result=ingest_postgres(a.bundle)
    except (StorageError,ImportError):
        print(json.dumps(dict(status='failed',error_code='postgres_unavailable_or_unowned')));raise SystemExit(2)
    print(json.dumps(result,indent=2));raise SystemExit(1 if result['status']=='rejected' else 0)
