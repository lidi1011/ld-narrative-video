from nv_runtime import executable
"""Compare rendered audio to the declared source mix in measured time windows."""
import array,math,subprocess
from nv_core import local

def pcm(args):
 raw=subprocess.check_output([executable('ffmpeg','NARRATIVE_VIDEO_FFMPEG'),'-v','error',*args,'-ac','1','-ar','8000','-f','f32le','pipe:1'])
 x=array.array('f');x.frombytes(raw);return x

def verify(root,media,plan,duration_ms):
 args=[];filters=[]
 for i,a in enumerate(plan):
  args+=['-i',str(local(root,a['path']))]
  begin=a.get('source_start_ms',0)/1000;length=(a['end_ms']-a['start_ms'])/1000
  filters.append(f'[{i}:a]atrim=start={begin}:duration={length},asetpts=PTS-STARTPTS,adelay={a["start_ms"]}:all=1[a{i}]')
 filters.append(''.join(f'[a{i}]' for i in range(len(plan)))+f'amix=inputs={len(plan)}:normalize=0,apad,atrim=duration={duration_ms/1000}[out]')
 expected=pcm(args+['-filter_complex',';'.join(filters),'-map','[out]'])
 actual=pcm(['-i',str(media),'-vn']);failures=[];scores=[];active=0
 # AAC can perturb boundaries; compare half-second windows with ±2ms sample lag.
 for start in range(0,len(expected),4000):
  end=min(start+4000,len(expected),len(actual));e=expected[start:end];a=actual[start:end]
  if len(e)<400:continue
  ee=sum(v*v for v in e);aa=sum(v*v for v in a)
  if ee/len(e)<1e-8:
   if aa/len(a)>1e-5:failures.append({'at_ms':start//8,'reason':'unexpected audible content'})
   continue
  active+=1;best=-1
  for lag in range(-16,17,2):
   lo=max(0,lag);hi=min(len(e),len(a)+lag)
   dot=sum(e[k]*a[k-lag] for k in range(lo,hi));en=sum(e[k]*e[k] for k in range(lo,hi));an=sum(a[k-lag]*a[k-lag] for k in range(lo,hi))
   if en*an>0:best=max(best,dot/math.sqrt(en*an))
  scores.append(best)
  if best<.85:failures.append({'at_ms':start//8,'reason':'source mix differs or missing audio','correlation':round(best,4)})
 return {'method':'8kHz mono PCM comparison against declared source mix; 500ms windows; ±2ms lag','active_windows':active,'minimum_correlation':min(scores) if scores else None,'failures':failures,'passed':not failures,'limitation':'Verifies source content and placement; does not replace pronunciation, loudness or listening review'}
