import pathlib, subprocess, datetime, hashlib, json
root=pathlib.Path(__file__).parent/'repository'
files=sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '.git' not in p.parts)
manifest={
 'repository':'https://github.com/vietquang8071/se2026-t15',
 'branch':subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True).strip(),
 'commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
 'inspected_at':datetime.datetime.now().astimezone().isoformat(),
 'codegraph':(root/'.codegraph').exists(),
 'lecture_04_05':'Not supplied; no lecture files in workspace or reference clone',
 'files':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}}
pathlib.Path('evidence/snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
with open('evidence/source-numbered.txt','w') as out:
 for f in files:
  if f.endswith(('.ts','.tsx','.md','.prisma','.yml','.json')):
   out.write('\nFILE: '+f+'\n')
   for i,line in enumerate((root/f).read_text().splitlines(),1): out.write(f'{i:4} {line}\n')
