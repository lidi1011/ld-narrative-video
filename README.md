# 通用叙事视频技能 / Narrative video skill

版本：0.2.0-rc.1。将文案与素材制作成可编辑 HyperFrames 工程、分镜或视频。无需固定 Agent、付费素材服务或人物 IP；无声与已有配音任务可独立完成。

安装目录、环境能力与验证状态见 [跨平台安装](references/installation.md)。完整流程见 [技能入口](SKILL.md)。`<skill>` 指当前技能安装目录，命令执行位置与技能目录不必相同。

## 最小示例

需要 Node 22+、Python 3.10+；渲染另需 FFmpeg/ffprobe、Google Chrome 和 npm 依赖。以下命令同时适用于 PowerShell 和 POSIX shell，路径有空格时保留引号：

```text
node "<skill>/scripts/run_python.mjs" "<skill>/scripts/create_project.py" "./demo-video" --title "中文演示" --aspect-ratio 9:16
cd demo-video/video
npm ci
node tools/run_python.mjs tools/build_storyboard.py --project-root .
npm run doctor -- --browser-check
npm run storyboard
npm run render
```

模板是 48 秒无声配方演示，不是用户主题成片。替换 shots/timeline 内容后再交付。完成真实关键帧检查；有声作品另需听审。Doctor 退出 1 表示渲染环境尚未就绪，不妨碍文案规划或可用的构建阶段。

## 声音

先选择无声、已有音频、或可选豆包 TTS。已有音频按 [音频说明](references/audio-tools.md) 导入实测时间戳；不默认下载 ASR 模型。豆包需用户自己的显式配置，示例在 assets/config-examples/tts.example.json。没有 API key 不调用云服务。

## 可复现与边界

固定 HyperFrames 0.8.35 与 npm lock，附原版 Noto Sans CJK SC 字体及 OFL。首次 npm ci 需要网络；渲染器可能需要首次浏览器准备。测试不使用真实凭据。Windows/Linux 代码路径已适配，但只有实际运行的系统才能标记通过；见安装说明。

版权：自有代码和文档采用 [MIT License](LICENSE)，版权声明使用 narrative-video contributors；第三方资源适用各自条款，见 [第三方声明](THIRD_PARTY_NOTICES.md)。公开发布仓库：[ld-narrative-video](https://github.com/lidi1011/ld-narrative-video)。当前版本仍为发布候选，跨系统实测边界见上文。
