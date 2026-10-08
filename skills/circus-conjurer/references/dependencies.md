# External tools

This package contains independently implemented Python code and skill instructions.
It does not bundle external executables, model weights or third-party source code.

| Tool | Use | Upstream license |
| --- | --- | --- |
| yt-dlp | Extractor, download, subtitles | [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE); dependencies and bundled distributions may have other licenses |
| FFmpeg / ffprobe | Remux, audio extraction, probe and decode verification | [LGPL 2.1+ or GPL depending on build](https://ffmpeg.org/legal.html) |
| Host browser tool | Dynamic webpage discovery by the agent | Governed by the host's terms; not redistributed here |

Users install these tools separately. Calling installed CLI tools is distinct from
redistributing their binaries or linking their libraries. A future binary bundle
must separately audit its exact components, licenses and source-offer obligations.

No WeChat Channels-specific backend is included. Platform access and rights in
downloaded media are independent of the license of this skill package.
