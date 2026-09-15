from nv_runtime import executable
#!/usr/bin/env python3
"""Validate contracts, build freshness, and actual rendered media."""
import argparse,subprocess
from pathlib import Path
from verify_audio import verify
from nv_core import validate,read,write,sha,fingerprints,probe,local,frame

def check(root,media=None):
 r=validate(root);errors=r['errors'];report={'errors':errors,'warnings':r['warnings'],'visual_review':'not_performed'}
 try:
  b=read(root/'qc/build.json')
  if b['inputs']!=fingerprints(root) or b['html_sha256']!=sha(root/'index.html') or b['builder_sha256']!=sha(Path(__file__).with_name('build_storyboard.py')):errors.append('Stale build: rebuild and recapture storyboard')
  if (root/'qc/snapshots.json').exists():
   snap=read(root/'qc/snapshots.json')
   if snap.get('build_sha256')!=sha(root/'qc/build.json') or any(sha(local(root,n))!=h for n,h in snap.get('frames',{}).items()):report['warnings'].append('Storyboard snapshots are stale: recapture before visual review')
  else:report['warnings'].append('Actual storyboard capture pending')
  if media and not errors:
   path=local(root,media);receipt=read(root/'qc/render.json')
   if receipt.get('build_sha256')!=sha(root/'qc/build.json') or receipt.get('media')!=media or receipt.get('media_sha256')!=sha(path):errors.append('Stale or unbound rendered media: use render_project.py')
   m=probe(path);vs=[s for s in m['streams'] if s['codec_type']=='video'];aa=[s for s in m['streams'] if s['codec_type']=='audio'];p=r['project'];t=r['timeline']
   if not vs:errors.append('Missing video stream')
   else:
    v=vs[0];num,den=map(int,v['avg_frame_rate'].split('/'))
    if (v['width'],v['height'])!=(p['width'],p['height']) or abs(num/den-p['fps'])>0.001:errors.append('Video dimensions or fps mismatch')
    actual=int(v.get('nb_frames',round(float(v['duration'])*p['fps'])))
    if abs(actual-frame(t['duration_ms'],p['fps']))>1:errors.append('Rendered duration differs by more than one frame')
   if bool(aa)!=bool(r['expected_audio']):errors.append('Rendered audio stream does not match requested audio mode')
   subprocess.run([executable('ffmpeg','NARRATIVE_VIDEO_FFMPEG'),'-v','error','-xerror','-i',str(path),'-f','null','-'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   if r['expected_audio']:
    audio_check=verify(root,path,r['audio_plan'],t['duration_ms']);report['audio_content_check']=audio_check
    if not audio_check['passed']:errors.append('Rendered audio differs from declared source mix')
   report.update(media=media,sha256=sha(path),probe=m,full_decode='passed')
 except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:errors.append('Check failed: '+str(e))
 report['passed']=not errors;write(root/'qc/report.json',report);return report
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--project-root',type=Path,required=True);ap.add_argument('--media');a=ap.parse_args();r=check(a.project_root.resolve(),a.media);print('PASS' if r['passed'] else '\n'.join(r['errors']));raise SystemExit(0 if r['passed'] else 1)
