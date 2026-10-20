"""Explicit-contract, append-only ingestion lab. Python 3.10+, stdlib only."""
import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

VERSION = 'operations-bundle-v1'
MAX_BYTES = 5_000_000
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, contract TEXT NOT NULL, fingerprint TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('committed','rejected','duplicate')),
 started_utc TEXT NOT NULL, finished_utc TEXT NOT NULL, report_json TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS committed_bundle ON runs(contract,fingerprint) WHERE status='committed';
CREATE TABLE IF NOT EXISTS orders (
 order_id TEXT PRIMARY KEY, due_date TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0),
 source_run TEXT NOT NULL REFERENCES runs(run_id));
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(order_id),
 timestamp_utc TEXT NOT NULL, event_type TEXT NOT NULL,
 source_run TEXT NOT NULL REFERENCES runs(run_id));
CREATE TABLE IF NOT EXISTS notes (
 note_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(order_id),
 raw_text TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 source_run TEXT NOT NULL REFERENCES runs(run_id));
CREATE INDEX IF NOT EXISTS event_order_time ON events(order_id,timestamp_utc);
CREATE INDEX IF NOT EXISTS note_order ON notes(order_id);
'''

class Invalid(Exception):
    def __init__(self, code, source, row=None):
        self.issue = dict(code=code, source=source, row=row)


def identifier(value, source, row):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Invalid('invalid_identifier', source, row)
    return value


def keys(row, expected, source, line):
    if not isinstance(row, dict) or set(row) != set(expected):
        raise Invalid('schema_mismatch', source, line)


def read_bundle(root):
    root = Path(root).resolve()
    files = {}
    def read(name):
        if not isinstance(name, str):
            raise Invalid('invalid_path', 'manifest')
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root):
            raise Invalid('path_outside_bundle', 'manifest')
        try:
            if path.stat().st_size > MAX_BYTES:
                raise Invalid('file_too_large', name)
            raw = path.read_bytes()
            if len(raw) > MAX_BYTES:
                raise Invalid('file_too_large', name)
            value = raw.decode('utf-8-sig')
        except (OSError, UnicodeError):
            raise Invalid('unreadable_utf8_file', name) from None
        files[name] = raw
        return value
    try:
        manifest = json.loads(read('manifest.json'))
    except json.JSONDecodeError:
        raise Invalid('invalid_json', 'manifest.json') from None
    keys(manifest, ['contract','orders','events','notes'], 'manifest.json', None)
    if manifest['contract'] != VERSION:
        raise Invalid('unsupported_contract','manifest.json')
    if not isinstance(manifest['notes'], list) or len(manifest['notes']) > 1000:
        raise Invalid('invalid_notes_manifest','manifest.json')
    order_source = manifest['orders']
    reader = csv.DictReader(io.StringIO(read(order_source)))
    if reader.fieldnames != ['order_id','due_date','quantity']:
        raise Invalid('schema_mismatch',order_source,1)
    orders=[]
    try:
        for i, row in enumerate(reader,2):
            keys(row,['order_id','due_date','quantity'],order_source,i)
            oid=identifier(row['order_id'],order_source,i)
            try:
                d = date.fromisoformat(row['due_date'])
                if d.isoformat()!=row['due_date']: raise ValueError()
                if not re.fullmatch(r'[1-9][0-9]*',row['quantity']): raise ValueError()
                qty=int(row['quantity'])
                if qty > 2**63-1: raise ValueError()
            except (ValueError,TypeError):
                raise Invalid('invalid_order_date_or_quantity',order_source,i) from None
            orders.append((oid,d.isoformat(),qty))
    except csv.Error:
        raise Invalid('malformed_csv',order_source) from None
    events=[]
    for i,line in enumerate(read(manifest['events']).splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError: raise Invalid('invalid_json',manifest['events'],i) from None
        keys(row,['event_id','order_id','timestamp_utc','event_type'],manifest['events'],i)
        eid=identifier(row['event_id'],manifest['events'],i)
        oid=identifier(row['order_id'],manifest['events'],i)
        try:
            ts=datetime.fromisoformat(row['timestamp_utc'].replace('Z','+00:00'))
            if ts.tzinfo is None: raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise Invalid('invalid_aware_timestamp',manifest['events'],i) from None
        if row['event_type'] not in ('dispatched','delivered','exception'):
            raise Invalid('unknown_event_type',manifest['events'],i)
        events.append((eid,oid,ts.astimezone(timezone.utc).isoformat(),row['event_type']))
    notes=[]
    for i,entry in enumerate(manifest['notes'],1):
        keys(entry,['note_id','order_id','path'],'manifest.json',i)
        nid=identifier(entry['note_id'],'manifest.json',i)
        oid=identifier(entry['order_id'],'manifest.json',i)
        content=read(entry['path'])
        if not content.strip(): raise Invalid('empty_note',entry['path'])
        notes.append((nid,oid,content,hashlib.sha256(content.encode()).hexdigest()))
    for label,rows in [('orders',orders),('events',events),('notes',notes)]:
        if len({r[0] for r in rows}) != len(rows):
            raise Invalid('duplicate_id_in_bundle',label)
    digest=hashlib.sha256()
    digest.update(VERSION.encode())
    for name,raw in sorted(files.items()):
        digest.update(json.dumps([name,len(raw),hashlib.sha256(raw).hexdigest()],separators=(',',':')).encode())
    return dict(orders=orders,events=events,notes=notes), digest.hexdigest()


def ingest(bundle, database, fail_after=None):
    """All-or-nothing bundle; conflicts reject, identical entity replay skips."""
    started=datetime.now(timezone.utc).isoformat()
    run_id=uuid.uuid4().hex
    report={'contract':VERSION,'run_id':run_id,'data_class':'caller-supplied; bundled fixtures are synthetic',
            'status':'rejected','issues':[], 'inserted':{},'unchanged':{}}
    fingerprint='validation_failed'
    try:
        tables,fingerprint=read_bundle(bundle)
    except Invalid as exc:
        report['issues']=[exc.issue]
        tables=None
    db=Path(database)
    db.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(db,isolation_level=None) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')
        conn.executescript(SCHEMA)
        try:
            conn.execute('BEGIN IMMEDIATE')
            if tables is not None:
                duplicate=conn.execute("SELECT run_id FROM runs WHERE contract=? AND fingerprint=? AND status='committed'",(VERSION,fingerprint)).fetchone()
                if duplicate:
                    report['status']='duplicate'
                    report['original_run_id']=duplicate[0]
                else:
                    # Insert placeholder inside transaction to satisfy row provenance foreign keys.
                    conn.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(run_id,VERSION,fingerprint,'committed',started,started,'{}'))
                    columns={'orders':('order_id','due_date','quantity'),
                             'events':('event_id','order_id','timestamp_utc','event_type'),
                             'notes':('note_id','order_id','raw_text','content_sha256')}
                    count=0
                    for table,rows in tables.items():
                        fields=columns[table]
                        report['inserted'][table]=0;report['unchanged'][table]=0
                        for row in rows:
                            # Table and column identifiers are internal constants, never user input.
                            previous=conn.execute(f"SELECT {','.join(fields)} FROM {table} WHERE {fields[0]}=?",(row[0],)).fetchone()
                            if previous is not None:
                                if previous!=row: raise Invalid('existing_id_content_conflict',table)
                                report['unchanged'][table]+=1
                                continue
                            conn.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(len(row)+1))})",(*row,run_id))
                            count+=1;report['inserted'][table]+=1
                            if fail_after is not None and count >= fail_after:
                                raise RuntimeError('test-only injected failure')
                    report['status']='committed'
            finished=datetime.now(timezone.utc).isoformat()
            report['fingerprint']=fingerprint
            payload=json.dumps(report,sort_keys=True)
            if report['status']=='committed':
                conn.execute('UPDATE runs SET finished_utc=?,report_json=? WHERE run_id=?',(finished,payload,run_id))
            else:
                conn.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(run_id,VERSION,fingerprint,report['status'],started,finished,payload))
            conn.commit()
        except (Invalid,sqlite3.IntegrityError,RuntimeError) as exc:
            conn.rollback()
            report['status']='rejected';report['inserted']={};report['unchanged']={}
            report['issues']=[exc.issue if isinstance(exc,Invalid) else dict(code='relational_constraint_failed' if isinstance(exc,sqlite3.IntegrityError) else 'injected_failure',source='database',row=None)]
            report['fingerprint']=fingerprint
            conn.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(run_id,VERSION,fingerprint,'rejected',started,datetime.now(timezone.utc).isoformat(),json.dumps(report,sort_keys=True)))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=ingest(args.bundle,args.database)
    except (OSError,sqlite3.Error):
        print(json.dumps({'status':'failed','issues':[{'code':'storage_unavailable'}]}))
        raise SystemExit(2)
    print(json.dumps(result,indent=2))
    raise SystemExit(1 if result['status']=='rejected' else 0)
