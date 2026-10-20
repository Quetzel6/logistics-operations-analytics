"""Acceptance uses only temporary databases."""
import json
from pathlib import Path
import sqlite3
import platform
import subprocess
import sys
import tempfile
from ingest import ingest
ROOT=Path(__file__).resolve().parent
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,check=True)
with tempfile.TemporaryDirectory() as td:
    db=Path(td)/'acceptance.sqlite'
    first=ingest(ROOT/'fixtures',db)
    again=ingest(ROOT/'fixtures',db)
    with sqlite3.connect(db) as c:
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('orders','events','notes','runs')}
        quantity=c.execute('SELECT SUM(quantity) FROM orders').fetchone()[0]
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        fk=c.execute('PRAGMA foreign_key_check').fetchall()
    assert first['status']=='committed' and again['status']=='duplicate'
    assert counts==dict(orders=3,events=3,notes=2,runs=2)
    assert quantity==225 and integrity=='ok' and fk==[]
report={'status':'passed_local','python':sys.version.split()[0],
        'execution_platform':platform.system(),
        'scope':'verified on this execution host using temporary SQLite; no PostgreSQL, cloud, remote CI or model execution in this run',
        'first_run_status':first['status'],'second_run_status':again['status'],
        'row_counts':counts,'order_quantity_total':quantity,
        'integrity_check':integrity,'foreign_key_violations':len(fk)}
out=ROOT/'output';out.mkdir(exist_ok=True)
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
