#!/usr/bin/env python3
"""Render with pinned local HyperFrames and bind output to its build."""
import argparse,subprocess
from pathlib import Path
from nv_core import read,write,sha,local
from check_project import check
from nv_runtime import hyperframes_command
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--project-root',type=Path,required=True);ap.add_argument('--hyperframes',type=Path);ap.add_argument('--output',default='renders/final.mp4');a=ap.parse_args();root=a.project_root.resolve()
 try:
  r=check(root)
  if not r['passed']:raise ValueError('\n'.join(r['errors']))
  command=hyperframes_command(root,a.hyperframes);out=local(root,a.output);out.parent.mkdir(parents=True,exist_ok=True)
  build_hash=sha(root/'qc/build.json')
  subprocess.run([*command,'render',str(root),'--output',str(out),'--fps',str(read(root/'project.json')['fps']),'--workers','1','--quality','standard','--strict','--no-best-effort'],check=True)
  if build_hash!=sha(root/'qc/build.json') or not check(root)['passed']:raise ValueError('Inputs changed during rendering')
  write(root/'qc/render.json',{'build_sha256':build_hash,'media':a.output,'media_sha256':sha(out)})
  r=check(root,a.output)
  if not r['passed']:raise ValueError('\n'.join(r['errors']))
  print(out)
 except (ValueError,OSError,subprocess.CalledProcessError) as e:ap.exit(1,str(e)+'\n')
