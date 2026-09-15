#!/usr/bin/env python3
"""Create a 3-second silent fixture for clean-install smoke tests. No cloud calls."""
import argparse,json,subprocess,sys
from pathlib import Path
from nv_core import read,write

def main():
    ap=argparse.ArgumentParser();ap.add_argument('task_root',type=Path);ap.add_argument('--aspect-ratio',choices=['16:9','9:16'],default='16:9');a=ap.parse_args()
    subprocess.run([sys.executable,str(Path(__file__).with_name('create_project.py')),str(a.task_root),'--title','中文 portable smoke','--aspect-ratio',a.aspect_ratio],check=True)
    root=a.task_root/'video';p=root/'script/shots.json';d=read(p);d['shots']=d['shots'][:1];d['shots'][0]['end_ms']=3000;write(p,d)
    p=root/'script/timeline.json';d=read(p);d['duration_ms']=3000;d['events']=d['events'][:1];d['events'][0]['end_ms']=3000;write(p,d)
    subprocess.run([sys.executable,str(root/'tools/build_storyboard.py'),'--project-root',str(root)],check=True)
if __name__=='__main__':main()
