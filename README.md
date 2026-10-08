<div align="center">
  <h1>🎪 Video Circus</h1>
  <p><b>把视频变成一份读得懂、查得到依据的报告。</b></p>
  <p>中文 · <a href="README.en.md">English</a></p>
</div>

适用于 **Codex、Claude Code 等 Agent Harness** 的视频技能套件：**获取视频 → 理解字幕、声音与画面 → 交付 HTML 阅读报告**。

- 接收平台链接、网页嵌入视频或本地文件。
- 没有字幕时，使用本地 Whisper 转写；支持中文、英文及多语言处理。
- 章节、关键画面和转写保留时间与证据引用，疑点单独列出。
- 三个阶段可以独立调用，也可以交给总入口连续完成。

## 安装

使用 [Skills CLI](https://github.com/vercel-labs/skills)，需要 Node.js / npm 和 Git：

```bash
npx skills add somkanel/video-circus --skill '*' -a codex claude-code -g
```

这会安装总入口和三个子技能。只使用一个 Harness 时，保留 `-a` 后对应的名称；去掉 `-g` 可安装到当前项目。安装后新建会话，再调用技能。

**也可以把下面这段直接发给你的 Codex 或 Claude Code：**

```text
请从 https://github.com/somkanel/video-circus 安装 Video Circus。
将 video-circus、circus-conjurer、circus-juggler、circus-ticket 四个技能
安装到当前 Harness 的用户级技能目录，保留已有同名技能的自定义修改。
检查 Python、FFmpeg、yt-dlp，以及本地转写所需的 whisper.cpp 和多语言模型，
告诉我缺少哪些依赖。不要自动下载模型或上传视频。
```

<details>
<summary>手动安装与其他 Harness</summary>

```bash
git clone https://github.com/somkanel/video-circus.git
```

将仓库 `skills/` 下四个完整目录复制到目标位置，保留其中的脚本、模板和引用文件：

| Harness | 用户级安装 | 项目级安装 |
| --- | --- | --- |
| [Codex](https://developers.openai.com/codex/skills/) | `~/.agents/skills/` | `.agents/skills/` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills/` | `.claude/skills/` |

其他支持 Agent Skills 的 Harness 可通过 `npx skills add somkanel/video-circus -g` 选择安装目标，或使用其文档指定的技能目录。浏览器发现、图片读取和本地命令执行能力由 Harness 提供；不同宿主的功能覆盖可能不同。

</details>

## 使用

**Codex**，用 `$` 调用：

```text
$video-circus 看懂这个视频，整理成带章节、关键画面和证据回查的中文报告：<URL 或本地文件路径>
```

**Claude Code**，用 `/` 调用：

```text
/video-circus 看懂这个视频，整理成带章节、关键画面和证据回查的中文报告：<URL 或本地文件路径>
```

可以指定读者、范围或重点，比如“写给刚入职的同事”“只看 10:00 到 25:00”“整理操作步骤与功能限制”。已有媒体包或已审阅内容包，也可以直接交给总入口继续处理。

## 技能

| 技能 | 用途 | 产物 |
| --- | --- | --- |
| [🎪 video-circus](skills/video-circus/SKILL.md) | 一次完成全流程，或从已有产物继续 | 最终报告 |
| [🎩 circus-conjurer](skills/circus-conjurer/SKILL.md) | 获取并验证视频、字幕与来源 | 媒体包 |
| [🤹 circus-juggler](skills/circus-juggler/SKILL.md) | 转写语音、阅读字幕、查看画面并核对疑点 | 带时间与证据的内容包 |
| [🎫 circus-ticket](skills/circus-ticket/SKILL.md) | 将已审阅内容整理成阅读报告 | HTML、Markdown、JSON |

独立调用时，Codex 使用 `$circus-conjurer` 等名称，Claude Code 使用 `/circus-conjurer` 等命令。总入口由 Agent 编排，实际阅读和审阅由 Agent 完成，没有独立的一键 CLI。

## 产出

默认生成自包含的 `report.html`：

- **简报与章节**：先读主线，再展开细节，支持折叠与搜索。
- **关键画面与依据**：点击查看对应转写或采样帧，区分讲话者主张、画面观察和整理者归纳。
- **可检索转写**：保留时间标签、校正记录的上游依据及未确认内容。
- **边界与复习**：按需组织观点、应用建议、问答和待确认事项。

另附 `report.md`、`report.json` 和报告清单。HTML 内含文字与已审阅图片，不依赖 CDN，默认不嵌入原音视频；Markdown 保留正文、时间与证据 ID，完整转写和画面回查在 HTML 中。

## 运行依赖

安装技能不会自动安装工具或语音模型。

| 依赖 | 用途 |
| --- | --- |
| Python 3.10+ | 三个阶段的脚本运行，仅用标准库 |
| FFmpeg / ffprobe | 媒体验证、音频提取与抽帧 |
| yt-dlp | 平台提取及部分流媒体下载 |
| whisper.cpp + 多语言 Whisper GGML 模型 | 没有字幕或需要复查时，本地语音转写 |
| Harness 的浏览器、图片读取与视觉能力 | 动态播放器发现、画面理解和报告检查 |

只使用报告阶段，需要 Python 和可用的原内容包；浏览器用于页面验收。只用已有字幕时，可以省略语音转写工具。

<details>
<summary>macOS 安装工具与配置模型</summary>

```bash
brew install python ffmpeg yt-dlp whisper-cpp
```

按 [whisper.cpp 模型说明](https://github.com/ggml-org/whisper.cpp/tree/master/models) 单独获取多语言 GGML 模型，不要为中文视频选择仅英文的 `.en` 模型。已测 `large-v3-turbo`，模型约 1.5 GB，推理还需要数 GB 内存。

可以设置 `CIRCUS_WHISPER_MODEL`，或在脚本参数中传入 `--model`。默认只检查已有的 `~/.cache/whisper/ggml-large-v3-turbo.bin`，不会自动下载。工具路径、选轨和局部复查见 [本地 ASR](skills/circus-juggler/references/asr.md)。

</details>

## 支持范围

平台链接优先用 yt-dlp；普通网页检查媒体与 iframe，动态播放器由宿主浏览器继续发现。登录内容需要已有访问权限，不保证任意 URL 都能获取，不绕过 DRM，微信视频号不作为保证覆盖的平台。

本地转写和抽帧不上传视频；Agent 的文字和图片推理是否经过云端，取决于 Harness 配置。当前没有原生云端视频 API 适配器。

字幕、语音识别和画面采样可能有误差，报告保留局部范围与待确认项。默认没有视频播放器或时间跳转；打印入口已提供，PDF 导出和分页尚未完成验收。真实运行主要在 macOS Apple Silicon 上验证，其他系统与 Harness 仍需分别验证。

## 为什么叫 Circus

把看懂视频安排成一场马戏：🎩 **Conjurer** 从帽子里“变出”素材，🤹 **Juggler** 同时照看字幕、声音和画面，🎫 **Ticket** 则是交到读者手中的入场券。整场表演由 🎪 **Video Circus** 串起来，进度消息也用这些符号标识当前阶段。

## 文档与许可

[审阅与证据格式](skills/circus-juggler/references/handoff.md) · [报告输入](skills/circus-ticket/references/report-input.md) · [验证记录](docs/validation.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

代码、技能指引与模板采用 [MIT](LICENSE)。外部工具和模型单独安装，按各自许可使用；仓库不包含模型、第三方二进制或真实视频、逐字稿与报告。
