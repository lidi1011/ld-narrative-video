# narrative-video 音频工具

这两个脚本只依赖 Python 标准库，脚本路径按项目根目录计算。音频工具不读取默认凭据目录、不搜索环境变量；TTS 的凭据只能来自配置中写明的环境变量，或配置中写明的一份凭据文件。交付的技能配置不包含密钥。

## TTS：整篇一次请求

内置豆包适配器使用 V3 端点、显式 API key 文件引用与 `seed-tts-2.0` 资源，提供 PCM→WAV 输出和完整性检查，不依赖其他技能。1024 Unicode 字符是当前适配器示例约定，不作为官方接口上限声明。

默认男声为刘飞 2.0（`zh_male_liufei_uranus_bigtts`）；默认女声为爽快思思 2.0（`zh_female_shuangkuaisisi_uranus_bigtts`）。配置 `voices` 中各音色与资源成对保存，调用时用 `--voice male` 或 `--voice female`；省略时使用配置的 `speaker`，当前默认为男声。

先复制并审阅 [`assets/config-examples/tts.example.json`](../assets/config-examples/tts.example.json)。示例使用豆包 V3 HTTP 单向接口，发送一次完整文本请求；`max_text_chars: 1024` 按 Unicode 字符数检查；兼容旧配置的 `max_text_bytes` 字节检查。超过接口限制时命令直接失败，不拆句、不循环拼接，也不把分段结果冒充整篇合成。

默认示例通过 `access_token_env: NARRATIVE_VIDEO_DOUBAO_API_KEY` 显式读取环境变量，适用于 macOS、Linux、Windows。设置方式见 [安装说明](installation.md)。POSIX 用户也可自行选择显式 credentials_file/credentials_file_env 与 credential_key；其他用户可读的凭据文件会被拒绝。Windows 不用 POSIX 权限位检查 ACL，文件凭据路径会给出改用环境变量的提示。

先把示例复制到任务的 `video/config/tts.json`，不要把密钥写入该文件；以下命令的 `--config` 相对 video 根解析。

准备请求而不联网、不写音频：

```sh
python3 <skill>/scripts/synthesize_full.py tts \
  --project-root /path/to/video-root \
  --text script/narration.txt \
  --config config/tts.json \
  --output audio/vo-full.wav \
  --dry-run
```

明确执行一次整篇请求：

```sh
python3 <skill>/scripts/synthesize_full.py tts \
  --project-root /path/to/video-root \
  --text script/narration.txt \
  --config config/tts.json \
  --output audio/vo-full.wav
```

脚本会检查配置指定的字符数或字节数、端点配置、凭据是否可用，然后发送一个 POST。端点必须是没有 query/fragment 的 HTTPS URL；仅测试时可以在配置中显式打开 loopback HTTP。所有重定向都会被拒绝。HTTP 失败只报告状态，不读取或回显响应正文，因此不会把 token、原稿或服务端错误正文泄露到终端。

示例请求使用 `audio_format: pcm`，因为豆包 V3 HTTP 流式文档把 PCM、OGG Opus 和 MP3 列为流式输出格式，并提示 WAV 不支持流式；工具把完整 PCM 响应按配置的声道、位深和采样率封装为 WAV。若项目账号的当前接口支持 WAV，可把 `audio_format` 改成 `wav`。MP3/OGG 响应不能由标准库解码，工具会明确失败而不会写入未经验证的文件。

每次成功写入后，工具会完整读取 WAV 帧，检查 PCM 编码、声道、采样宽度、采样率、帧数与字节数，并计算 SHA-256 和毫秒时长。旁边的 `audio/vo-full.wav.meta.json` 保存 `text_sha256`、不含凭据的 request hash、音频 hash、采样参数和时长。重复执行时只有当音频重新解码、hash、文本 hash、请求 hash 与 metadata 全部一致才命中缓存；否则会重新请求。可以用 `--force` 忽略有效缓存并重新执行一次。

官方资料（2026-09-12 浏览核对）：

- [豆包语音大模型 HTTP Chunked 单向流式接口](https://docs.volcengine.com/docs/6561/2528925?lang=zh)：V3 端点、一次性输入文本、认证格式、音频编码与返回数据说明。
- [豆包语音鉴权方法](https://www.volcengine.com/docs/6561/1105162?lang=zh)：资源 ID 与 Bearer token 的配置方式。当前账号的资源 ID、音色、鉴权 header 可能随控制台服务类型变化，应以项目配置和账号对应的官方页面为准。

## 对齐：已知文本、ASR 与手工时间戳分开

最小命令如下；`--backend python` 是可运行的标准库后端：

```sh
python3 <skill>/scripts/align_narration.py align \
  --project-root /path/to/video-root \
  --text script/narration.txt \
  --audio audio/vo-full.wav \
  --output audio/alignment.json \
  --backend python
```

没有测量时间戳时，`python` 后端只输出一个覆盖整个已解码 WAV 的 `python-coarse` 段，并在 `issues` 写入 `NO_INTERNAL_BOUNDARIES`。这代表音频总时长边界，不代表词或字的声学起止；脚本绝不会按字数或字符数均分时间。

如果已有人工校准的短语时间戳，保存为项目内 JSON 并显式导入：

```json
[
  {"text": "你好", "start_ms": 120, "end_ms": 540},
  {"text": "Codex", "start_ms": 800, "end_ms": 1180}
]
```

```sh
python3 <skill>/scripts/align_narration.py align \
  --project-root /path/to/video-root \
  --text script/narration.txt \
  --audio audio/vo-full.wav \
  --output audio/alignment.json \
  --backend python \
  --timestamps script/manual-timestamps.json
```

时间戳按原稿顺序映射到原稿的真实切片。只由标点、符号或空格组成的差异会附着在相邻的有时间短语上，不会为标点另造声学时间；大小写、Unicode 归一化、标点和空格差异进入 `TEXT_FORMAT_DIFFERENCE`。包含实际字词的未覆盖原稿片段会保留为 `start_ms: null, end_ms: null`，并在 `issues` 标明未对齐区间；无法映射的 ASR 词进入 `ASR_WORD_DIFFERENCE`，不会被猜测到别的词。测量段必须在音频内、不能重叠，段与段之间的时间空档会原样保留为静音。

ASR 是另一条路径，不等同于已知文本对齐。把外部本地 ASR 工具产生的 JSON（脚本不选择绝对路径、不下载模型、不修改 ASR 环境）传给 `--backend asr`：

```sh
python3 <skill>/scripts/align_narration.py align \
  --project-root /path/to/video-root \
  --text script/narration.txt \
  --audio audio/vo-full.wav \
  --output audio/alignment.json \
  --backend asr \
  --asr-json inputs/asr.json
```

支持 `segments`、`result.utterances` 和 `result.words` 中带 `text`/`word` 与 `start_time`/`end_time`（毫秒）的常见 ASR 形状；`start`/`end` 按秒解释。ASR 文字先用于定位原稿，输出的 `segments[].text` 始终来自原稿；识别差异、原稿空档和尾部都会进入 `issues`。无法按顺序映射的导入会失败且不写出旧文件。

两种后端都输出以下契约：

```json
{
  "version": 1,
  "audio_path": "audio/vo-full.wav",
  "audio_sha256": "...",
  "text_sha256": "...",
  "method": "known-text-manual",
  "reviewed": false,
  "segments": [
    {"id": "seg-001", "text": "你好", "start_ms": 120, "end_ms": 540}
  ],
  "issues": []
}
```

`audio_path` 始终是相对项目根目录的路径，`segments` 拼接后必须等于完整原稿，测量段不会重叠，`reviewed` 需要人工听查后才由上层流程改变。脚本本身不声称已经完成人工审阅。

## 已验证范围与未验证项

`tests/test_audio.py` 使用标准库 `http.server` mock，不需要云凭据，覆盖整篇单请求、dry-run、UTF-8 超限不拆分、响应失败不泄密、重定向拒绝、WAV 全解码/hash 缓存、手工时间戳静音间隔、ASR/已知文本区分和重叠时间戳导入失败。

开发环境的历史实测不代表当前用户环境已验证。技能自带单元测试使用 `python3 -m unittest discover -s <skill>/tests -v`。

真实豆包请求需要项目管理员在当前环境中显式提供配置列出的凭据，并且会产生云端调用；没有凭据时不应尝试网络调用。每台机器仍须验证自身账户权限和本地 ASR 可用性，不能沿用另一台机器的验证结论。

可使用当前环境已有的 `transcribe` 技能在本机运行 ASR，再导入其 JSON；不要把 `python-coarse` 当作可用字幕。`TEXT_FORMAT_DIFFERENCE` 仅为格式提示，仍保留原稿；内容差异、无测量边界和未覆盖文本会阻止构建。
