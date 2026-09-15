from nv_runtime import executable
import hashlib,json,math,re,subprocess
from pathlib import Path
MODULES={'infographic','screen-demo','footage','typography','ip-character','presenter'}
RECIPES={'comparison','steps','grouping','cause','focus','takeaway'}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def local(root,name):
 if not isinstance(name,str) or not name or Path(name).is_absolute():raise ValueError('Expected project-relative path')
 p=(Path(root)/name).resolve()
 if not p.is_relative_to(Path(root).resolve()):raise ValueError('Path escapes project: '+name)
 return p
def probe(p):return json.loads(subprocess.check_output([executable('ffprobe','NARRATIVE_VIDEO_FFPROBE'),'-v','error','-show_streams','-show_format','-of','json',str(p)]))
def frame(ms,fps):return math.floor(ms*fps/1000+0.5)
def fingerprints(root):
 names=['project.json','script/timeline.json','script/shots.json','assets/manifest.json','DESIGN.md','styles.css','vendor/gsap.min.js','package.json','package-lock.json','hyperframes.json']
 names += [p.relative_to(root).as_posix() for p in sorted((root/'vendor/fonts').glob('*')) if p.is_file()]
 names += ['portrait.css'] if (root/'portrait.css').exists() else []
 names += [a['path'] for a in read(root/'assets/manifest.json')['assets']]
 names += [a['path'] for a in read(root/'script/timeline.json').get('audio',[])]
 names += [p for p in ['audio/alignment.json','script/narration.txt'] if (root/p).exists()]
 return {n:sha(local(root,n)) for n in sorted(set(names))}
def validate(root):
 root=Path(root).resolve();errors=[];warnings=[];result={}
 def req(ok,msg):
  if not ok:errors.append(msg)
 def integer(x):return type(x) is int
 try:
  p=read(root/'project.json');t=read(root/'script/timeline.json');d=read(root/'script/shots.json');aa=read(root/'assets/manifest.json')['assets']
  shots=d['shots'];duration=t['duration_ms'];fps=p['fps'];am={};em={}
  req(all(x.get('schema_version')==1 for x in [p,t,d]),'Unsupported schema')
  dims=(p['width'],p['height']);req(dims in [(1280,720),(720,1280)],'Supported layouts: 1280x720 or 720x1280')
  req(p.get('aspect_ratio','9:16' if dims==(720,1280) else '16:9')==('9:16' if dims==(720,1280) else '16:9'),'Aspect ratio/dimensions mismatch')
  if dims==(720,1280):req((root/'portrait.css').is_file(),'Missing portrait.css: initialize from the current skill template')
  req(fps in [24,25,30,60],'Invalid fps');req(integer(duration) and duration>0,'Invalid duration')
  req(p['audio_mode'] in ['silent','narration','source'],'Invalid audio mode')
  prev=0
  for e in t['events']:
   req(e['id'] not in em,'Duplicate event');em[e['id']]=e
   req(integer(e['start_ms']) and integer(e['end_ms']) and prev<=e['start_ms']<e['end_ms']<=duration,'Invalid/overlapping events');prev=e['end_ms']
  for a in aa:
   req(a['id'] not in am,'Duplicate asset');am[a['id']]=a;f=local(root,a['path'])
   req(f.is_file(),'Missing asset '+a['id']);req(a['kind'] in ['image','video'],'Invalid asset kind')
   req(a.get('usage') in ['evidence','illustration','fixture'] and bool(a.get('source')),'Missing asset provenance')
   if f.is_file():req(a['sha256']==sha(f),'Changed asset '+a['id'])
  ids=set();cursor=0;source_audio=0;used_events=[];audio_plan=[]
  for s in shots:
   sid=s['id'];req(bool(re.fullmatch('S[0-9]{3,}',sid)) and sid not in ids,'Invalid shot ID');ids.add(sid)
   req(integer(s['start_ms']) and integer(s['end_ms']) and s['start_ms']==cursor<s['end_ms']<=duration,'Shot coverage error '+sid);cursor=s['end_ms']
   req(s['recipe_id'] in RECIPES,'Unknown recipe');req(bool(s.get('purpose')) and bool(s.get('hero_state')),'Missing shot intention')
   mods=set(s['presentations']);req(bool(mods) and mods<=MODULES,'Invalid module');req(0<len(s['items'])<=4 and all(isinstance(x,str) and x.strip() for x in s['items']),'Use 1-4 nonempty text items per shot')
   req(bool(s.get('event_ids')),'No events in '+sid)
   for eid in s['event_ids']:
    used_events.append(eid)
    e=em.get(eid);req(e is not None,'Unknown event '+eid)
    if e:req(s['start_ms']<=e['start_ms']<e['end_ms']<=s['end_ms'],'Event outside shot')
   beat_items=[]
   for b in s.get('beats',[]):
    req(b['event_id'] in s['event_ids'] and integer(b['at_ms']) and s['start_ms']<=b['at_ms']<s['end_ms'],'Invalid beat')
    req(integer(b.get('item_index')) and 0<=b.get('item_index',-1)<len(s['items']),'Invalid beat item_index');beat_items.append(b.get('item_index'))
   req(len(set(beat_items))==len(beat_items),'One entrance beat per item in V1')
   req(s['end_ms']-s['start_ms']>=300,'V1 scenes need at least 300 ms')
   aids=s.get('asset_ids',[])
   req(len(aids)<=1,'V1 allows one visible asset per shot')
   req(not mods.intersection({'screen-demo','footage','ip-character','presenter'}) or bool(aids),'Media module missing assets '+sid)
   if 'ip-character' in mods:
    refs=s.get('module_options',{}).get('ip-character',{}).get('reference_asset_ids',[]);req(bool(refs) and all(x in am for x in refs),'IP references missing')
   for aid in aids:
    req(aid in am,'Unregistered asset '+aid)
    if aid not in am:continue
    a=am[aid];f=local(root,a['path'])
    if 'presenter' in mods:req(a['kind']=='video','Presenter requires actual video')
    if 'screen-demo' in mods and a['usage']!='evidence':warnings.append(sid+': illustrative interface, not evidence')
    if a['kind']=='video' and f.is_file():
     m=probe(f);offset=s.get('media_start_ms',0);has_audio=any(x['codec_type']=='audio' for x in m['streams'])
     req(integer(offset) and offset>=0 and offset+s['end_ms']-s['start_ms']<=float(m['format']['duration'])*1000+1000/fps,'Source too short '+sid)
     if s.get('preserve_audio',True) and has_audio:
      source_audio+=1;audio_plan.append({'path':a['path'],'start_ms':s['start_ms'],'end_ms':s['end_ms'],'source_start_ms':offset})
     if 'presenter' in mods and not s.get('preserve_audio',True):warnings.append('Presenter audio removed: verify user requested this')
   req(frame(s['end_ms'],fps)>frame(s['start_ms'],fps),'Zero-frame shot')
  req(bool(shots) and cursor==duration,'Incomplete full-film coverage')
  req(sorted(used_events)==sorted(em),'Every event must belong to exactly one shot')
  for a in t.get('audio',[]):
   req(all(integer(a.get(k,0)) for k in ['start_ms','end_ms','source_start_ms']),'Audio timing must be integer milliseconds')
   audio_plan.append(a)
   f=local(root,a['path']);req(f.is_file(),'Missing audio');req(0<=a['start_ms']<a['end_ms']<=duration,'Invalid audio placement')
   if f.is_file():
    req(a['sha256']==sha(f),'Stale audio');m=probe(f);req(any(x['codec_type']=='audio' for x in m['streams']),'Missing audio stream')
    req(a.get('source_start_ms',0)>=0 and a.get('source_start_ms',0)+a['end_ms']-a['start_ms']<=float(m['format']['duration'])*1000+1000/fps,'Audio range exceeds media')
  for i,a in enumerate(audio_plan):
   for b in audio_plan[i+1:]:req(a['path']!=b['path'] or max(a['start_ms'],b['start_ms'])>=min(a['end_ms'],b['end_ms']),'Duplicate overlapping audio source')
  audio_count=source_audio+len(t.get('audio',[]));req((p['audio_mode']=='silent')==(audio_count==0),'Audio mode/source mismatch')
  if p['audio_mode']=='narration':
   alignment=read(root/'audio/alignment.json');req(alignment['audio_sha256']==sha(local(root,alignment['audio_path'])),'Stale alignment audio')
   req(alignment['text_sha256']==sha(root/'script/narration.txt'),'Stale alignment text');req(not [i for i in alignment.get('issues',[]) if i.get('code')!='TEXT_FORMAT_DIFFERENCE'],'Unresolved alignment issues')
   if alignment.get('issues'):warnings.append('Alignment includes formatting differences; original text retained')
   segs=alignment['segments'];norm=lambda x:re.sub(r'[\W_]+','',x,flags=re.UNICODE)
   req(norm(''.join(x['text'] for x in segs))==norm((root/'script/narration.txt').read_text(encoding='utf-8')),'Alignment text mismatch')
   placed=[a for a in t.get('audio',[]) if a['path']==alignment['audio_path']];req(len(placed)==1,'Narration must have one matching audio placement')
   prev=0
   for z in segs:
    req(integer(z['start_ms']) and integer(z['end_ms']),'Alignment timing must be integer milliseconds')
    req(prev<=z['start_ms']<z['end_ms'],'Alignment overlap');prev=z['end_ms']
   if placed:
    offset=placed[0]['start_ms']-placed[0].get('source_start_ms',0);pm={z['id']:z for z in segs}
    for e in t['events']:
     req(bool(e.get('phrase_id')),'Narration event requires phrase_id')
     if e.get('phrase_id'):
      z=pm.get(e['phrase_id']);req(z is not None,'Unknown aligned phrase')
      if z:req((e['start_ms'],e['end_ms'],e['text'])==(z['start_ms']+offset,z['end_ms']+offset,z['text']),'Event changed measured alignment')
   req(len({z['id'] for z in segs})==len(segs),'Duplicate aligned phrase')
   req({e.get('phrase_id') for e in t['events']}=={z['id'] for z in segs},'Every aligned phrase needs an event')
   if not alignment.get('reviewed'):warnings.append('Alignment listening review pending')
  result={'project':p,'timeline':t,'shots':shots,'assets':am,'expected_audio':audio_count,'audio_plan':audio_plan}
 except (KeyError,TypeError,ValueError,OSError,subprocess.CalledProcessError) as e:errors.append('Contract error: '+str(e))
 return dict(result,errors=errors,warnings=warnings)
