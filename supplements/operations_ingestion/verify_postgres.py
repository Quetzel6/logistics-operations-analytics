"""One-command Docker acceptance on Mac/Linux; dedicated disposable database only."""
import argparse
import json
from pathlib import Path
import os
import secrets
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent
class DockerError(Exception):pass

def run(output):
    import psycopg
    from psycopg.conninfo import make_conninfo
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    name='operations-m5-'+uuid.uuid4().hex[:12];password=secrets.token_hex(24)
    def docker(args,stage,timeout=60):
        try:r=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=timeout)
        except FileNotFoundError:raise DockerError('docker_executable_missing') from None
        except subprocess.TimeoutExpired:raise DockerError(stage+'_timeout') from None
        except OSError:raise DockerError(stage+'_unavailable') from None
        if r.returncode:raise DockerError(stage+'_failed')
        return r.stdout.strip()
    report=dict(status='failed',api_calls=0,container_removed=False)
    attempted=False
    try:
        print('Checking Docker and pulling PostgreSQL image...',flush=True)
        docker(['info','--format','{{.ServerVersion}}'],'docker_info')
        docker(['pull','postgres:16-alpine'],'image_pull',300)
        attempted=True
        docker(['run','--detach','--rm','--name',name,'--label','portfolio.lab=operations-m5',
            '--publish','127.0.0.1::5432','-e','POSTGRES_USER=lab',
            '-e','POSTGRES_DB=operations_test_m5','-e','POSTGRES_PASSWORD='+password,'postgres:16-alpine'],'container_start')
        for attempt in range(45):
            try:docker(['exec',name,'pg_isready','-h','127.0.0.1','-U','lab','-d','operations_test_m5'],'postgres_ready');break
            except DockerError:
                if attempt==44:raise DockerError('postgres_not_ready')
                time.sleep(1)
        info=json.loads(docker(['inspect',name],'container_inspect'))[0]
        binding=info['NetworkSettings']['Ports']['5432/tcp'][0]
        if binding['HostIp']!='127.0.0.1' or not binding['HostPort'].isdigit():raise DockerError('unexpected_port_binding')
        dsn=make_conninfo(host='127.0.0.1',port=int(binding['HostPort']),user='lab',password=password,dbname='operations_test_m5')
        env=dict(os.environ,OPERATIONS_TEST_DSN=dsn)
        print('Running real PostgreSQL tests and repeated pipeline...',flush=True)
        r=subprocess.run([sys.executable,str(ROOT/'postgres_acceptance.py'),'--output',str(out/'evidence')],
            env=env,capture_output=True,text=True,timeout=300)
        (out/'acceptance_log.txt').write_text((r.stdout+r.stderr).replace(dsn,'[test DSN]').replace(password,'[redacted]'))
        if r.returncode:raise DockerError('postgres_acceptance_failed')
        report=json.loads((out/'evidence/postgres_acceptance.json').read_text())
        report.update(docker_image_id=info['Image'],container_removed=False)
    except (DockerError,OSError,subprocess.TimeoutExpired,ValueError,KeyError) as exc:
        report.update(status='failed',error_code=str(exc) if isinstance(exc,DockerError) else 'runner_failed')
    finally:
        if attempted:
            try:docker(['rm','--force',name],'container_cleanup');report['container_removed']=True
            except DockerError:report['container_removed']=False
        if report['status']=='passed_local' and not report['container_removed']:
            report.update(status='failed',error_code='container_cleanup_failed')
        (out/'postgres_runner.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:r=run(a.output)
    except (ImportError,OSError):
        print(json.dumps(dict(status='failed',error_code='driver_missing_or_output_exists')));raise SystemExit(1)
    print(json.dumps(r,indent=2));raise SystemExit(0 if r['status']=='passed_local' else 1)
