import {spawnSync} from 'node:child_process';
const args = process.argv.slice(2);
if (!args.length) { console.error('Usage: node run_python.mjs <script.py> [args]'); process.exit(2); }
const candidates = process.env.NARRATIVE_VIDEO_PYTHON
  ? [[process.env.NARRATIVE_VIDEO_PYTHON]]
  : (process.platform === 'win32' ? [['py','-3'],['python'],['python3']] : [['python3'],['python']]);
let selected;
for (const cmd of candidates) {
  const probe = spawnSync(cmd[0], [...cmd.slice(1), '-c', 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'], {shell:false, stdio:'ignore'});
  if (probe.status === 0) { selected=cmd; break; }
}
if (!selected) { console.error('Python 3.10+ required; set NARRATIVE_VIDEO_PYTHON to its executable path.'); process.exit(2); }
const run = spawnSync(selected[0], [...selected.slice(1), ...args], {shell:false, stdio:'inherit', env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
if (run.error) console.error(run.error.message);
process.exit(run.status ?? 1);
