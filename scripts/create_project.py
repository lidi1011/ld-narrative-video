#!/usr/bin/env python3
import argparse,shutil
from pathlib import Path
from nv_core import read,write
p=argparse.ArgumentParser();p.add_argument('task_root');p.add_argument('--title',required=True);p.add_argument('--aspect-ratio',choices=['16:9','9:16'],default='16:9');a=p.parse_args();root=Path(a.task_root).resolve()
if root.exists():p.error('Target already exists; do not reinitialize an existing task')
width,height=(720,1280) if a.aspect_ratio=='9:16' else (1280,720)
tpl=Path(__file__).resolve().parents[1]/'assets/project-template'
root.mkdir(parents=True);shutil.copytree(tpl,root/'video',ignore=shutil.ignore_patterns('node_modules','.hyperframes','renders','stills','qc'))
shutil.copytree(Path(__file__).resolve().parent,root/'video/tools',ignore=shutil.ignore_patterns('__pycache__'))
(root/'inputs').mkdir();(root/'inputs/SOURCES.csv').write_text('id,path,source,usage,verified\n', encoding='utf-8')
(root/'BRIEF.md').write_text(f'# {a.title}\n\n- 状态：准备中\n- 观众与目标：待填写\n- 当前内容：无声配方演示，须替换为本任务分镜\n- 画幅：{width}×{height}（{a.aspect_ratio}），30fps\n- 用户要求与停止阶段：记录有效决定\n', encoding='utf-8')
(root/'HANDOFF.md').write_text('# 任务状态\n\n已初始化独立工程；尚未制作任务成片。\n', encoding='utf-8')
x=read(root/'video/project.json');x.update(title=a.title,width=width,height=height,aspect_ratio=a.aspect_ratio);write(root/'video/project.json',x);print(root)
