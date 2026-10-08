# 🎪 Video Circus

[English](README.en.md) · 中文

给 Agent 一个视频链接或本地文件，让它获取素材、理解内容，再交付一份方便人阅读的报告。

Video Circus 将这件事拆成三个独立子技能，由一个总入口串联。适合整理课程、产品培训、演示和访谈，尤其是需要同时核对讲话与画面、保留时间和依据的长视频。

## 一张票之前，要做三件事

| 角色 | 技能 | 负责什么 | 交付什么 |
| --- | --- | --- | --- |
| 🎪 整场马戏 | `video-circus` | 识别输入、衔接阶段、从已有产物继续 | 完整流程与最终报告 |
| 🎩 魔术师 | `circus-conjurer` | 获取视频并验证媒体 | 视频或字幕、来源记录、媒体清单 |
| 🤹 杂耍演员 | `circus-juggler` | 阅读字幕、转写语音、查看画面并核对疑点 | 带时间和证据引用的内容包 |
| 🎫 入场券 | `circus-ticket` | 提炼内容、组织阅读层次、渲染报告 | 自包含 HTML、Markdown、JSON |

命名时，希望每个阶段既能一眼辨认，又有一点趣味。获取阶段最初考虑过松鼠、蚂蚁、蜜蜂，取的是收集素材的意思；后来决定把整套技能放进同一个马戏团，🎩 就成了把视频素材“变出来”的魔术帽，英文名字是 **Conjurer**。

理解阶段叫 **Juggler**，因为 Agent 要同时照看字幕、声音和画面，让几条证据互相补充、校正。交付阶段曾考虑用报纸，最后选了 **Ticket**：马戏已经准备好，读者拿到一张票，就能入场。报告也应该如此，打开之后先看清主线，再按需要走进细节。

这几个符号也用于 Agent 的进度消息：🎪 表示总流程，🎩、🤹、🎫 告诉你现在进行到哪一步。

## 你会拿到什么

默认交付一份自包含的 HTML 阅读报告，文字和已审阅的关键画面放在同一文件中：

- 简报先讲主线，详细章节保留时间范围，支持折叠与搜索。
- 观点、能力边界、应用建议和问答按内容需要组织。
- “查看依据”打开对应的转写或画面，区分讲话者主张、画面观察和整理者归纳。
- 校正转写可检索，待确认事项与来源说明保留下来。

同时生成 `report.md`、`report.json` 和 `manifest.json`。Markdown 保留正文、时间与证据 ID，完整转写和图片回查在 HTML 中。报告无需外部字体、CDN 或第三方前端库，默认不嵌入原视频或音频。

## 快速开始

安装总入口和三个子技能后，告诉 Agent：

```text
使用 $video-circus 看懂这个视频，生成方便阅读、可检索、可回查依据的 HTML 报告：
<视频 URL 或本地文件路径>
```

也可以补充阅读目标，比如“写给第一次接触这个产品的同事”“只分析 10:00 到 25:00”或“重点整理操作步骤和限制”。报告语言跟随你的要求，逐字稿保留源语言。

总入口会从合适的阶段开始：URL 或文件先获取，已有媒体包进入理解，已审阅的最终内容包直接生成报告。阶段间不重复询问是否继续；需要选择正文视频、补齐依赖或处理访问权限时，会说明具体阻碍并保留已有产物。

三个子技能也可以单独使用：

```text
使用 $circus-conjurer 下载并验证这个视频：<URL>
使用 $circus-juggler 分析这个本地视频：<文件路径>
使用 $circus-ticket 将这个已审阅内容包整理成阅读报告：<final/manifest.json>
```

总入口由宿主 Agent 编排，没有独立的一键 CLI。脚本负责获取和转换素材、核验交接、渲染报告；实际阅读、画面理解、证据审阅与内容提炼由 Agent 完成。

## 安装

```bash
git clone https://github.com/somkanel/video-circus.git
cd video-circus
```

将 `skills/` 下四个目录复制到宿主 Agent 的技能目录：

```text
video-circus/
circus-conjurer/
circus-juggler/
circus-ticket/
```

Codex 默认为 `~/.codex/skills/`；其他宿主使用各自的技能目录。已有同名技能时先对比版本，保留自己的修改。只用某个阶段时，可以仅安装对应子技能；完整流程需要总入口和三个子技能。

**技能文件、运行工具和语音模型需要分别安装。** 复制技能目录不会自动安装依赖或下载模型。

### 运行依赖

| 依赖 | 🎩 获取 | 🤹 理解 | 🎫 交付 |
| --- | --- | --- | --- |
| Python 3.10+ | 必需 | 必需 | 必需 |
| FFmpeg / ffprobe | 获取、验证媒体时需要 | 分析音视频时需要 | 不需要 |
| yt-dlp | 平台提取及部分流媒体需要 | 不需要 | 不需要 |
| whisper.cpp 的 `whisper-cli` | 不需要 | 本地语音转写时需要 | 不需要 |
| 多语言 Whisper GGML 模型 | 不需要 | 本地语音转写时需要 | 不需要 |
| 宿主浏览器工具 | 动态网页发现时需要 | 不需要 | 页面验收时需要 |
| 宿主图片读取工具与视觉模型 | 不需要 | 理解画面时需要 | 不需要 |

Python 脚本只用标准库。总入口不新增运行依赖；某些受限网页还需要宿主提供的专用只读下载工具和已有登录态，这些能力不随技能分发。

在已安装 Homebrew 的 macOS 上，可以安装运行工具：

```bash
brew install python ffmpeg yt-dlp whisper-cpp
python3 --version
python3 skills/circus-conjurer/scripts/fetch.py --doctor
python3 skills/circus-juggler/scripts/juggle.py doctor
```

确认实际调用的 Python 版本符合要求。只用交付阶段时，Python 3.10+ 即可运行渲染器，浏览器用于查看和检查结果。

### 语音模型

按 [whisper.cpp 模型说明](https://github.com/ggml-org/whisper.cpp/tree/master/models) 单独获取兼容的多语言 GGML 模型。中文或多语言视频不要选择仅英文的 `.en` 模型。

当前已测 `large-v3-turbo`，模型约 1.5 GB，运行还需数 GB 内存；速度和内存占用取决于硬件、模型与片长。通过参数指定已有模型：

```bash
python3 skills/circus-juggler/scripts/juggle.py doctor \
  --model '/path/ggml-large-v3-turbo.bin'
```

也可以设置 `CIRCUS_WHISPER_MODEL`。未显式指定时，脚本只检查已有的 `~/.cache/whisper/ggml-large-v3-turbo.bin`，不会自动下载。

Linux 和 Windows 按工具的官方方式安装相同 CLI。实际运行验收目前主要在 macOS Apple Silicon 上完成。

## 视频从哪里来

| 输入场景 | 处理方式与边界 |
| --- | --- |
| 本地视频 | 探测、解码检查并记录哈希，默认引用原文件 |
| YouTube、Bilibili 等平台链接 | 优先由 yt-dlp 提取视频及可用字幕；平台版本和访问条件影响结果 |
| 普通网页中的 `video`、`source` 或 iframe | 静态发现可用媒体，必要时继续检查嵌入页面 |
| 动态播放器、HLS / DASH、`blob:` | 静态提取不足时由宿主浏览器观察真实播放器，再按可用路径获取；`blob:` 本身不是可下载文件地址 |
| 没有 CC 字幕 | 提取音频，使用本地 Whisper 转写，再结合画面理解 |
| 已有媒体包或内容包 | 核验来源和封存材料后，从对应阶段继续 |

支持多语言处理，现有真实验收覆盖中文、英文，以及中文讲话中的英文术语。所有混合语种的准确性尚未得到验证。

浏览器或专用只读工具取得视频后，可以用 `--origin-file` 记录实际观察到的来源、标题和时长，并绑定媒体哈希，详见 [浏览器发现](skills/circus-conjurer/references/browser-discovery.md)。没有平台转写也可以继续下载和本地分析，不需要先生成云端纪要。

## 手动调用脚本

以下命令从仓库根目录执行。日常完整流程可以直接交给 Agent，这些命令用于单独运行阶段或排查问题。

```bash
# 获取并验证
python3 skills/circus-conjurer/scripts/fetch.py 'https://example.com/lesson' \
  --output './acquired'

# 准备字幕、音频和画面
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/acquired/manifest.json' \
  --model '/path/ggml-large-v3-turbo.bin' --output './understanding'

# Agent 实际阅读素材、写好 review.json 后，形成最终内容包
python3 skills/circus-juggler/scripts/juggle.py finalize './understanding' \
  --review '/path/review.json'

# Agent 编写带证据引用的 editorial.json 后，生成报告
python3 skills/circus-ticket/scripts/ticket.py './understanding/final/manifest.json' \
  --editorial '/path/editorial.json' --output './report'
```

获取脚本会返回实际任务目录，以产物中的路径为准。报告渲染时，原内容包、媒体和被封存素材须可访问；输出目录须独立且为空。

默认 `--asr auto` 处理字幕缺口，并跳过至少 10 秒的估计低音量区间。`--asr always` 转写指定范围的全部音频，包括低音量区间；`--asr never` 只使用已有字幕和视觉材料。估计低音量不等于没有讲话，强制转写也可能产生幻觉，疑点需要核对并保留记录。

选轨、时间偏移、局部复查、补帧与环境变量见 [本地 ASR](skills/circus-juggler/references/asr.md) 和 [审阅契约](skills/circus-juggler/references/handoff.md)；报告输入格式见 [报告输入](skills/circus-ticket/references/report-input.md)。

## 怎样判断完成

每个阶段有自己的完成条件。拿到可播放视频、生成逐字稿和完成内容审阅是不同的结果。

- `materials_ready`：素材准备完成，Agent 还需要阅读和审阅。
- 理解阶段的 `complete`：指定输入范围的审阅和交接检查完成，仍有采样边界。
- `partial`：上游缺失、仅分析局部、未审阅素材或仍有疑点，报告继续保留这些限制。
- `stale`：素材发生变化，旧审阅结果需要更新。
- 报告的 `rendered`：文件生成成功，页面验收另行记录，不改变上游内容状态。

画面只有实际查看并写下观察才算证据。文字校正保留原稿和依据，材料与交接文件通过 SHA256 核验；已有结果核验通过才复用，输入或参数变化使用新目录。

## 当前边界与隐私

任意网页都可以作为尝试入口，但无法保证任意 URL 都能取得视频。动态发现依赖宿主能力，登录内容依赖已有访问权限；不绕过 DRM 或访问控制，微信视频号不作为保证覆盖的平台。

本地语音转写和抽帧不会上传视频。Agent 阅读文字和图片是否经过云端，取决于宿主模型；当前没有云端原生视频 API 适配器。

HTML 默认没有原视频播放器，时间标签不提供播放跳转。打印入口已提供，实际 PDF 导出和分页尚未完成验收。语音识别、字幕和采样画面均有误差，不能将报告视为逐帧、逐字无误的记录。

真实任务包可能包含私有视频、讲话和页面信息，分享前按需要选择文件。公开仓库不包含视频、音频、逐字稿、真实报告、账户信息、模型权重或第三方二进制。

## 验证与许可

```bash
python3 -m unittest discover -s tests -v
```

发布前完整测试为 70 项通过，覆盖本机 HTTP 媒体获取、字幕与审阅、证据引用、哈希、输出隔离等。测试需 FFmpeg / ffprobe 及本机回环 HTTP 服务权限；模拟测试不等于全部平台兼容。真实平台、约 66 分钟无平台字幕的培训验收和已知限制见 [验证记录](docs/validation.md)。

代码、技能指引与模板采用 [MIT](LICENSE)，独立实现，不分发外部工具或模型。yt-dlp、FFmpeg、whisper.cpp 和具体模型的许可分别适用，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。

从旧版升级时，原 `video-fetch` 已更名为 `circus-conjurer`；`video-fetch/1` 清单与已有环境变量保持兼容。确认旧目录没有自己的修改后，再移除重复安装，避免同时触发。
