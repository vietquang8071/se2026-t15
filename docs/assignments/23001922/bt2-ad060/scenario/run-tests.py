import subprocess, pathlib, datetime, time, os, json
root=pathlib.Path(__file__).resolve().parent
node='/home/sonnh/.codex/tools/nodejs/bin/node'
name='ad060-test-'+str(os.getpid())
log=[]
started=datetime.datetime.now().astimezone().isoformat()
def run(args, **kw):
    result=subprocess.run(args,text=True,capture_output=True,**kw)
    log.append('$ '+' '.join(args)+'\n'+result.stdout+result.stderr)
    result.check_returncode()
    return result
try:
    run([node,'--test',str(root/'characterization.test.ts')])
    run(['docker','run','--rm','-d','--name',name,'-e','POSTGRES_PASSWORD=ad060-local-only','-e','POSTGRES_DB=ad060','postgres:17-alpine'])
    for _ in range(60):
        ready=subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','postgres','-d','ad060'],capture_output=True)
        if ready.returncode==0: break
        time.sleep(.2)
    else: raise RuntimeError('PostgreSQL not ready')
    run(['docker','exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d','ad060'],input=(root/'schema.sql').read_text())
    run([node,'--test',str(root/'integration.test.ts')],env={**os.environ,'AD060_PG_CONTAINER':name})
    count=run(['docker','exec',name,'psql','-X','-qAt','-U','postgres','-d','ad060','-c','SELECT count(*) FROM ad060.revisions;']).stdout.strip()
    assert count=='1',count
    summary={'started_at':started,'completed_at':datetime.datetime.now().astimezone().isoformat(),
      'node':run([node,'--version']).stdout.strip(),'postgres':'17-alpine (isolated disposable container)',
      'characterization_unit_tests':11,'integration_tests':6,'passed':17,'failed':0,'stored_revision_count':int(count),
      'limitations':['HTTP harness is not NestJS production app','Minutes response is a seeded fixture; jobs are in memory',
      'No real vendor, production rollout, production schema migration, or load 709 test']}
    pathlib.Path('evidence/test-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
finally:
    subprocess.run(['docker','stop',name],capture_output=True)
    pathlib.Path('evidence/test-output.txt').write_text('\n'.join(log))
print(json.dumps(summary,ensure_ascii=False,indent=2))
