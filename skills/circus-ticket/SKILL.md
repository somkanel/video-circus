---
name: circus-ticket
description: 将已审阅的视频内容包整理为可阅读、可检索、可回查证据的HTML报告及Markdown笔记。用于课程、培训、演示和视频研究的交付阶段；不下载视频、不重新转写，也不把未审阅素材当已理解内容。
metadata:
  version: "0.1.0"
---

# 🎫 Circus Ticket

🎪 Video Circus 的交付阶段。首条进度和最终交付首句以 🎫 开头。可以独立安装，消费已有 `circus-juggler/1` 最终内容包；不要求同时安装获取/理解技能。

## 先理解交接内容

读取最终 manifest、content、review 与 coverage；只消费 `complete` 或 `partial`，拒绝 materials_ready 和 stale。partial可以交付有用报告，在页首和待确认事项保留限制；不因排版完成升级内容审阅状态。

先确认视频类型、目标读者、范围和用户指定样例。默认采用分层阅读：简报 → 详细章节 → 关键观点与边界 → 应用/复习 → 可检索转写 → 来源说明。适合长培训的编辑式报告，不强制短视频也填满所有模块。标题、信息密度、章节和语言服务读者，不把emoji主题变成阅读干扰。

## 提炼与证据

Agent阅读内容后编写 `editorial.json`，格式见 [报告输入](references/report-input.md)。简报、观点、边界、应用建议和问答都引用已审阅的逐字稿或有观察记录的画面ID，区分 source_claim、visual_observation、agent_interpretation。不新增未经确认的人名、数字、平台保证、默认值、操作步骤或已上线承诺。规划/例子/竞争主张/演示数据不能改写成已证实事实。

提炼不是复制JSON，渲染不是新的语义审阅。需要新的画面或原声证据时回到理解阶段补充，不在交付阶段修改原稿、绕过partial或伪造证据。

## 生成报告

Python 3.10+，仅标准库；无需FFmpeg、Whisper、模型、Node、CDN或云端API。需要原交接包及其引用的本地媒体/关键帧保持可读，以完成哈希核验。

```bash
python3 scripts/ticket.py '/path/understanding/final/manifest.json' \
  --editorial '/path/editorial.json' --output '/path/new-report-directory'
```

输出目录须独立且为空，保留旧报告。脚本核验上游材料、最终内容、原媒体、关键帧及可用的来源清单哈希；拒绝不认识或未审阅的引用。默认交付单HTML，内含文字、转写和有观察记录的关键帧，另出Markdown、JSON与报告清单。无外部字体/脚本请求，不自动附带数百MB原视频。

依据按钮回查文字/画面，时间标签对应原视频；第一版不提供播放器或原网页的精确seek，不承诺原网页登录分享可用。Markdown保留内容、时间与证据ID，画面互动在HTML内。需要分享时提醒报告含原视频内容，按用户范围交付；生成本地文件不等于发布到外部。

## 验收与交付

渲染清单仅为rendered、visual_qa=not_performed。使用宿主浏览器或允许的预览工具实际查看HTML，检查桌面/窄屏排版、章节搜索、转写搜索、依据窗口和打印逻辑。没有浏览器工具时检查能做的项目并注明尚未视觉验收，不把生成成功当页面已检查。

交付HTML链接，简述内容范围和状态。把视觉/交互检查另存 `qa.md`，不篡改输入包或报告哈希；报告的内容状态跟随输入。私有视频、逐字稿、画面和账户信息不进入公开技能ZIP。
