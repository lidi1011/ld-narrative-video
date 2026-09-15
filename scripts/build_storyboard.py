#!/usr/bin/env python3
"""Build HTML and storyboard from validated, shared millisecond timing."""
import argparse,html,json,shutil,subprocess
from pathlib import Path
from nv_runtime import hyperframes_command
from nv_core import validate,write,sha,fingerprints,probe,local

def build(root):
 v=validate(root)
 if v['errors']:raise ValueError('\n'.join(v['errors']))
 p,t,shots,assets=[v[k] for k in ['project','timeline','shots','assets']]
 esc=lambda x:html.escape(str(x),quote=True)
 blocks=[];motion=[];track=1;table=['# 分镜关键帧','', '由 script/shots.json 与 script/timeline.json 生成。图片须通过 --capture 渲染后查看。','', '|镜头|时间（秒）|目的|配方 / 模块|关键状态|','|---|---|---|---|---|']
 for i,s in enumerate(shots):
  sid=s['id'];start=s['start_ms']/1000;duration=(s['end_ms']-s['start_ms'])/1000;aids=s.get('asset_ids',[])
  cards=''.join(f'<div class="card" id="{sid}-item-{j}"><span class="number">{j+1:02}</span><span>{esc(item)}</span></div>' for j,item in enumerate(s['items']))
  media=''
  for j,aid in enumerate(aids):
   a=assets[aid]
   # V1 supports one visible source per shot. Multiple references live in module_options.
   if j:raise ValueError(sid+': V1 uses one visible asset; split the shot for more')
   if a['kind']=='image':media=f'<div class="media-panel"><img src="{esc(a["path"])}" alt="{esc(aid)}"></div>'
   else:
    offset=s.get('media_start_ms',0)/1000
    media='<div class="media-panel"></div>'
    blocks.append(f'<video id="{sid}-video" style="z-index:{track+1}" class="clip actual-media" data-start="{start}" data-duration="{duration}" data-media-start="{offset}" data-track-index="{track+1}" src="{esc(a["path"])}" muted playsinline></video>')
    if s.get('preserve_audio',True) and any(x['codec_type']=='audio' for x in probe(local(root,a['path']))['streams']):
     blocks.append(f'<audio id="{sid}-sound" class="clip" src="{esc(a["path"])}" data-start="{start}" data-duration="{duration}" data-media-start="{offset}" data-track-index="90"></audio>')
  blocks.append(f'<section id="{sid}" style="z-index:{track}" class="clip scene {s["recipe_id"]} {"with-media" if media else ""}" data-start="{start}" data-duration="{duration}" data-track-index="{track}"><div class="eyebrow">NARRATIVE / {i+1:02}</div><h1 id="{sid}-title">{esc(s.get("title",s["purpose"]))}</h1><div class="content"><div class="items">{cards}</div>{media}</div><div class="footer">{esc(p["title"])}</div><div class="counter">{i+1:02} / {len(shots):02}</div></section>')
  motion.append(f'tl.from("#{sid}-title",{{y:22,opacity:0,duration:{min(0.55,duration*.35)},ease:"power2.out"}},{start+min(0.12,duration*.1)});')
  for j in range(len(s['items'])):
   beats=[b for b in s.get('beats',[]) if b.get('item_index')==j]
   at=beats[0]['at_ms']/1000 if beats else start+min(0.6+j*0.18,duration*(.2+.12*j))
   anim_duration=min(.5,start+duration-at)
   motion.append(f'tl.from("#{sid}-item-{j}",{{y:28,opacity:0,duration:{anim_duration},ease:"power2.out"}},{at});')
  if i:
   cut=start;wid='wipe-'+sid
   blocks.append(f'<div id="{wid}" class="clip wipe" data-start="{cut-0.2}" data-duration="0.4" data-track-index="99"></div>')
   motion.append(f'tl.fromTo("#{wid}",{{scaleX:0,transformOrigin:"left"}},{{scaleX:1,duration:0.2,ease:"power2.in"}},{cut-0.2}).to("#{wid}",{{scaleX:0,transformOrigin:"right",duration:0.2,ease:"power2.out"}},{cut});')
  table.append(f'|{sid}|{start:g}–{start+duration:g}|{s["purpose"]}|{s["recipe_id"]} / {", ".join(s["presentations"])}|{s["hero_state"]}|')
  track+=2
 for j,a in enumerate(t.get('audio',[])):
  blocks.append(f'<audio id="audio-{j}" class="clip" src="{esc(a["path"])}" data-start="{a["start_ms"]/1000}" data-duration="{(a["end_ms"]-a["start_ms"])/1000}" data-media-start="{a.get("source_start_ms",0)/1000}" data-track-index="80"></audio>')
 if p.get('show_subtitles',p['audio_mode']=='narration'):
  for e in t['events']:
   blocks.append(f'<div class="clip caption" data-start="{e["start_ms"]/1000}" data-duration="{(e["end_ms"]-e["start_ms"])/1000}" data-track-index="95">{esc(e.get("text",""))}</div>')
 portrait=p['height']>p['width']
 extra='<link rel="stylesheet" href="portrait.css">' if portrait else ''
 doc='<!doctype html><html lang="zh-CN" style="--canvas-width:'+str(p['width'])+'px;--canvas-height:'+str(p['height'])+'px"><head><meta charset="utf-8"><link rel="stylesheet" href="styles.css">'+extra+'<script src="vendor/gsap.min.js"></script></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="'+str(t['duration_ms']/1000)+'" data-width="'+str(p['width'])+'" data-height="'+str(p['height'])+'">'+''.join(blocks)+'</div><script>const tl=gsap.timeline({paused:true});'+''.join(motion)+'window.__timelines=window.__timelines||{};window.__timelines.main=tl;</script></body></html>'
 (root/'index.html').write_text(doc, encoding='utf-8');(root/'shots.md').write_text('\n'.join(table)+'\n', encoding='utf-8')
 write(root/'qc/build.json',{'schema_version':1,'inputs':fingerprints(root),'html_sha256':sha(root/'index.html'),'builder_sha256':sha(__file__),'warnings':v['warnings']})
 return shots

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--project-root',type=Path,required=True);ap.add_argument('--capture',action='store_true');ap.add_argument('--hyperframes',type=Path);a=ap.parse_args();root=a.project_root.resolve()
 try:
  shots=build(root)
  if a.capture:
   command=hyperframes_command(root,a.hyperframes)
   times=','.join(str((s['start_ms']+(s['end_ms']-s['start_ms'])*.7)/1000) for s in shots)
   subprocess.run([*command,'snapshot',str(root),'--output',str(root/'stills'),'--at',times,'--no-end','--describe','false'],check=True)
   write(root/'qc/snapshots.json',{'build_sha256':sha(root/'qc/build.json'),'frames':{p.relative_to(root).as_posix():sha(p) for p in sorted((root/'stills').glob('*.png'))}})
  print(root/'shots.md')
 except (ValueError,OSError,subprocess.CalledProcessError) as e:ap.exit(1,str(e)+'\n')
if __name__=='__main__':main()
