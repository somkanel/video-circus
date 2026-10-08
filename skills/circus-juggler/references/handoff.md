# circus-juggler/1 内容包与审阅契约

任务目录包含原始轨/ASR JSON (`raw/`)、所有标准化字幕轨、主逐字稿、抽帧及未审阅帧索引、覆盖记录和材料 manifest。媒体默认引用本地原件，迁移时要复制原件并更新引用。

材料 manifest 的 status 为 materials_ready；`final/manifest.json` 为最终审阅状态。将最终路径交给下游。读取时先确认 status，不能消费 stale 的旧审阅。

## Evidence IDs

- `s000001` 等：主逐字稿段，start/end 为原视频秒数，source 指向字幕轨或原 ASR 块。
- `t2s000001` 等：备用字幕轨 track2 中的标准化段，可核对 ASR 误识别。
- `f0000450000` 等：450 秒请求抽帧，帧索引记录实际文件路径及哈希。音视频末尾不一致时最多回退 0.25 秒及 1 秒；time 和 ID 使用实际请求的回退时间，requested_for 记录原请求。

先实际读逐字稿和图片，再把 ID 写入 reviewed 列表。ID 是可回查索引，不自动证明观察结论正确。

## review.json

以下是格式示例，内容必须根据实际材料填写，不能原样复制：

```json
{
  "schema": "circus-juggler/1",
  "summary": "视频介绍产品的使用方式。",
  "reviewed_segment_ids": ["s000001"],
  "reviewed_frame_ids": ["f0000000000"],
  "reviewed_subtitle_ids": [],
  "verified_subtitle_tracks": [],
  "subtitle_selection_verified": true,
  "quiet_intervals_checked": true,
  "resolved_anomalies": [],
  "audio_checks": [],
  "chapters": [{"start": 0, "end": 10, "title": "产品介绍"}],
  "observations": [{"frame_id": "f0000000000", "text": "界面产品标题为 Solvea。"}],
  "corrections": [{
    "segment_id": "s000001",
    "original": "这是 Sobia",
    "corrected": "这是 Solvea",
    "basis": "visual",
    "evidence_ids": ["f0000000000"],
    "reason": "屏幕上能清楚读到产品名。",
    "certainty": "confirmed"
  }],
  "content": [{
    "start": 0, "end": 10,
    "kind": "source_claim",
    "text": "讲师介绍了 Solvea 产品。",
    "evidence_ids": ["s000001", "f0000000000"]
  }],
  "unresolved": []
}
```

`content.kind`：
- source_claim：讲话者的主张，未自动核实为外部事实。
- visual_observation：实际画面观察。
- agent_interpretation：Agent 的推断，不能伪装成讲话者原话。

备用字幕引用需写入 reviewed_subtitle_ids；verified_subtitle_tracks 只列实际核对语言和来源质量的轨 ID。主字幕读过并不等于所有备用轨读过。

`corrections.basis`：
- visual：引用的帧必须已读且有对应 observation。
- audio：audio_checks 必须覆盖该段，包含 `{start,end,observation}`；只在实际复听后声明。
- subtitle：引用已读且已核对质量的备用字幕轨，时间需要匹配目标段；记录平台字幕作为校正来源。
- cross_segment：至少引用另一条已读逐字稿段。适用于前后文明确给出的拼写或解释，不能仅凭猜测。

confirmed 替换正文，但保留原文和理由。uncertain 保留原始文字，并把替代识别和依据留在 correction 中；最终状态为 partial。

`resolved_anomalies` 为 transcript-original.json 中 anomalies 的数组索引；逐条检查后才填写。`subtitle_selection_verified` 需要核对实际语言/来源/质量。`quiet_intervals_checked` 需要实际复听 coverage 中低音量区间；同时 `audio_checks` 的时间范围须覆盖这些区间，并注明听到的内容。单独设置 true、复跑 ASR 或阅读采样图都不能解除静音复核缺口。

覆盖中 `asr_processed` 表示执行范围，不保证每秒有文字或文字准确。`asr_skipped_quiet` 表示 auto 实际跳过的低音量范围；`audio_not_transcribed` 包含所有没有所选字幕且未执行 ASR 的范围。旧的 `unprocessed_audio` 排除估计低音量，不可单独作为完整转写依据。`speech_on_estimated_quiet` 标记可能的低声讲话、幻觉或时间漂移，逐条检查再声明解决。

由获取包进入时，source.upstream_manifest 保留上游清单路径与SHA256，方便回查原网页和获取证据。媒体不变但上游清单变更也会拒绝复用，须新建材料包；不能篡改旧manifest来更换来源声明。

所有重要数字、术语、步骤都放入有 evidence_ids 的内容单元。章节覆盖整个已准备范围；大段概要不能代替内容单元的真实时间和引用。内容证据时间需与条目范围重叠或在 2 秒以内。

未解决项包含 start/end/reason，例如语音不清、图表无法读数或字幕丢段。时间都是原视频时间，不是分块音频的相对时间。

## 最终状态

finalize 校验已读 ID、引用、时间范围、校正原文和证据类型，保留原逐字稿，导出校正文本、视觉观察、content、coverage、review 和最终 manifest。

complete 只表示包内定义的整个输入范围经过 Agent 声明审阅、引用有效且没有记录的必需缺口；采样依然不能证明逐帧覆盖，代码也不能验证 Agent 是否真的读过或理解正确。

partial 的 remaining 指出缺口：未读段/帧、章节缺口、未处理音频、空 ASR 块、未解决疑点、未核实字幕选择/静音、未复查 ASR 异常、局部范围或上游 partial。它是有用交付，不是程序崩溃。

目前空 ASR 块会保守保持 partial；可通过实际复听和局部重跑形成证据、注明结论，但不要删改覆盖记录以强行 complete。

补帧之后旧 final manifest 标记 stale；需要重新审阅新增帧并 finalize。已准备材料和输入有 SHA256 校验，检测到修改则应新建任务包，不能把已校正文字写回 transcript-original.json。

## 隐私与分发

任务包包含视频/音频、原始讲话和本地路径，是工作产物；公开技能包仅包含独立脚本、指引和许可文件。清单不传递上游签名媒体 URL、Cookie 或私有请求头。长期存档或分享前单独选择需要的产物。
