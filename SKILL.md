---
name: ld-narrative-video
description: 将主题、定稿文案与可靠素材编排为可修改的横屏或竖屏叙事视频，按需组合信息图、录屏、实拍素材、文字动效、可选 IP 与真人口播。
license: MIT
metadata:
  compatibility: "Python 3.10+; Node 22+ and npm; FFmpeg and Chrome for rendering."
  version: "0.2.0-rc.1"
---

# 通用叙事视频

在用户指定的独立任务目录内，把主题、文案和已有素材落成可修改的 HyperFrames 工程、分镜、样片或成片。仅使用当前任务明确提供或授权的资料、配置和凭据；不继承技能开发环境或其他用户的授权。无声与已有配音任务不需要配置 TTS。

先确认观众、目标、内容依据、声音来源和可靠素材，再把每个镜头写成观众要理解的内容、画面状态、时间变化、素材来源与实现方式。表现形式由镜头职责和素材条件决定；IP 角色是可选分支。`A-roll`/`B-roll` 只是编辑标记，不等于角色、信息图或固定画面类别。

## 环境与兼容

首次使用先读 [安装与能力说明](references/installation.md)，通过 Node 启动器选择 Python。渲染前运行 `npm run doctor -- --browser-check`；缺少能力时只完成可执行阶段。无声、已有配音和可选豆包路径分开。当前无需特定 Agent 私有工具，不继承维护者运行环境。

## 入口与输出

- 新任务根目录按需创建 `BRIEF.md`、`HANDOFF.md`、`inputs/`、`video/` 和 `delivery/`。由项目脚本创建时使用：
  `python3 <skill>/scripts/create_project.py <new-task-root> --title '主题'`。
- 定稿、已有配音、素材原声和明确的无声要求都保留原意。只有收到主题或资料时才新增脚本整理，并标明事实依据与待核查内容。
- `script/shots.json` 是可编辑分镜源；其根结构、时间轴、素材清单和 QC 合同以 [`references/contracts-and-qc.md`](references/contracts-and-qc.md) 为唯一权威，本入口不重复定义 schema。
- 生成分镜表和预览索引：`python3 <skill>/scripts/build_storyboard.py --project-root <video>`。加 `--capture` 从真实 HTML 抽帧并生成联系表；不要把概念图当成工程关键帧。
- 检查项目：`python3 <skill>/scripts/check_project.py --project-root <video> [--media renders/final.mp4]`。
- 默认 16:9 横屏（1280×720）；用户要求竖屏时选 9:16（720×1280）。初始化加 `--aspect-ratio 9:16`，使用独立竖屏布局；未指定时保留横屏。切换已有内容请新建任务，复用文案、音频与素材并重新编排和验证，不裁切旧成片。

## 使用顺序

按当前任务读取所需资料：

1. 所有任务先读 [`references/workflow.md`](references/workflow.md) 和 [`references/visual-and-audio.md`](references/visual-and-audio.md)。
2. 需要选择或组合镜头配方时读 [`references/shot-recipes.md`](references/shot-recipes.md)。
3. 只加载当前镜头实际使用的表现模块：[`infographic`](references/modules/infographic.md)、[`screen-demo`](references/modules/screen-demo.md)、[`footage`](references/modules/footage.md)、[`typography`](references/modules/typography.md)、[`ip-character`](references/modules/ip-character.md)、[`presenter`](references/modules/presenter.md)。没有 IP 需求就不加载 `ip-character`，也不索要角色参考。
4. 需要整篇配音或对齐时读项目提供的 [`references/audio-tools.md`](references/audio-tools.md)；默认 TTS 由音频适配器 适配豆包，已有配音可跳过 TTS。
5. 进入时间、分镜、素材、媒体或修改检查时读 [`references/contracts-and-qc.md`](references/contracts-and-qc.md)，以其中的合同和检查结果为准。

## 不易推断的约束

- 视觉风格、画面布局和渲染引擎分别记录：`DESIGN.md` 负责风格与字幕规则，任务配置负责画幅规格，HyperFrames 负责当前实现。不要因使用某种配色就推断必须出现某个角色，也不要把模块绑定到 A/B 分类。
- 信息图、录屏、实拍、文字、IP 和真人可以在同一条视频中组合。每个模块只负责自己的输入、实现提示和质量检查，不另建全片时间轴、不改定稿、不替其他模块决定样式。
- 真实工具演示必须使用真实截图、录屏、数据和结果。示意 UI、占位数据或未执行的操作要明确标记，不能伪造成产品证据。
- 平面角色图只能做其实际提供的移动、缩放或镜头运动；换表情、转身、操作道具等需要相应姿势、分层素材或视频资产。IP 完全可选。
- 当前项目已验证 HyperFrames 0.8.35，优先使用项目 npm scripts：`npm run check`、`npm run dev`、`npm run render`。需要快照时使用项目原生 snapshot 命令的 `--at` 和 `--describe false`；先看实际命令的 `--help`，不要猜测参数或自动启用外部描述服务。
- 按用户已授予的范围连续执行；用户要求“只规划”“只出样片”或其他阶段停止点时，在该阶段交付，不擅自推进到下一阶段。流程中的审阅点是可交付检查点，不新增逐步审批门。
