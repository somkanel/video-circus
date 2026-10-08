#!/usr/bin/env python3
"""Acquire media and emit a versioned, verified handoff. Python stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

MEDIA_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.flv', '.ts',
              '.mp3', '.m4a', '.wav', '.ogg', '.flac', '.opus', '.m3u8', '.mpd'}
SUB_EXTS = {'.vtt', '.srt', '.ass', '.ttml', '.srv1', '.srv2', '.srv3', '.json3'}
SCHEMA = 'video-fetch/1'


class ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url)[:2] != urllib.parse.urlsplit(newurl)[:2]:
            safe = {'user-agent', 'accept', 'range', 'if-range'}
            for name in list(redirected.headers):
                if name.lower() not in safe:
                    redirected.remove_header(name)
        return redirected


def open_url(request, timeout):
    return urllib.request.build_opener(ScopedRedirect()).open(request, timeout=timeout)


class FetchError(Exception):
    def __init__(self, status, message, candidates=None):
        self.status, self.message = status, message
        self.candidates = candidates
        super().__init__(message)


def web_url(value):
    p = urllib.parse.urlsplit(value)
    return p.scheme in ('http', 'https') and bool(p.hostname)


def public_url(value):
    """Do not export signed query strings, userinfo or URL fragments."""
    p = urllib.parse.urlsplit(value)
    host = p.hostname or ''
    if ':' in host:
        host = '[' + host + ']'
    if p.port:
        host += ':' + str(p.port)
    return urllib.parse.urlunsplit((p.scheme, host, p.path, '', ''))


def digest_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def run(cmd, timeout=300):
    cmd = list(cmd)
    if cmd[0] == 'yt-dlp':
        cmd[0] = executable('yt-dlp') or 'yt-dlp'
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise FetchError('dependency_missing', f'Missing executable: {cmd[0]}')
    except subprocess.TimeoutExpired:
        raise FetchError('retryable', 'Operation timed out; rerun to resume this job.')


def executable(name):
    if name == 'yt-dlp':
        configured = os.environ.get('VIDEO_FETCH_YTDLP')
        if configured:
            return shutil.which(configured)
        managed = Path.home() / '.local/share/video-fetch/tools' / ('Scripts/yt-dlp.exe' if os.name == 'nt' else 'bin/yt-dlp')
        if managed.is_file() and os.access(managed, os.X_OK):
            return str(managed)
    return shutil.which(name)


def tool_json(cmd, timeout=90):
    result = run(cmd, timeout)
    if result.returncode:
        # Tool stderr may contain signed URLs or credentials. Classify without exporting it.
        err = result.stderr.lower()
        if any(s in err for s in ('drm', 'widevine', 'fairplay')):
            raise FetchError('unsupported_drm', 'Media is DRM-protected.')
        if any(s in err for s in ('sign in', 'login', 'cookies', 'captcha', '403', '401')):
            raise FetchError('access_required', 'Existing session or manual access verification may be needed.')
        raise FetchError('extractor_failed', 'Extractor could not resolve this source.')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise FetchError('extractor_failed', 'Extractor did not return valid metadata.')


def headers_from_file(path):
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or len(data) > 30:
        raise FetchError('invalid_input', 'Headers file must contain a JSON object with at most 30 entries.')
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9-]+', k) or '\r' in v or '\n' in v:
            raise FetchError('invalid_input', 'Invalid HTTP header.')
    return data


def ytdlp_args(args, headers):
    cmd = ['yt-dlp', '--no-playlist', '--no-warnings', '--socket-timeout', '30', '--retries', '3']
    if args.cookies_browser:
        cmd += ['--cookies-from-browser', args.cookies_browser]
    for k, v in headers.items():
        cmd += ['--add-headers', f'{k}:{v}']
    if args.referer and not any(k.lower() == 'referer' for k in headers):
        cmd += ['--referer', args.referer]
    return cmd


def extract_info(source, args, headers):
    data = tool_json(ytdlp_args(args, headers) + ['--dump-single-json', '--skip-download', '--', source])
    if data.get('_type') == 'multi_video' or (data.get('entries') and data.get('extractor') == 'generic'):
        # Generic extractors may list alternate encodings as separate videos.
        # Inspect actual players before asking the user to choose.
        raise FetchError('multi_video', 'Inspect webpage players to identify the intended video.')
    if data.get('_type') == 'playlist' or data.get('entries'):
        entries = [e for e in data.get('entries', []) if e]
        candidates = [{'url': e.get('webpage_url') or e.get('url'), 'kind': 'embed', 'label': e.get('title', 'Video'), 'page': source} for e in entries]
        candidates = [c for c in candidates if web_url(c['url'] or '')]
        raise FetchError('selection_required', 'Source is a playlist; pass an individual video or select from the private candidates file.', candidates)
    formats = data.get('formats') or []
    if data.get('is_live'):
        raise FetchError('live_requires_scope', 'Live input needs an explicit recording interval; use a completed recording.')
    if data.get('has_drm') or (formats and all(f.get('has_drm') for f in formats)):
        raise FetchError('unsupported_drm', 'Media is DRM-protected.')
    return data


class EmbeddedMedia(HTMLParser):
    def __init__(self):
        super().__init__()
        self.media, self.frames = [], []
        self.in_player, self.player_has_source = False, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('video', 'audio'):
            self.in_player, self.player_has_source = True, bool(a.get('src'))
            if a.get('src'):
                self.media.append(a['src'])
        if tag == 'source' and a.get('src') and (not self.in_player or not self.player_has_source):
            self.media.append(a['src'])
            self.player_has_source = True
        if tag == 'iframe' and a.get('src'):
            self.frames.append(a['src'])
        if tag == 'meta' and a.get('property', '').lower() in ('og:video', 'og:video:url', 'og:video:secure_url') and a.get('content'):
            self.media.append(a['content'])

    def handle_endtag(self, tag):
        if tag in ('video', 'audio'):
            self.in_player, self.player_has_source = False, False


def read_page(url, headers):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', **headers})
    with open_url(req, timeout=25) as r:
        kind = r.headers.get_content_type()
        if kind.startswith(('video/', 'audio/')) or kind in ('application/vnd.apple.mpegurl', 'application/x-mpegurl', 'application/dash+xml'):
            return None, r.url
        if kind not in ('text/html', 'application/xhtml+xml'):
            return '', r.url
        raw = r.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise FetchError('browser_required', 'Page exceeds static discovery limit; inspect it with the browser.')
        return raw.decode(r.headers.get_content_charset() or 'utf-8', errors='replace'), r.url


def http_file(source, folder, timeout, headers):
    """Resume an ordinary file when its server provides an entity validator."""
    suffix = Path(urllib.parse.urlsplit(source).path).suffix.lower()
    final = folder / ('media' + (suffix if suffix in MEDIA_EXTS else '.mp4'))
    partial, state_file = folder / 'http.download.part', folder / 'http-state.private.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    offset = partial.stat().st_size if partial.exists() else 0
    validator = state.get('etag') or state.get('last_modified')
    request_headers = {'User-Agent': 'Mozilla/5.0', **headers}
    if offset and validator:
        request_headers.update({'Range': f'bytes={offset}-', 'If-Range': validator})
    else:
        offset = 0
    started = time.monotonic()
    try:
        with open_url(urllib.request.Request(source, headers=request_headers), timeout=min(30, timeout)) as response:
            append = offset > 0 and response.status == 206
            if append and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                raise FetchError('download_failed', 'Server returned an unexpected resume range.')
            if not append:
                offset = 0
            kind = response.headers.get_content_type()
            if kind in ('text/html', 'application/xhtml+xml'):
                raise FetchError('download_failed', 'Server returned a webpage instead of a media file.')
            length = response.headers.get('Content-Length')
            total = offset + int(length) if length and length.isdigit() else None
            write_json(state_file, {'etag': response.headers.get('ETag'), 'last_modified': response.headers.get('Last-Modified'), 'total': total})
            with open(partial, 'ab' if append else 'wb') as out:
                while True:
                    if time.monotonic() - started > timeout:
                        raise FetchError('retryable', 'File transfer timed out; partial bytes are retained.')
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if total is not None and partial.stat().st_size != total:
                raise FetchError('retryable', 'Transfer is incomplete; partial bytes are retained.')
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise FetchError('download_failed', 'HTTP file transfer failed; partial bytes are retained.') from error
    partial.replace(final)
    return final


def discover(source, headers, max_depth=3):
    """Bounded static iframe traversal. No scripts executed or browser state read."""
    queue, visited, candidates = [(source, 0)], set(), []
    while queue and len(visited) < 12:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            same_origin = urllib.parse.urlsplit(url)[:2] == urllib.parse.urlsplit(source)[:2]
            body, final_url = read_page(url, headers if same_origin else {})
        except (OSError, ValueError, FetchError):
            continue
        if body is None:
            candidates.append({'url': final_url, 'kind': 'media', 'page': url})
            continue
        p = EmbeddedMedia()
        p.feed(body)
        for value in p.media:
            resolved = urllib.parse.urljoin(final_url, value)
            if web_url(resolved):
                candidates.append({'url': resolved, 'kind': 'media', 'page': final_url})
        for value in p.frames:
            resolved = urllib.parse.urljoin(final_url, value)
            if not web_url(resolved):
                continue
            host = urllib.parse.urlsplit(resolved).hostname or ''
            platform = any(host == h or host.endswith('.' + h) for h in ('youtube.com', 'youtube-nocookie.com', 'vimeo.com', 'bilibili.com', 'dailymotion.com'))
            if platform:
                candidates.append({'url': resolved, 'kind': 'embed', 'page': final_url})
            elif depth < max_depth:
                queue.append((resolved, depth + 1))
    unique = {}
    for c in candidates:
        unique.setdefault(c['url'], c)
    return list(unique.values())


def verify(path, quick=False, expected_duration=None, require_video=True, require_audio=False):
    try:
        probe = tool_json(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], 90)
    except FetchError as error:
        if error.status == 'dependency_missing':
            raise
        raise FetchError('validation_failed', 'File is not readable media.') from error
    streams = probe.get('streams', [])
    video = [s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    duration = float(probe.get('format', {}).get('duration') or 0)
    if not path.is_file() or not path.stat().st_size or duration <= 0 or (require_video and not video) or (require_audio and not audio):
        raise FetchError('validation_failed', 'File has no usable required media track or duration.')
    if not quick:
        r = run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:v?', '-map', '0:a?', '-f', 'null', '-'], max(300, duration * 2))
        if r.returncode:
            raise FetchError('validation_failed', 'Full media decode failed; file is not verified.')
    match = None
    if expected_duration:
        match = abs(duration - float(expected_duration)) <= max(3, float(expected_duration) * .01)
    return {
        'duration_seconds': round(duration, 3), 'bytes': path.stat().st_size,
        'container': probe.get('format', {}).get('format_name'),
        'video': [{k: s.get(k) for k in ('codec_name', 'width', 'height', 'avg_frame_rate')} for s in video],
        'audio': [{k: s.get(k) for k in ('codec_name', 'sample_rate', 'channels')} for s in audio],
        'decode_check': 'probe_only' if quick else 'full', 'duration_matches_source': match,
        'sha256': digest_file(path),
    }


def public_metadata(info):
    data = {k: info.get(k) for k in ('id', 'title', 'uploader', 'duration', 'extractor', 'upload_date') if info.get(k) is not None}
    if info.get('chapters'):
        data['chapters'] = [{k: c.get(k) for k in ('start_time', 'end_time', 'title')} for c in info['chapters']]
    return data


@contextmanager
def job_lock(folder):
    lock = folder / '.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise FetchError('job_locked', 'This job is already running or was interrupted. Check its owner before removing .lock.')
    try:
        os.write(fd, f'{os.getpid()}\n'.encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def cached_result(manifest, args):
    if not manifest.exists() or args.force:
        return None
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('status') not in ('complete', 'partial', 'subtitles_only'):
        return None
    for item in data.get('files', []):
        p = Path(item['path'])
        if not p.is_file() or digest_file(p) != item.get('sha256'):
            return None
    if not data.get('files'):
        return None
    data['cached'] = True
    return data


def format_selection(quality):
    if quality == 'best':
        return 'bv*+ba/b'
    limit = quality.rstrip('p')
    return f'bv*[height<={limit}]+ba/b[height<={limit}]'


def subtitle_selection(info, requested):
    if requested != 'auto':
        return requested
    manual = set(info.get('subtitles', {})) - {'live_chat'}
    automatic = set(info.get('automatic_captions', {}))
    original = {x for x in automatic if x.endswith('-orig')}
    language = info.get('language')
    if language:
        original.add(language)
    # Keep all manual captions; avoid hundreds of machine-translated variants.
    return ','.join(sorted(manual | original)) if manual or original else 'zh.*,en.*,-live_chat'


def download_ytdlp(source, folder, args, headers):
    cmd = ytdlp_args(args, headers) + ['--continue', '--no-overwrites', '--restrict-filenames',
        '-o', str(folder / 'media.%(ext)s'),
        '--abort-on-unavailable-fragments']
    if args.mode == 'subtitles':
        main_download = None
    elif args.mode == 'audio':
        main_download = cmd + ['-f', 'ba/b', '-x', '--audio-format', args.audio_format]
    else:
        main_download = cmd + ['-f', format_selection(args.quality), '--merge-output-format', 'mkv']
    if main_download:
        r = run(main_download + ['--', source], args.timeout)
        if r.returncode:
            raise FetchError('download_failed', 'Media download failed. Existing partial files are retained for a retry.')
    subtitle_cmd = cmd + ['--skip-download', '--write-subs', '--write-auto-subs', '--sub-langs', getattr(args, 'subtitle_selector', args.langs), '--', source]
    try:
        r = run(subtitle_cmd, min(args.timeout, 180))
        if r.returncode:
            return 'Some subtitles could not be fetched; available media is retained. Retry selected subtitle languages or use ASR.'
    except FetchError as error:
        if args.mode == 'subtitles':
            raise
        return 'Subtitle request timed out; media acquisition is independent and retained.'
    return None


def download_direct(source, folder, args, headers):
    if args.mode == 'subtitles':
        raise FetchError('no_subtitles', 'Direct media does not expose sidecar subtitles. Supply a subtitle source separately.')
    suffix = Path(urllib.parse.urlsplit(source).path).suffix.lower()
    if args.mode == 'video' and suffix not in ('.m3u8', '.mpd'):
        h = dict(headers)
        if args.referer and not any(k.lower() == 'referer' for k in h):
            h['Referer'] = args.referer
        final = folder / ('media' + (suffix if suffix in MEDIA_EXTS else '.mp4'))
        if final.exists() and not args.force:
            return
        http_file(source, folder, args.timeout, h)
        return
    path = folder / ('media.' + args.audio_format if args.mode == 'audio' else 'media.mkv')
    if path.exists() and not args.force:
        return
    if path.exists():
        path.rename(folder / f'previous-{time.time_ns()}{path.suffix}')
    partial = folder / ('transfer.' + args.audio_format if args.mode == 'audio' else 'transfer.mkv')
    cmd = ['ffmpeg', '-nostdin', '-v', 'error', '-y']
    h = dict(headers)
    if args.referer and not any(k.lower() == 'referer' for k in h):
        h['Referer'] = args.referer
    if h:
        cmd += ['-headers', ''.join(f'{k}: {v}\r\n' for k, v in h.items())]
    cmd += ['-i', source]
    if args.mode == 'audio':
        cmd += ['-vn', '-map', '0:a:0']
    else:
        cmd += ['-map', '0:v?', '-map', '0:a?', '-c', 'copy']
    r = run(cmd + [str(partial)], args.timeout)
    if r.returncode:
        raise FetchError('download_failed', 'Direct media transfer failed; refresh the source or its session headers.')
    partial.replace(path)


def candidates_output(candidates, folder):
    # Actual URLs are private local handoff data, never printed to chat or put in reports.
    write_json(folder / 'candidates.private.json', candidates)
    return [{'index': i, 'kind': c.get('kind', 'media'), 'host': urllib.parse.urlsplit(c['url']).hostname,
             'label': c.get('label', f'candidate {i}')} for i, c in enumerate(candidates)]


def local_origin(path, media):
    """Host-observed provenance, bound to the downloaded bytes; never session headers."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    allowed = {'page_url', 'title', 'duration', 'acquisition_method', 'observed_by', 'media_sha256'}
    if not isinstance(data, dict) or set(data) != allowed:
        raise FetchError('invalid_input', 'Origin JSON requires page_url, title, duration, acquisition_method, observed_by and media_sha256 only.')
    if not isinstance(data['page_url'], str) or not web_url(data['page_url']) or any(c in data['page_url'] for c in '\r\n'):
        raise FetchError('invalid_input', 'Origin page must be an observed HTTP(S) page URL.')
    for key, limit in [('title', 500), ('observed_by', 128)]:
        if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit or any(ord(c) < 32 for c in data[key]):
            raise FetchError('invalid_input', 'Origin title and observer must be nonempty bounded text.')
    if data['acquisition_method'] not in ('browser_download', 'host_download', 'external_download'):
        raise FetchError('invalid_input', 'Invalid origin acquisition method.')
    duration = data['duration']
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise FetchError('invalid_input', 'Origin duration must be a finite positive observed duration.')
    if data['media_sha256'] != digest_file(media):
        raise FetchError('invalid_input', 'Origin record does not match these media bytes.')
    return {**data, 'page_url': public_url(data['page_url']), 'evidence_basis': 'host_observation'}


def acquire(args):
    if args.referer and (not web_url(args.referer) or '\n' in args.referer or '\r' in args.referer):
        raise FetchError('invalid_input', 'Referer must be an HTTP(S) URL without line breaks.')
    headers = headers_from_file(args.headers_file)
    local = not web_url(args.source)
    source_path = Path(args.source).expanduser().resolve() if local else None
    if local and not source_path.is_file():
        raise FetchError('invalid_input', 'Local media file does not exist.')
    origin_path = getattr(args, 'origin_file', None)
    if origin_path and not local:
        raise FetchError('invalid_input', 'Origin records apply only to locally downloaded media.')
    origin = local_origin(origin_path, source_path) if origin_path else None
    identity = str(source_path) if local else args.source
    options = [identity, args.mode, args.quality, args.langs, args.audio_format, args.quick,
               args.referer, args.candidate, str(args.candidates_file), sorted(headers.items())]
    if local:
        options += [source_path.stat().st_size, source_path.stat().st_mtime_ns]
    if origin:
        options.append(origin)
    if args.candidates_file:
        options += [digest_file(Path(args.candidates_file))]
    key = hashlib.sha256(json.dumps(options, ensure_ascii=False).encode()).hexdigest()[:24]
    folder = Path(args.output).expanduser().resolve() / key
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    manifest = folder / 'manifest.json'
    with job_lock(folder):
        cached = cached_result(manifest, args)
        if cached:
            return cached
        result = {'schema': SCHEMA, 'status': 'failed', 'cached': False, 'job_id': key,
                  'source': {'kind': 'local' if local else 'url',
                             'page_url': None if local else public_url(args.source),
                             'local_path': str(source_path) if local else None},
                  'manifest_path': str(manifest), 'metadata': {}, 'files': [], 'warnings': []}
        try:
            if local:
                if origin:
                    result['source']['page_url'] = origin['page_url']
                    result['source']['origin'] = origin
                    result['metadata'] = {'title': origin['title'], 'duration': origin['duration']}
                if args.mode in ('info', 'video'):
                    media = source_path
                elif args.mode == 'subtitles':
                    raise FetchError('no_subtitles', 'Use external sidecar subtitles; local subtitle extraction is not automatic.')
                else:
                    media = folder / ('media.' + args.audio_format)
                    r = run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source_path), '-vn', '-map', '0:a:0', str(media)], args.timeout)
                    if r.returncode:
                        raise FetchError('download_failed', 'Audio extraction failed.')
                info = {'duration': origin['duration']} if origin else {}
                result['method'] = 'local'
            else:
                host = urllib.parse.urlsplit(args.source).hostname or ''
                if host == 'weixin.qq.com' and urllib.parse.urlsplit(args.source).path.startswith('/sph/'):
                    raise FetchError('unsupported_platform', 'WeChat Channels is outside the supported scope; provide a local video.')
                source = args.source
                info = {}
                direct = Path(urllib.parse.urlsplit(source).path).suffix.lower() in MEDIA_EXTS
                if args.candidates_file:
                    candidates = json.loads(Path(args.candidates_file).read_text(encoding='utf-8'))
                    if not isinstance(candidates, list) or any(not isinstance(c, dict) or not web_url(c.get('url', '')) for c in candidates):
                        raise FetchError('invalid_input', 'Candidate file must be a list of HTTP(S) media/embed URLs.')
                    if len(candidates) != 1 and args.candidate is None:
                        result['candidates'] = candidates_output(candidates, folder)
                        raise FetchError('selection_required', 'Select the intended video with --candidate INDEX.')
                    idx = args.candidate if args.candidate is not None else 0
                    if not 0 <= idx < len(candidates):
                        raise FetchError('invalid_input', 'Candidate index is out of range.')
                    source = candidates[idx]['url']
                    direct = candidates[idx].get('kind', 'media') == 'media'
                    if not args.referer:
                        args.referer = candidates[idx].get('page') or args.source
                if not direct:
                    try:
                        info = extract_info(source, args, headers)
                    except FetchError as error:
                        if error.status in ('unsupported_drm', 'live_requires_scope', 'selection_required'):
                            raise
                        candidates = discover(source, headers)
                        result['candidates'] = candidates_output(candidates, folder)
                        if not candidates:
                            raise FetchError('browser_required', 'Static extraction found no playable media. Use browser discovery and pass --candidates-file.')
                        if len(candidates) > 1 and args.candidate is None:
                            raise FetchError('selection_required', 'Multiple media candidates found; select the intended video.')
                        idx = args.candidate if args.candidate is not None else 0
                        if not 0 <= idx < len(candidates):
                            raise FetchError('invalid_input', 'Candidate index is out of range.')
                        selected = candidates[idx]
                        source, direct = selected['url'], selected['kind'] == 'media'
                        if not args.referer:
                            args.referer = selected['page']
                        if not direct:
                            info = extract_info(source, args, headers)
                result['metadata'] = public_metadata(info)
                is_dash = Path(urllib.parse.urlsplit(source).path).suffix.lower() == '.mpd'
                if direct and (args.mode == 'info' or args.quality != 'best' or is_dash):
                    try:
                        info = extract_info(source, args, headers)
                        result['metadata'] = public_metadata(info)
                        direct = False
                    except FetchError as error:
                        if error.status in ('unsupported_drm', 'live_requires_scope'):
                            raise
                        if is_dash and error.status == 'dependency_missing':
                            raise
                        if args.quality != 'best':
                            result['warnings'].append('Quality cap could not be applied to this direct source; preserving the available original.')
                result['method'] = 'direct' if direct else 'yt-dlp'
                if args.mode == 'info' and info:
                    result['status'] = 'info_only'
                    write_json(manifest, result)
                    return result
                if args.mode == 'info':
                    raise FetchError('probe_requires_download', 'Direct remote media requires download to verify; use --mode video.')
                if args.force:
                    for p in folder.glob('media.*'):
                        p.rename(folder / f'previous-{time.time_ns()}-{p.name}')
                if direct:
                    download_direct(source, folder, args, headers)
                else:
                    args.subtitle_selector = subtitle_selection(info, args.langs)
                    subtitle_warning = download_ytdlp(source, folder, args, headers)
                    if subtitle_warning:
                        result['warnings'].append(subtitle_warning)
                media_files = [p for p in folder.glob('media.*') if p.suffix.lower() in MEDIA_EXTS and p.suffix.lower() not in ('.m3u8', '.mpd')]
                if args.mode != 'subtitles':
                    if len(media_files) != 1:
                        raise FetchError('validation_failed', 'Expected exactly one final media file; inspect this job before retrying.')
                    media = media_files[0]
            if args.mode != 'subtitles':
                source_has_audio = bool(info.get('acodec') and info['acodec'] != 'none') or any(f.get('acodec') and f['acodec'] != 'none' for f in info.get('formats', []))
                facts = verify(media, args.quick, info.get('duration'), args.mode in ('video', 'info'), source_has_audio or args.mode == 'audio')
                result['files'].append({'kind': 'audio' if args.mode == 'audio' else 'video', 'path': str(media), **facts})
                result['status'] = 'info_only' if args.mode == 'info' else ('partial' if args.quick or facts['duration_matches_source'] is False else 'complete')
                if facts['duration_matches_source'] is False:
                    result['warnings'].append('Downloaded duration differs from source metadata; inspect for preview or truncation.')
                if facts['duration_matches_source'] is None:
                    result['warnings'].append('No independent source duration; successful decode does not prove this is the full intended video.')
                if not facts['audio']:
                    result['warnings'].append('No audio track; downstream analysis must use visual evidence.')
            subtitles = [p for p in folder.glob('media.*') if p.suffix.lower() in SUB_EXTS]
            for p in subtitles:
                if p.stat().st_size:
                    result['files'].append({'kind': 'subtitle', 'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest_file(p)})
            if args.mode == 'subtitles':
                if not result['files']:
                    raise FetchError('no_subtitles', 'No matching platform subtitles. Use video acquisition followed by ASR.')
                result['status'] = 'subtitles_only'
            if args.quick:
                result['warnings'].append('Probe-only verification: do not describe this file as fully decoded.')
        except FetchError as error:
            result['status'], result['message'] = error.status, error.message
            if error.candidates is not None:
                result['candidates'] = candidates_output(error.candidates, folder)
                result['candidates_file'] = str(folder / 'candidates.private.json')
        write_json(manifest, result)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', nargs='?', help='Local file or HTTP(S) URL')
    p.add_argument('--output', default='./video-fetch-output')
    p.add_argument('--mode', choices=['video', 'audio', 'subtitles', 'info'], default='video')
    p.add_argument('--quality', choices=['best', '2160p', '1440p', '1080p', '720p', '480p'], default='best')
    p.add_argument('--audio-format', choices=['mp3', 'm4a', 'wav', 'opus'], default='mp3')
    p.add_argument('--langs', default='auto', help='Subtitle languages: auto preserves manual/original captions; all or yt-dlp patterns also accepted')
    p.add_argument('--cookies-browser', choices=['chrome', 'edge', 'firefox', 'safari'])
    p.add_argument('--headers-file', help='Private JSON HTTP headers; never stored in public output')
    p.add_argument('--referer')
    p.add_argument('--candidates-file', help='Private browser-discovered media/embed candidates JSON')
    p.add_argument('--origin-file', help='Host-observed provenance JSON for an already downloaded local media file')
    p.add_argument('--candidate', type=int)
    p.add_argument('--timeout', type=int, default=3600)
    p.add_argument('--quick', action='store_true', help='Only probe; explicitly partial verification')
    p.add_argument('--force', action='store_true', help='Reacquire; preserve previous files')
    p.add_argument('--doctor', action='store_true')
    args = p.parse_args()
    try:
        if args.doctor:
            tool_details = {}
            for t in ('yt-dlp', 'ffmpeg', 'ffprobe'):
                path = executable(t)
                version = None
                if path:
                    r = run([path, '--version' if t == 'yt-dlp' else '-version'], 15)
                    version = (r.stdout.splitlines() or ['unknown'])[0]
                tool_details[t] = {'available': bool(path), 'path': path, 'version': version}
            result = {'python': sys.version.split()[0], 'tools': tool_details}
        elif not args.source:
            p.error('source is required unless --doctor is used')
        else:
            result = acquire(args)
    except FetchError as error:
        result = {'schema': SCHEMA, 'status': error.status, 'message': error.message}
    except (OSError, ValueError, KeyError, TypeError):
        result = {'schema': SCHEMA, 'status': 'invalid_input', 'message': 'Invalid input or unavailable local storage; check paths and JSON files.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.doctor or result.get('status') in ('complete', 'partial', 'subtitles_only', 'info_only') else 2


if __name__ == '__main__':
    sys.exit(main())
