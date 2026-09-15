# 安装、能力与跨平台支持

## Agent 安装

复制完整技能目录（目录名须与 SKILL.md 的 name 一致），不是只复制入口。公开包名称为 `ld-narrative-video`；维护者全局源码名为 `narrative-video`。使用所在 runtime 的技能调用方式，或明确要求“使用 ld-narrative-video”。

- Codex：本项目维护者已验证全局技能发现；公开包可按当前 Codex 技能安装机制导入。不要把维护者的绝对路径复制到其他机器。
- Claude Code：项目 `.claude/skills/<name>/` 或用户 `~/.claude/skills/<name>/`。[官方说明](https://code.claude.com/docs/en/skills)
- WorkBuddy：技能页面 → 添加技能 → 上传本地技能包。无须假定与 CodeBuddy 共用目录。[官方说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)
- DeepSeek Harness：当前本地 provider 支持项目 `.dsh/skills`、`.agents/skills` 等来源；部署可能更换 provider，检查实际配置。[官方实现](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)
- ZCode：用户技能目录 `~/.zcode/skills/<name>/`；市场插件属于可选外壳。[官方说明](https://zcode.z.ai/en/docs/skill)

上述外部安装方式依据 2026-09-15 官方文档，不代表已在这些 runtime 实测。

## 本机依赖

最低 Python 3.10、Node 22；固定 npm lock。Python 启动器自动尝试 Windows 的 py -3/python/python3，其他系统 python3/python；NARRATIVE_VIDEO_PYTHON 可显式设置可执行文件路径。npm 脚本使用 Node 启动器，无 Bash、chmod 或 Unix npm shim 依赖。

FFmpeg、ffprobe 与 Chrome 需自行安装。NARRATIVE_VIDEO_NODE、NARRATIVE_VIDEO_FFMPEG、NARRATIVE_VIDEO_FFPROBE 可指定可执行文件路径。doctor 浏览器探测使用已安装 Google Chrome，或 NARRATIVE_VIDEO_CHROME 指定路径；该变量只控制 doctor，不宣称替换 HyperFrames 自身的浏览器选择。渲染器参数以固定版本的 --help 为准。

macOS/Linux 可用 python3；Windows 可用 py -3。文档中的多行反斜杠示例属于 POSIX shell，PowerShell 使用单行命令或 README 的 Node 启动器。凭据示例：

```sh
export NARRATIVE_VIDEO_DOUBAO_API_KEY='your-key'
```

```powershell
$env:NARRATIVE_VIDEO_DOUBAO_API_KEY = 'your-key'
```

密钥不要写入公开仓库。Windows 使用 access_token_env，不拿 POSIX 权限位冒充 Windows ACL 验证；POSIX 显式凭据文件仍要求禁止其他用户读取。

## 能力降级

| 可用能力 | 可交付阶段 |
| --- | --- |
| 文本读写 | 文案、分镜与素材需求 |
| Python 与可写任务目录 | 初始化、分镜构建、合同检查 |
| Node、HyperFrames、FFmpeg、浏览器与字体 | 技术渲染与导出 |
| 图片查看 | 才能记录实际视觉检查 |
| 音频播放与实际审听 | 才能记录听审 |

不依赖 Codex 专有面板、子 Agent 或特定生成工具。素材生成服务与 ASR 均为可选外部输入；支持标准目录和 JSON 合同。缺少终端时停止在文本交付，明确交给用户执行的命令。缺少图片查看时不声称视觉通过。

## 验证矩阵

- macOS ARM：维护环境；具体版本与本轮结果保存在项目发布验证记录。
- Windows 原生、Linux：代码兼容测试与 CI 流程已提供，未在本机实际运行。
- WSL：不等于 Windows 原生验证。
- Claude Code、WorkBuddy、DeepSeek Harness、ZCode：官方文档核对，运行时端到端测试尚未执行。

执行自检：`node <skill>/scripts/run_python.mjs -m unittest discover -s <skill>/tests -v`。本机用临时中文/空格路径跑两种画幅，再检查缺依赖、缺凭据与停止阶段。跨环境报告记录 OS、Agent 版本、依赖版本、命令、结果、未验证范围；不得只因 SKILL.md 可识别就宣布成片兼容。
