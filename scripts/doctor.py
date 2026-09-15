#!/usr/bin/env python3
"""Local readiness probe. No downloads, paid calls, or secret values in output."""
import argparse
import json
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from nv_runtime import executable, hyperframes_command

def inspect(root, browser=False):
    root = Path(root).resolve()
    checks = {}
    def run(name, fn):
        try:
            checks[name] = {"ok": True, "detail": fn()}
        except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
            checks[name] = {"ok": False, "detail": str(exc)[:500]}
    def version(name, env):
        cmd = executable(name, env)
        flag = '-version' if name in {'ffmpeg','ffprobe'} else '--version'
        p = subprocess.run([cmd,flag], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15, check=True)
        line = p.stdout.splitlines()[0]
        if name == 'node' and int(line.lstrip('v').split('.')[0]) < 22:
            raise ValueError('Node 22+ required')
        return line
    checks['python'] = {'ok':sys.version_info >= (3,10),'detail':platform.python_version()}
    for name,env in [('node','NARRATIVE_VIDEO_NODE'),('ffmpeg','NARRATIVE_VIDEO_FFMPEG'),('ffprobe','NARRATIVE_VIDEO_FFPROBE')]:
        run(name,lambda n=name,e=env:version(n,e))
    def writable():
        with tempfile.TemporaryDirectory(prefix='.nv-doctor-',dir=root) as t:
            p=Path(t)/'中文 write.txt';p.write_text('中文',encoding='utf-8')
            if p.read_text(encoding='utf-8') != '中文': raise ValueError('UTF-8 round trip failed')
        return 'temporary UTF-8 file round trip passed'
    run('workspace',writable)
    def loopback():
        with socket.socket() as sock: sock.bind(('127.0.0.1',0))
        return 'loopback port allocation passed'
    run('loopback',loopback)
    run('hyperframes',lambda:hyperframes_command(root)[1])
    def font():
        import hashlib
        folder=root/'vendor/fonts';m=json.loads((folder/'source.json').read_text(encoding='utf-8'))
        if hashlib.sha256((folder/m['file']).read_bytes()).hexdigest()!=m['sha256']:
            raise ValueError('Bundled font hash mismatch')
        return 'bundled font hash passed; browser load tested separately'
    run('font',font)
    if browser:
        def browser_probe():
            command=[executable('node','NARRATIVE_VIDEO_NODE'),str(Path(__file__).with_name('doctor_browser.mjs')),str(root)]
            p=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            if p.returncode:raise ValueError(p.stderr[-500:] or p.stdout[-500:])
            return json.loads(p.stdout)
        run('browser',browser_probe)
    else: checks['browser']={'ok':None,'detail':'not tested; use --browser-check after building index.html'}
    ready=all(checks[x]['ok'] is True for x in ['python','node','ffmpeg','ffprobe','workspace','loopback','hyperframes','font','browser'])
    return {'platform':platform.system(),'checks':checks,'capabilities':{'planning':True,'build':checks['python']['ok'] and checks['workspace']['ok'],'render_environment':ready},'not_tested':['actual video render','visual review','listening review','cloud account access']}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project-root',type=Path,required=True);ap.add_argument('--browser-check',action='store_true');ap.add_argument('--output',type=Path)
    a=ap.parse_args();report=inspect(a.project_root,a.browser_check);text=json.dumps(report,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if report['capabilities']['render_environment'] else 1
if __name__=='__main__':sys.exit(main())
