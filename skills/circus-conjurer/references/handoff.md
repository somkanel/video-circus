# 媒体包交接契约 v1

清单 schema 为 `video-fetch/1`。每个任务目录按来源和选项的哈希区分；原始 URL 不作为文件名。清单原子写入，文件哈希用于检测缓存被篡改或替换。

| 字段 | 含义 |
| --- | --- |
| status | complete、partial、subtitles_only、info_only，或恢复/失败状态 |
| source | local/url、脱敏页面 URL 或本地路径 |
| source.origin | 可选宿主来源观察：原网页、标题、时长、下载方式、观察工具、绑定的media_sha256；evidence_basis为host_observation |
| method | local、yt-dlp、direct |
| metadata | 可得的 ID、标题、作者、时长、章节、提取器 |
| files | 绝对路径、类型、SHA-256、大小；媒体另含音视频参数和验证范围 |
| warnings | 无音轨、缺乏独立时长、时长不匹配或仅快速验证 |
| manifest_path | 下游读取的本地清单路径 |
| cached | 文件哈希匹配后是否复用已有结果 |

`complete` 描述该文件的技术验证结果。若没有独立来源时长，`duration_matches_source` 为 null，不能承诺全片完整。标题、画面和原页面的一致性由 Agent 核对；ASR/画面分析属于下一阶段。

专用工具或浏览器先下载文件时，`--origin-file` 将已观察来源记录绑定到本地媒体。method仍为local，source.origin.acquisition_method说明此前的取得方式；来源时长参与校验，不匹配保持partial。页面身份/时长是宿主观察声明，不是脚本自动证明。来源文件内容参与缓存身份，变更记录产生新任务，不改旧manifest。source.origin不包含签名媒体地址或会话头。

恢复状态包括 browser_required、selection_required、access_required、retryable、dependency_missing、job_locked、probe_requires_download。停止状态包括 unsupported_drm、unsupported_platform、live_requires_scope、invalid_input。download_failed / validation_failed 应按具体来源检查，不允许把未验证分片冒充成品。

原始字幕保留，不在获取阶段翻译、去重或校订。下游根据媒体时间轴检查字幕偏移、覆盖范围、原语言与自动识别质量。`metadata.chapters` 是平台章节，不能当作已经核实的内容总结。

本地输入默认引用原件，输出目录不一定包含视频本体。迁移媒体包时需要复制清单所引用的文件并更新路径。候选私有 JSON、会话头、签名 URL 不属于人类报告。
