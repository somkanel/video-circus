# 🎪 Video Circus

English · [中文](README.md)

Give your Agent a video URL or a local file. It acquires the media, understands the content, and produces a report that people can read and check against the evidence.

Video Circus has three independent stage skills and one entry skill that connects them. It is useful for courses, product training, demonstrations, and interviews, especially long videos where speech and visuals need to be checked together.

## Three acts before the ticket

| Role | Skill | Responsibility | Output |
| --- | --- | --- | --- |
| 🎪 The whole circus | `video-circus` | Choose the starting point, connect stages, resume from existing artifacts | The full workflow and final report |
| 🎩 The magician | `circus-conjurer` | Acquire and verify media | Video or subtitles, provenance, media manifest |
| 🤹 The juggler | `circus-juggler` | Read captions, transcribe speech, inspect frames, review uncertainties | Content with timestamps and evidence references |
| 🎫 The admission ticket | `circus-ticket` | Distill the content, organize the reading experience, render the report | Self-contained HTML, Markdown, JSON |

The names started with a wish for each stage to be recognizable and a little playful. A squirrel, an ant, and a bee were considered for acquisition because they collect things. Once the suite became a circus, the choice was 🎩: a magician's hat that brings the video material into view. That became **Conjurer**.

**Juggler** fits the understanding stage because the Agent handles captions, sound, and pictures together, using each to complement or correct the others. A newspaper was considered for delivery, but **Ticket** felt closer to the idea: the circus is ready, and the reader has a ticket to enter. The report should offer that same experience, starting with the main thread and letting the reader explore the details.

The symbols also appear in the Agent's progress messages. 🎪 identifies the full workflow; 🎩, 🤹, and 🎫 identify the current stage.

## What you get

The default output is a self-contained HTML reading report with text and reviewed key frames in one file:

- A brief introduces the main thread. Timestamped chapters can be collapsed and searched.
- Key points, capability boundaries, applications, and review questions appear where useful.
- Evidence buttons open the relevant transcript or frame, distinguishing speaker claims, visual observations, and the Agent's interpretation.
- The corrected transcript is searchable. Unresolved questions and source notes remain visible.

The renderer also writes `report.md`, `report.json`, and `manifest.json`. Markdown contains the report text, times, and evidence IDs; the full transcript and image lookup are in HTML. The report uses no external fonts, CDN, or third-party frontend libraries. Original video and audio are not embedded by default.

## Quick start

After installing the entry skill and all three stage skills, ask your Agent:

```text
Use $video-circus to understand this video and create a readable, searchable HTML report with evidence references:
<video URL or local file path>
```

Add a reading goal if useful, such as "write for colleagues who are new to this product," "analyze only 10:00 to 25:00," or "focus on operating steps and limitations." The report follows your requested language; the transcript retains the source language.

The entry skill starts at the appropriate stage: acquisition for a URL or file, understanding for an existing media package, or delivery for a reviewed final content package. It continues between stages without repeatedly asking whether to proceed. If it needs a video selection, missing dependencies, or access permissions, it explains the specific obstacle and preserves existing artifacts.

Each stage can also be used independently:

```text
Use $circus-conjurer to download and verify this video: <URL>
Use $circus-juggler to analyze this local video: <file path>
Use $circus-ticket to turn this reviewed content package into a reading report: <final/manifest.json>
```

The host Agent runs the workflow. There is no standalone one-command CLI for the entry skill. Scripts acquire and transform material, verify handoffs, and render reports. The Agent performs the reading, visual understanding, evidence review, and editorial work.

## Installation

```bash
git clone https://github.com/somkanel/video-circus.git
cd video-circus
```

Copy these four directories from `skills/` into your host Agent's skill directory:

```text
video-circus/
circus-conjurer/
circus-juggler/
circus-ticket/
```

Codex defaults to `~/.codex/skills/`; other hosts use their own locations. If a skill with the same name already exists, compare versions and preserve your changes. Install only the relevant stage skill for standalone use. The full workflow requires the entry skill and all three stage skills.

**Skill files, runtime tools, and speech models are separate installations.** Copying a skill directory does not install dependencies or download a model.

### Runtime dependencies

| Dependency | 🎩 Acquisition | 🤹 Understanding | 🎫 Delivery |
| --- | --- | --- | --- |
| Python 3.10+ | Required | Required | Required |
| FFmpeg / ffprobe | For media acquisition and verification | For audio/video analysis | Not required |
| yt-dlp | For platform extraction and some streams | Not required | Not required |
| whisper.cpp `whisper-cli` | Not required | For local speech transcription | Not required |
| Multilingual Whisper GGML model | Not required | For local speech transcription | Not required |
| Host browser tools | For dynamic page discovery | Not required | For report inspection |
| Host image-reading tools and a vision model | Not required | For understanding visuals | Not required |

The Python scripts use only the standard library. The entry skill adds no runtime dependencies. Some restricted pages also require a host-specific read-only download tool and an existing authenticated session; those capabilities are not distributed with the skills.

On macOS with Homebrew installed:

```bash
brew install python ffmpeg yt-dlp whisper-cpp
python3 --version
python3 skills/circus-conjurer/scripts/fetch.py --doctor
python3 skills/circus-juggler/scripts/juggle.py doctor
```

Check the version of the Python executable you actually use. For delivery alone, Python 3.10+ runs the renderer; a browser is used to inspect the result.

### Speech model

Download a compatible multilingual GGML model separately using the [whisper.cpp model instructions](https://github.com/ggml-org/whisper.cpp/tree/master/models). Avoid English-only `.en` models for Chinese or multilingual videos.

The tested model is `large-v3-turbo`, about 1.5 GB. Inference needs several additional GB of memory; speed and memory use depend on the hardware, model, and video length. Point the script to your existing model:

```bash
python3 skills/circus-juggler/scripts/juggle.py doctor \
  --model '/path/ggml-large-v3-turbo.bin'
```

You can also set `CIRCUS_WHISPER_MODEL`. Without an explicit path, the script only checks for an existing `~/.cache/whisper/ggml-large-v3-turbo.bin`; it does not download one automatically.

For Linux and Windows, install the same CLIs through each tool's official instructions. Real runtime acceptance has so far been performed mainly on macOS Apple Silicon.

## Where the video comes from

| Input | Handling and limits |
| --- | --- |
| Local video | Probe, decode verification, and hashing; reference the original file by default |
| YouTube, Bilibili, and other platform links | Prefer yt-dlp for media and available subtitles; extractor versions and access conditions affect results |
| A regular page with `video`, `source`, or an iframe | Discover media statically, inspecting embedded pages when needed |
| Dynamic players, HLS / DASH, or `blob:` | When static extraction is insufficient, use host browser tools to inspect the actual player and acquire media through an available path; a `blob:` URL is not itself a downloadable file address |
| Video without CC captions | Extract audio, transcribe with local Whisper, and interpret it alongside visuals |
| Existing media or content packages | Verify provenance and sealed artifacts, then resume at the relevant stage |

The workflow handles multilingual material. Real acceptance covers Chinese, English, and English terminology within Chinese speech. Accuracy across all mixed-language combinations has not been established.

When browser or host-specific read-only tools obtain a local video, `--origin-file` can record the observed source, title, and duration, bound to the media hash. See [browser discovery](skills/circus-conjurer/references/browser-discovery.md). Missing platform transcripts do not prevent downloading and local analysis; generating cloud meeting notes is not a prerequisite.

## Running the scripts manually

Run these commands from the repository root. The Agent can handle the full workflow in normal use; these commands are useful for running individual stages or investigating a problem.

```bash
# Acquire and verify media
python3 skills/circus-conjurer/scripts/fetch.py 'https://example.com/lesson' \
  --output './acquired'

# Prepare subtitles, audio, and frames
python3 skills/circus-juggler/scripts/juggle.py prepare '/path/acquired/manifest.json' \
  --model '/path/ggml-large-v3-turbo.bin' --output './understanding'

# After the Agent reads the material and writes review.json, finalize the content package
python3 skills/circus-juggler/scripts/juggle.py finalize './understanding' \
  --review '/path/review.json'

# After the Agent writes editorial.json with evidence references, render the report
python3 skills/circus-ticket/scripts/ticket.py './understanding/final/manifest.json' \
  --editorial '/path/editorial.json' --output './report'
```

The acquisition script returns the actual job directory; use the paths in its artifacts. Rendering requires access to the original content package, media, and sealed materials. The report output directory must be separate and empty.

The default `--asr auto` transcribes subtitle gaps and skips estimated quiet intervals of at least 10 seconds. `--asr always` transcribes the full requested audio range, including quiet intervals. `--asr never` uses existing subtitles and visual material only. Low volume does not prove there is no speech, and forced transcription can hallucinate. Uncertainties need review and a retained record.

For track selection, timestamp offsets, targeted rechecks, additional frames, and environment variables, see [local ASR](skills/circus-juggler/references/asr.md) and the [review contract](skills/circus-juggler/references/handoff.md). The editorial schema is in [report input](skills/circus-ticket/references/report-input.md).

## What counts as finished

Each stage has its own completion criteria. A playable file, a generated transcript, and a reviewed understanding of the content are different outcomes.

- `materials_ready`: material preparation is finished; the Agent still needs to read and review it.
- Understanding `complete`: review and handoff checks cover the specified input scope, with sampling limits still applying.
- `partial`: upstream gaps, a limited scope, unreviewed material, or unresolved questions remain. The report carries these limits forward.
- `stale`: the material has changed and the previous review needs updating.
- Report `rendered`: files were generated successfully. Page inspection is recorded separately and does not change the upstream content status.

A frame becomes evidence only after it has been viewed and an observation recorded. Text corrections preserve the original and their supporting evidence. SHA256 checks protect materials and handoffs. Existing results are reused only after verification; changed inputs or parameters use a new directory.

## Current limits and privacy

Any page can be an acquisition starting point, but successful acquisition from every URL is not guaranteed. Dynamic discovery depends on the host's tools, and authenticated content requires existing access. The workflow does not bypass DRM or access controls. WeChat Channels is not a guaranteed platform.

Local speech transcription and frame extraction do not upload the video. Whether the Agent sends text or images to a cloud model depends on the host. There is currently no native cloud-video API adapter.

The HTML report has no original video player by default, and timestamp labels do not seek playback. A print button is available; PDF export and pagination have not yet completed acceptance testing. Speech recognition, subtitles, and sampled frames can contain errors, so the report is not a frame-by-frame or word-perfect record.

Real job packages may contain private media, speech, and page information. Select files deliberately before sharing. The public repository contains no video, audio, transcripts, real reports, account information, model weights, or third-party binaries.

## Verification and license

```bash
python3 -m unittest discover -s tests -v
```

All 70 tests passed before publication. They cover local HTTP media acquisition, subtitles and review, evidence references, hashes, and output isolation. Tests require FFmpeg / ffprobe and permission to bind a loopback HTTP server. Simulated tests do not establish compatibility with every platform. Real platform checks, an approximately 66-minute training video without platform captions, and known limitations are documented in the [validation record](docs/validation.md).

Code, skill instructions, and templates are independently implemented under [MIT](LICENSE). External tools and models are not distributed here. yt-dlp, FFmpeg, whisper.cpp, and individual model distributions retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).

When upgrading from an older version, `video-fetch` has been renamed to `circus-conjurer`. The `video-fetch/1` manifest and existing environment variables remain compatible. Before removing the old installation to avoid duplicate activation, check for your own changes in that directory.
