<div align="center">
  <h1>🎪 Video Circus</h1>
  <p><b>Turn videos into readable reports with evidence you can check.</b></p>
  <p><a href="README.md">中文</a> · English</p>
  <p>
    <a href="https://github.com/somkanel/video-circus/releases/latest"><img src="https://img.shields.io/github/v/release/somkanel/video-circus" alt="Release"></a>
    <a href="https://github.com/somkanel/video-circus/actions/workflows/checks.yml"><img src="https://github.com/somkanel/video-circus/actions/workflows/checks.yml/badge.svg" alt="Checks"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  </p>
</div>

Video skills for **Codex, Claude Code, and other Agent Harnesses**: **import media → understand captions, audio, and visuals → deliver an HTML reading report**.

- Accept video links, web players, or local files, and acquire and verify media you are authorized to use.
- Use local Whisper when captions are missing; handle Chinese, English, and multilingual content.
- Keep timestamps and evidence references for chapters, key frames, and transcripts. List uncertainties separately.
- Run each stage independently or let the entry skill connect the full workflow.

## Why Circus?

Understanding a video becomes a circus act: 🎩 **Conjurer** brings the material out of the hat, 🤹 **Juggler** handles captions, sound, and pictures together, and 🎫 **Ticket** is the admission pass handed to the reader. 🎪 **Video Circus** connects the whole show, and progress messages use the same symbols to identify each stage.

## Install

[Download the latest release](https://github.com/somkanel/video-circus/releases/latest) · [Changelog](CHANGELOG.md)

Use the [Skills CLI](https://github.com/vercel-labs/skills). Node.js / npm and Git are required:

```bash
npx skills add somkanel/video-circus --skill '*' -a codex claude-code -g
```

This installs the entry skill and all three stage skills. For one Harness, keep only its name after `-a`. Omit `-g` to install into the current project. Start a new session after installation, then invoke the skill.

**Or paste this directly into Codex or Claude Code:**

```text
Install Video Circus from https://github.com/somkanel/video-circus.
Install video-circus, circus-conjurer, circus-juggler, and circus-ticket
in this Harness's user-level skill directory, preserving custom changes to existing skills.
Check Python, FFmpeg, yt-dlp, and the whisper.cpp CLI and multilingual model needed for local transcription.
Tell me which dependencies are missing. Do not automatically download a model or upload video.
```

<details>
<summary>Manual installation and other Harnesses</summary>

```bash
git clone https://github.com/somkanel/video-circus.git
```

Copy all four complete directories from `skills/` to the target location, including their scripts, templates, and reference files:

| Harness | User-level installation | Project-level installation |
| --- | --- | --- |
| [Codex](https://developers.openai.com/codex/skills/) | `~/.agents/skills/` | `.agents/skills/` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills/` | `.claude/skills/` |

For other Harnesses that support Agent Skills, use `npx skills add somkanel/video-circus -g` to select a target, or use the skill directory specified in their documentation. Browser discovery, image reading, and local command execution come from the Harness; coverage can differ between hosts.

</details>

## Use

**Codex**, invoke with `$`:

```text
$video-circus Understand this video and create a report with chapters, key frames, and evidence lookup: <URL or local file path>
```

**Claude Code**, invoke with `/`:

```text
/video-circus Understand this video and create a report with chapters, key frames, and evidence lookup: <URL or local file path>
```

Specify an audience, time range, or focus, such as "for new colleagues," "only 10:00 to 25:00," or "focus on operating steps and feature limitations." You can also provide an existing media package or reviewed content package to resume the workflow.

## Skills

| Skill | Use | Output |
| --- | --- | --- |
| [🎪 video-circus](skills/video-circus/SKILL.md) | Run the full workflow or resume from existing artifacts | Final report |
| [🎩 circus-conjurer](skills/circus-conjurer/SKILL.md) | Import and verify video, subtitles, and provenance | Media package |
| [🤹 circus-juggler](skills/circus-juggler/SKILL.md) | Transcribe speech, read captions, inspect visuals, and review uncertainties | Content with timestamps and evidence |
| [🎫 circus-ticket](skills/circus-ticket/SKILL.md) | Turn reviewed content into a reading report | HTML, Markdown, JSON |

For individual stages, use names such as `$circus-conjurer` in Codex or `/circus-conjurer` in Claude Code. The Agent runs the workflow and performs the reading and review. There is no standalone one-command CLI for the entry skill.

## Output

The default output is a self-contained `report.html`:

- **Brief and chapters**: read the main thread first, then expand details with collapse and search controls.
- **Key frames and evidence**: open the corresponding transcript or sampled frame, distinguishing speaker claims, visual observations, and Agent interpretation.
- **Searchable transcript**: retain timestamps, upstream evidence for corrections, and unresolved text.
- **Boundaries and review**: include key points, applications, questions, and uncertainties where useful.

The renderer also writes `report.md`, `report.json`, and a report manifest. HTML includes text and reviewed images, requires no CDN, and does not embed the original audio or video by default. Markdown keeps report text, times, and evidence IDs; the full transcript and image lookup are in HTML.

## Runtime dependencies

Installing the skills does not install tools or speech models.

| Dependency | Purpose |
| --- | --- |
| Python 3.10+ | Run all three stage scripts; standard library only |
| FFmpeg / ffprobe | Verify media, extract audio, and sample frames |
| yt-dlp | Resolve supported video links and retrieve media |
| whisper.cpp + multilingual Whisper GGML model | Local speech transcription when captions are missing or need checking |
| Harness browser tools, image reading, and vision capabilities | Discover dynamic players, understand visuals, and inspect reports |

For delivery alone, you need Python and the original content package; a browser is used for page inspection. Speech transcription tools can be omitted when using existing subtitles only.

<details>
<summary>macOS tools and model setup</summary>

```bash
brew install python ffmpeg yt-dlp whisper-cpp
```

Download a multilingual GGML model separately using the [whisper.cpp model instructions](https://github.com/ggml-org/whisper.cpp/tree/master/models). Avoid English-only `.en` models for Chinese videos. The tested model is `large-v3-turbo`, about 1.5 GB, with several additional GB of memory needed for inference.

Set `CIRCUS_WHISPER_MODEL` or pass `--model` to the script. By default, the script only checks for an existing `~/.cache/whisper/ggml-large-v3-turbo.bin`; it does not download one. Tool paths, track selection, and targeted rechecks are documented in [local ASR](skills/circus-juggler/references/asr.md).

</details>

## Coverage

Supports local videos, supported video links, and identifiable web players. Online media availability depends on the source, access permissions, and host browser capabilities. If retrieval is unavailable, you can import a local file instead. Only process media you are authorized to access and use. This project does not bypass DRM or access controls.

Local transcription and frame extraction do not upload video. Whether the Agent sends text or images to a cloud model depends on the Harness configuration. There is currently no native cloud-video API adapter.

Captions, speech recognition, and frame sampling can contain errors. Reports preserve limited scope and unresolved questions. There is no video player or timestamp seeking by default. A print button is available, but PDF export and pagination have not completed acceptance testing. Real runtime checks have mainly used macOS Apple Silicon; other systems and Harnesses need separate validation.

## Docs and license

[Contributing](CONTRIBUTING.md) · [Review and evidence format](skills/circus-juggler/references/handoff.md) · [Report input](skills/circus-ticket/references/report-input.md) · [Validation record](docs/validation.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

Code, skill instructions, and templates use [MIT](LICENSE). External tools and models are installed separately under their own licenses. The repository contains no model weights, third-party binaries, or real videos, transcripts, and reports.
