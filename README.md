# 🎪 Video Circus

独立使用、可串联的视频技能包。已实现 **🎩 circus-conjurer**（获取）、**🤹 circus-juggler**（理解）和 **🎫 circus-ticket**（交付）。
总入口 **🎪 video-circus** 已实现，由宿主 Agent 连续编排三个子技能。

原 `video-fetch` 更名为 `circus-conjurer`；脚本、`video-fetch/1` 清单契约、环境变量和运行环境目录保持兼容。安装新版后移除旧技能目录，避免重复触发。

## 🎪 一次调用完成流程

安装总入口和三个子技能后，可以直接告诉 Agent：

```text
使用 $video-circus 看懂这个视频，生成可阅读、可检索、可回查依据的 HTML 报告：<URL或本地文件>
```

总入口默认获取 → 理解 → 交付，不在阶段间重复确认。已有媒体包、materials_ready准备包或最终内容包会从对应阶段继续；用户只要求下载/理解时按指定范围结束。每个阶段用 🎩、🤹、🎫 标识，总入口使用 🎪。

这是由宿主 Agent 执行的技能编排，没有独立的一键 CLI。文字与画面理解、证据审阅及编辑编排仍由 Agent 完成；不是三个脚本连续执行后就宣称看懂。总入口不新增工具依赖，各阶段仍按下表安装运行工具。实际需要选择视频、处理访问权限或补齐缺失依赖时，会保留已完成产物并指出下一步。已有结果先核验再复用，partial和局部范围继续保留到报告。

## 安装与依赖

技能文件和运行依赖需要分别安装。完整流程安装 `skills/video-circus` 及三个子技能。也可以仅安装所需的 `skills/circus-conjurer`、`skills/circus-juggler`、`skills/circus-ticket` 文件夹放入宿主 Agent 的技能目录；三个技能可以独立安装和调用。安装技能不会自动安装工具或下载模型。

| 依赖 | 🎩 获取阶段 | 🤹 理解阶段 | 🎫 交付阶段 | 用途与要求 |
| --- | --- | --- | --- | --- |
| Python 3.10+ | 必需 | 必需 | 必需 | 脚本只使用标准库，无额外 Python 包要求；确认实际调用的 `python3` 版本 |
| FFmpeg 与 ffprobe | 获取、验证媒体时必需 | 分析视频/音频时必需 | 不需要 | 解码验证、探测音视频轨、提取音频、抽帧；两阶段共用同一安装 |
| yt-dlp | 平台提取及部分流媒体需要 | 不需要 | 不需要 | 本地视频理解不依赖下载工具；仅获取本地文件也不需要 yt-dlp |
| whisper.cpp 的 `whisper-cli` | 不需要 | 本地 ASR 时需要 | 不需要 | 无字幕、字幕缺口或字幕质量不足时进行语音转写；无需 ASR 时可省略 |
| 多语言 Whisper GGML 模型 | 不需要 | 本地 ASR 时需要 | 不需要 | 与 whisper.cpp 兼容的独立模型文件；中文/多语言不要使用仅英文 `.en` 模型 |
| 宿主浏览器工具 | 动态网页发现时需要 | 不需要 | 页面验收时需要 | iframe、动态播放器等发现依赖宿主实际提供的能力 |
| 宿主专用只读下载工具及已有登录态 | 某些受限动态页面需要，可选 | 不需要 | 不需要 | 例如钉钉录制可用宿主听记下载能力；本地输入不需要，也不随技能安装 |
| 宿主图片读取工具与视觉模型 | 不需要 | 理解画面时需要 | 不需要 | Agent 阅读帧中的界面、文字、图表与操作；仅完成抽帧不等于理解画面 |

### 从 GitHub 安装

```bash
git clone https://github.com/somkanel/video-circus.git
```

将仓库 `skills/` 下四个技能目录复制到宿主 Agent 的技能目录。Codex 默认为 `~/.codex/skills/`；已有同名技能时先对比版本，保留自己的修改。完整流程需要四个目录，单独使用某个阶段只需相应子技能。运行工具与模型仍按依赖表另行安装。

### macOS 安装示例

已安装 Homebrew 时，可以独立安装工具：

```bash
brew install python ffmpeg yt-dlp whisper-cpp
python3 --version
ffmpeg -version
ffprobe -version
yt-dlp --version
whisper-cli --help
```

仅使用交付阶段只需 Python 3.10+；浏览器用于实际页面验收。若使用获取或理解阶段，按上表安装所需工具即可；已经可用的依赖不必重复安装。提取器版本可能影响平台下载，应结合实际失败判断是否更新。

Whisper 模型需要另行下载。按 [whisper.cpp 模型说明](https://github.com/ggml-org/whisper.cpp/tree/master/models) 获取多语言 GGML 模型；当前已测 `large-v3-turbo`，文件约 1.5 GB，运行还需数 GB 内存，实际占用和速度取决于模型、硬件及片长。工具安装不代表模型已安装，模型文件也不包含在技能 ZIP 中。

把已有模型路径传给脚本：

```bash
python3 skills/circus-juggler/scripts/juggle.py doctor --model '/path/ggml-large-v3-turbo.bin'
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/video.mp4' \
  --model '/path/ggml-large-v3-turbo.bin' --output './juggler-output'
```

也可以设置 `CIRCUS_WHISPER_MODEL`。未显式指定时，仅检查已有的 `~/.cache/whisper/ggml-large-v3-turbo.bin`，不会自动联网下载。

Linux/Windows 按各工具的官方安装方式提供相同 CLI；当前真实运行验证在 macOS Apple Silicon 上完成，尚未证明所有操作系统都可直接运行。

### 依赖检查与缺失处理

```bash
python3 skills/circus-conjurer/scripts/fetch.py --doctor
python3 skills/circus-juggler/scripts/juggle.py doctor
```

检查结果包含实际工具路径、版本提示，以及理解阶段的模型存在状态。`doctor` 不等于实际下载或模型推理已经成功。

- 缺少 ASR 工具或模型：仍可准备已有字幕和画面，明确记录音频缺口；没有字幕时不能交付完整语音理解。仅使用现有字幕可选 `--asr never`。
- 缺少视觉能力：可以做字幕/音频分析，但明确画面未检查，不能宣称完成多模态理解。
- GPU/Metal 初始化失败：理解阶段可尝试一次 `--cpu`，使用新的输出目录；耗时可能增加。
- 工具未进入 PATH：获取阶段可用 `VIDEO_FETCH_YTDLP` 指定 yt-dlp；理解阶段可用 `CIRCUS_FFMPEG`、`CIRCUS_FFPROBE`、`CIRCUS_WHISPER_CLI` 指定对应可执行文件。

本地 ASR 和抽帧不上传视频；Agent 的文字/图片推理是否经过云端取决于宿主模型。本版本没有云端原生视频 API 适配器，不需要为脚本配置云服务 API Key。

本仓库代码采用 MIT；外部工具、模型及其依赖的许可分别见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，下载/运行与再分发的要求需分别判断。本发布包不包含第三方二进制、模型权重或用户媒体。

## 使用

使用已安装的 `circus-conjurer` 获取媒体：

```bash
python3 skills/circus-conjurer/scripts/fetch.py --doctor
python3 skills/circus-conjurer/scripts/fetch.py '/path/video.mp4' --output './video-fetch-output'
python3 skills/circus-conjurer/scripts/fetch.py 'https://example.com/lesson' --output './video-fetch-output'
python3 skills/circus-conjurer/scripts/fetch.py 'https://example.com/video' --mode subtitles --langs 'zh.*,en.*'
```

动态播放器通过 Agent 的宿主浏览器完成发现，详见 skill 内引用。
脚本默认匿名，不升级工具、不读取浏览器 Cookie、不操作系统代理。
网络失败时保留任务目录；必要会话回退由 Agent 根据用户任务授权选择。

浏览器或专用只读工具已取得本地文件时，可以附带来源记录，再验证原网页时长与文件时长：

```bash
python3 skills/circus-conjurer/scripts/fetch.py '/path/downloaded.mp4' \
  --origin-file '/path/origin.private.json' --output './verified-media'
```

来源JSON的六个字段和证据边界见 [浏览器发现](skills/circus-conjurer/references/browser-discovery.md)。记录只采用已观察值并绑定媒体SHA256；没有逐字稿时可以继续下载视频，不需要先触发云端转写。通用脚本不会自动调用钉钉等专用工具。

## 🤹 理解本地视频

独立安装 `skills/circus-juggler`；ASR 使用本地 whisper.cpp 和独立模型，不随包分发。

```bash
python3 skills/circus-juggler/scripts/juggle.py doctor
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/video.mp4' --output './juggler-output'
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/acquired/manifest.json' --output './juggler-output'
```

Agent 继续阅读逐字稿和图片，形成 review.json 后调用 finalize。材料准备状态为 materials_ready，不能冒充理解完成。
详细审阅契约见技能内 references/handoff.md；云端原生视频模型是可选后端，未在此版本实现 API 适配器。

### 无字幕及低音量疑点

默认 `--asr auto` 转写字幕缺口，并跳过至少10秒的估计低音量区间；`--asr always` 对指定范围全部执行转写，包含低音量，已有字幕仍作为备用证据保存。

```bash
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/video.mp4' \
  --range 3916:3942 --asr always --language zh --output './tail-recheck'
```

`asr_processed` 是实际执行范围；`asr_skipped_quiet` 是自动模式跳过的低音量范围；`audio_not_transcribed` 是没有主字幕且未执行ASR的范围。不要只看旧字段 `unprocessed_audio` 判断全程已转写。强制转写可能把静音识别成文字，`speech_on_estimated_quiet` 提示需要复核，不自动删除原文。

完整审阅仍需要实际复听估计低音量区间，并在audio_checks记录时间与观察。仅设置“已核对”布尔值不会解除缺口；没有复听能力继续交付partial。新参数/新实现使用新输出目录，旧验收包保留。来自获取阶段时，上游manifest路径与哈希一同封存，来源记录被改动会阻止复用旧理解包。

## 🎫 交付阅读报告

独立安装 `skills/circus-ticket`。Agent 阅读最终内容包，编写带证据引用的 `editorial.json`，再生成报告；用户无需手工填写 JSON。格式见 [报告输入](skills/circus-ticket/references/report-input.md)。

```bash
python3 skills/circus-ticket/scripts/ticket.py '/path/understanding/final/manifest.json' \
  --editorial '/path/editorial.json' --output './ticket-report'
```

默认生成自包含的 `report.html`：简报、可折叠章节、观点/边界/应用/问答、关键画面、可检索转写和依据窗口；另附 `report.md`、`report.json`、`manifest.json`。可选模块不强制填满。无需 Node、CDN、FFmpeg、Whisper 或云服务 API；核验时仍需原内容包、媒体及被封存材料可访问。

只接收已审阅的 complete/partial 包，拒绝 materials_ready、stale、被修改的材料或未审阅引用。partial 在页首与待确认事项中保留，不因排版完成升级内容状态。原字幕、校正稿及采样画面仍有各自证据边界。

HTML 嵌入已查看且有观察记录的画面与文字，不内嵌原视频或音频；第一版时间标签不提供播放器跳转。输出目录须独立且为空，旧报告保留。报告生成后由 Agent 用宿主浏览器检查布局与交互，单独记录 `qa.md`；manifest 的 rendered 只表示渲染成功。打印入口已提供，PDF 分页和实际导出尚未完成验收。

用户只给 URL/文件时，Agent 可以依次使用获取 → 理解 → 交付技能；也可以通过已安装的 `video-circus` 总入口执行。公开技能 ZIP 不包含真实报告、逐字稿、画面、媒体或账户信息。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

测试生成短媒体并在本机 HTTP 服务中验证直链、iframe、多视频选择、
流媒体、损坏文件、缓存和私有输入脱敏。真实平台覆盖单独记录在
`docs/validation.md`，不能把模拟测试视为平台兼容性证明。

## License

MIT. No third-party binaries are bundled.
