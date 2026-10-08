# 本地 ASR 与时间轴

## 已支持后端

当前脚本适配 whisper.cpp 的 `whisper-cli` JSON 输出。本机已测 1.8.3，配合多语言 `large-v3-turbo` GGML 模型；不自动下载模型，也不把模型或后端打包。

`CIRCUS_WHISPER_CLI`、`CIRCUS_FFMPEG`、`CIRCUS_FFPROBE` 可指定工具路径。
`--model` 或 `CIRCUS_WHISPER_MODEL` 指定 GGML 模型；没有指定时仅查找已有的 `~/.cache/whisper/ggml-large-v3-turbo.bin`。

不使用仅英文 `.en` 模型处理中文。large-v3-turbo 偏重速度，不能承诺准确率；困难音频可用经过独立安装和核验的多语言 large-v3 模型重查。Windows/Linux 的 CLI 支持是接口层设计，未进行全平台运行验证。

如果 Metal/GPU 初始化失败，尝试一次 `--cpu`，并用新任务目录；不要无限重试。`doctor` 检测可执行程序和模型存在，不等于已经证明模型推理成功。

## 分块与字幕

字幕主轨按覆盖范围默认选取，不能据此认定质量或原始语言。脚本支持 SRT/VTT，以及 whisper.cpp `transcription` 和 `{segments:[{start,end,text}]}` JSON。ASS/TTML 等先通过 FFmpeg 转为 SRT，再明确主轨；原始文件仍保留。内嵌字幕需先单独提取，不会自动选择流。

auto 对主字幕之外的区间转写；always 对指定范围全部执行 ASR，包括估计低音量区间，保留字幕轨但以新 ASR 为主逐字稿。音频全范围先归一化为 16kHz 单声道，按容器起点处理音轨延迟，补齐结尾，再进行局部分块；所有输出时间都映射回原视频。

默认块长 300 秒，左右重叠 2 秒。用识别段中点归属主块，以减少重复；边界依然可能识别不一致，不能把去重当成已证实的文字。`-mc 0` 禁止跨块历史文本影响；自动识别每块主语言，多语言和块内中英切换仍需审阅。

低音量区间由 silencedetect（-40dB、持续 1 秒）估计；仅 auto 跳过持续至少 10 秒的区间，短停顿保留在块内以避免反复加载模型。`asr_skipped_quiet` 记录实际被 auto 排除的区间；`audio_not_transcribed` 记录无所选字幕且未执行 ASR 的范围，包括被跳过的区间。`unprocessed_audio` 延续旧契约，排除估计低音量后记录其余缺口，不能单独用它证明全程转写。没有音轨时这些音频缺口均为空。

疑点复查示例：

```bash
python3 scripts/juggle.py prepare '/path/video.mp4' \
  --range 3916:3942 --asr always --language zh --output './tail-recheck'
```

旧版本 always 也跳过长低音量，0.1.1 已修复。使用新任务目录；不修改原始材料来伪造覆盖。强制转写容易在静音上产生文字；如果 ASR 段至少1秒且80%以上落在估计低音量区间，标记 `speech_on_estimated_quiet` 待复核，保留原文和时间，不自动判定幻觉。它不等同于 VAD 或声学准确率。无异常标记也不代表文本正确。

ASR 原始 JSON、模型 SHA256、参数和逐块处理范围保留。空块、连续重复及低字符多样性文字作为复查线索。用户需要准确引用或行动步骤时，实际复听比再次 ASR 更有证据价值。

## 运行成本

模型可能占用数 GB 内存，长视频需要真实计算时间。使用实际 scope、模型和已完成块说明进度；不要许诺固定速度。根目录 audio-scope.wav 是局部范围的复听材料，不随公开技能打包。

本地转写与抽帧不上传；宿主 Agent 的图片/文字推理可能使用云端。不要称整套分析完全离线。
