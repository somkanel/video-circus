# Circus Juggler Implementation Plan

**Goal:** 实现本地优先的独立视频理解技能，交付可追溯内容包。

**Architecture:** Python 标准库 CLI 处理字幕、FFmpeg 媒体材料和 whisper.cpp 转写；宿主 Agent 读取材料并提交有证据的审阅结果；确定性校验器验证引用、修改依据和审阅覆盖后生成交接包。材料准备不能自动声明语义理解完成。

**Tech Stack:** Python 3.10+、FFmpeg/ffprobe、whisper.cpp（外部安装）、本地多语言模型、宿主视觉工具。

## 1. 材料管线

创建 `skills/circus-juggler/scripts/juggle.py`，实现 doctor、prepare、frames、finalize。
准备阶段接收本地媒体或 video-fetch/1 manifest；校验上游文件哈希；解析 SRT/VTT/Whisper JSON；保留原文件副本和字幕轨；明确选轨；音频时间轴补齐；按需处理字幕缺口，分块运行 ASR 并按中点分配重叠字幕；逐段缓存校验，输出字幕和异常标记。
用定时抽帧建立底稿，支持局部范围补帧；抽出帧不能写成已经阅读。

## 2. 审阅与交接

定义引用 ID、处理范围、视觉采样和未解决项。Agent 提交 review.json，包括实际读过的帧、逐字稿段、章节、带引用的内容单元和校正记录。校验有效 ID、时间范围、类型、校正原文和依据，保留原始文本。未经审阅或有未覆盖范围的包不得标为 complete。

## 3. 技能与许可

创建 SKILL.md、agents/openai.yaml、references/handoff.md、references/asr.md 和独立 MIT LICENSE。README 加入已实现入口；第三方说明包含 whisper.cpp 和模型许可边界。不得打包模型、媒体、第三方二进制或测试私有数据。

## 4. 行为验证

创建 tests/test_juggle.py：字幕滚动去重、时间偏移、重叠分块、字幕缺口、不可用/篡改媒体、无音轨、局部范围、坏引用、无证据校正、未读帧不能完成。使用生成短媒体验证抽帧和时间轴，再在真实本地中英片段运行 ASR，并实际看图后完成审阅交接。

## 5. 交付

运行相关测试和 skill validator，安装本地技能，校对安装内容，生成独立 ZIP 和整套 ZIP；记录已验证范围和未验证范围。阶段三及总入口仍不发布。
