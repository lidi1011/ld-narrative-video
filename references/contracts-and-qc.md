# 项目合同与检查

所有路径相对于任务的 `video/`。时间统一为整数毫秒，区间为 `[start_ms, end_ms)`；渲染按 `round(ms × fps / 1000)` 映射到帧。输出默认 16:9 / 1280 × 720，或 9:16 / 720 × 1280，支持 24/25/30/60 fps，模板为 30 fps。更改 fps 时同时更新渲染命令。

## 文件和字段

初始化模板含完整可运行的 48 秒无声工程示例。它是结构示例，替换主题和素材后再作为生产项目。

- `project.json`：`schema_version: 1`、`title`、`width`、`height`、`fps`、可选 `aspect_ratio`（须匹配尺寸）、`audio_mode`（`silent` / `narration` / `source`）；可选 `show_subtitles`。
- `script/timeline.json`：`schema_version: 1`、`duration_ms`、`events`、`audio`。事件有唯一 `id`、`start_ms`、`end_ms`、`text`；叙述事件的 `phrase_id` 指向实际对齐片段。事件不重叠；静音间隙可以没有事件。
- `script/shots.json`：`schema_version: 1`、`shots`。镜头有唯一 `S001` 型 `id`、`start_ms`、`end_ms`、`purpose`、`hero_state`、`title`、`recipe_id`、`presentations`、`items`（1–4 个字符串）、`event_ids`、`asset_ids` 和可选 `beats`。镜头完整、连续覆盖全片。每个事件归属一个镜头。变化点为 `{event_id, at_ms, item_index}`；每个 item 最多一个进入变化点，索引必须有效；镜头至少 300 ms，短镜头动画自动缩短；未设置的内容按进入顺序展开。单镜头支持一份可见素材；多份素材请拆镜头，参考图不占可见素材位。
- `assets/manifest.json`：`assets` 中每项有 `id`、`path`、`kind`（`image` / `video`）、`usage`（`evidence` / `illustration` / `fixture`）、`source` 和文件 `sha256`。只登记项目内文件；拒绝绝对路径、目录穿越、指向项目外的软链接。证据、示意、工程测试素材分开标记。
- 视频素材使用镜头级 `media_start_ms`（默认 0）裁取；默认 `preserve_audio: true`。无原声音轨时不创建伪音轨。真人模块输入实际视频，原声变更要符合用户要求。图像使用 contain，不能自动生成角色动作。
- `module_options.ip-character.reference_asset_ids` 是非空参考资产 ID 列表。无 IP 镜头无需此字段。
- `timeline.audio` 放置独立音轨：`{path, sha256, start_ms, end_ms, source_start_ms: 0}`。旁白必须完整使用同一份整篇音频，保留静音；不要逐句请求 TTS 或逐句拼接。
- `audio/alignment.json` 的音频、文案哈希、对齐片段、问题与听审状态见 `audio-tools.md`。使用真实测量结果；不能按字数冒充对齐。字幕保留定稿文本。

## 构建与渲染

```bash
python3 <skill>/scripts/build_storyboard.py --project-root <task>/video
cd <task>/video
npm ci
npm run check
npm run render
python3 <skill>/scripts/build_storyboard.py --project-root . --capture
python3 <skill>/scripts/check_project.py --project-root . --media renders/final.mp4
```

`--capture` 使用实际 HTML 和原生 `hyperframes snapshot --describe false`，不发起模型描述请求。可用 `--hyperframes /absolute/path/to/hyperframes` 指定已有本地运行时。快照在 `stills/`；需实际查看图片。联系表如需使用，应由这些快照拼接。初始化时脚本也复制到 `video/tools/`，所以任务工程可独立运行。`npm run render` 使用本地 `render_project.py`，把成片哈希绑定到当前构建；绕过它直接渲染的文件不能通过版本检查。首次 npm 安装需要网络；浏览器渲染需要 Chrome 和本地回环端口。默认中文字体为随包原版 Noto Sans CJK SC（OFL），字体文件参与构建哈希。doctor 的 --browser-check 实际等待字体加载；渲染与截图仍须检查真实画面。修改字体需重建并重新检查换行。

`shots.md` 与 `index.html` 是生成物，修改源 JSON 后重建。颜色、字体、版式在 `styles.css` 与 `DESIGN.md` 中修改，重建后检查每个受影响镜头。需要新布局时修改生成器并验证，而不是承诺任意布局已支持。

## 验证与失效

`qc/build.json` 记录输入、素材、声音、HTML 与生成器哈希。`check_project.py` 会拒绝过期构建，并在提供成片时检查流、尺寸、帧率、帧数（误差最多 1 帧）、音轨是否符合模式，以及全文件解码。有声输出另外与声明的源混音做 500 ms 窗口的 PCM 相关性检查，发现漏音、错误来源或偏移；这不是听感与音量审阅。禁止同源重叠放置造成重复混音。输出 `qc/report.json`。

技术 PASS 不等于视觉、听感或事实通过：实际查看关键帧、转场和全片；检查中文溢出、遮挡、信息节奏、字幕可读性；有声音时检查发音、停顿、同步、截断和混音。把实际审阅范围单独记录在 HANDOFF。没有执行的检查写为待完成。

改画面不合成新旁白；改文案或音频使对齐与字幕失效。替换资产需更新来源及哈希。重建后旧视频也需重渲染，不能只校验它的尺寸。保留新旧修改记录，避免把旧成片当成新构建。

迁移时复制完整任务目录，不复制 node_modules，运行 `npm ci` 后重建；不得依赖其他业务项目的路径或状态。豆包的私有配置由当前项目显式提供，技能包不包含密钥。

字幕框固定在画面下方；当前布局适合短句。长句应按真实短语边界拆事件并调整画面，不得为了塞入字幕改写定稿。自动合同检查不能替代长文本的浏览器溢出检查。

## 单独导出字幕

`python3 <skill>/scripts/export_subtitles.py --project-root <video>` 从同一事件表输出 `captions.srt`，保留原稿和实测毫秒，不合成声音。`qc/subtitles.json` 记录时间轴与字幕哈希；时间轴改变后重新导出。初始化任务自带同名 `tools/` 脚本。

## 画幅选择

初始化默认 `--aspect-ratio 16:9`；竖屏传 `--aspect-ratio 9:16`。`styles.css` 是基础样式，`portrait.css` 是竖屏专用覆盖，由生成器根据 project.json 尺寸加载。720×1280 画布原生渲染，不缩放横屏画布。竖屏标题预留最多两行、主体区从 y=260 开始，左右边距 48 px；素材区 624×430，保持 contain，说明在素材下方。字幕距底部 150 px，建议两行以内；长句按实测短语拆分。边距是模板基础值，不代表每个平台的界面安全区均已验证。

改画幅应从最新模板新建任务，并迁移文案、音频、素材及分镜数据；重新选择布局与文字密度。旧任务保留其自带工具和已验证成片。portrait.css 参与构建指纹，修改后需要重建、重新抽帧与渲染。
