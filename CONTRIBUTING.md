# Contributing / 参与贡献

## 中文

欢迎通过 Issue 反馈问题、提出建议，或提交 Pull Request。问题反馈请说明技能、Harness、系统、工具版本、复现步骤及预期结果；公开示例请用可分享的短片或合成素材。

Python 代码仅使用标准库。开发环境需要 Python 3.10+、FFmpeg / ffprobe 和 yt-dlp（用于 DASH 测试）：

```bash
python3 -m unittest discover -s tests -v
```

测试使用合成媒体、临时目录和模拟提取器，不需要账户、Whisper 模型或付费 API。测试通过不代表所有平台和 ASR 准确率均已验证。

修改技能时，请同步相关引用文件、测试及中英文 README。不要提交真实视频、逐字稿、私人报告、模型、cookies 或带签名的媒体地址。发布步骤见 [releasing.md](docs/releasing.md)。

## English

Use Issues for bugs and ideas, or open a Pull Request. Include the skill, Harness, operating system, tool versions, reproduction steps, and expected result. Use shareable short clips or synthetic media for public examples.

Python code uses only the standard library. Development requires Python 3.10+, FFmpeg / ffprobe, and yt-dlp (for DASH tests):

```bash
python3 -m unittest discover -s tests -v
```

Tests use synthetic media, temporary directories, and mocked extractors. They require no accounts, Whisper models, or paid APIs. Passing tests do not prove coverage of every platform or ASR accuracy.

When changing a skill, update its references, tests, and both READMEs as needed. Do not commit real videos, transcripts, private reports, models, cookies, or signed media URLs. See [releasing.md](docs/releasing.md) for release steps.
