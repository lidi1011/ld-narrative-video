#!/usr/bin/env python3
"""Export original event text and measured timing to SRT without rewriting."""
import argparse
from pathlib import Path
from nv_core import validate,local,sha,write

def stamp(ms):
 h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--project-root',type=Path,required=True);ap.add_argument('--output',default='captions.srt');a=ap.parse_args();root=a.project_root.resolve();r=validate(root)
 if r['errors']:ap.exit(1,'\n'.join(r['errors'])+'\n')
 out=local(root,a.output);events=r['timeline']['events'];blocks=[]
 for i,e in enumerate(events):
  if not e.get('text','').strip():ap.exit(1,'Cannot export event without text\n')
  blocks.append(f'{i+1}\n{stamp(e["start_ms"])} --> {stamp(e["end_ms"])}\n{e["text"].strip()}\n')
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(blocks),encoding='utf-8');write(root/'qc/subtitles.json',{'timeline_sha256':sha(root/'script/timeline.json'),'path':a.output,'sha256':sha(out),'event_count':len(events)});print(out)
