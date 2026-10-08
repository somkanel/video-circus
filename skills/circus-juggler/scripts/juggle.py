#!/usr/bin/env python3
"""Local material preparation and evidence-checked Agent handoff (MIT)."""
import argparse
import contextlib
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SCHEMA = 'circus-juggler/1'


class JuggleError(Exception):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(cmd, timeout=3600):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        # Do not echo credentials or media-derived untrusted text in errors.
        raise JuggleError(f'{Path(str(cmd[0])).name} failed (exit {p.returncode}); check local dependencies and input.')
    return p.stdout, p.stderr


def tool(name):
    value = os.environ.get('CIRCUS_' + name.upper().replace('-', '_')) or shutil.which(name)
    if not value:
        raise JuggleError(f'Missing external tool: {name}')
    return value


def default_model():
    explicit = os.environ.get('CIRCUS_WHISPER_MODEL')
    if explicit:
        return Path(explicit).expanduser()
    p = Path.home() / '.cache/whisper/ggml-large-v3-turbo.bin'
    return p if p.is_file() else None


def number(value):
    if isinstance(value, bool):
        raise JuggleError('Expected a finite number.')
    v = float(value)
    if not math.isfinite(v):
        raise JuggleError('Expected a finite number.')
    return v


def union(intervals):
    out = []
    for a, b in sorted(intervals):
        if b <= a:
            continue
        if out and a <= out[-1][1] + 0.001:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(intervals, covered):
    result = []
    for a, b in union(intervals):
        cursor = a
        for c, d in union(covered):
            if d <= cursor or c >= b:
                continue
            if c > cursor:
                result.append([cursor, min(c, b)])
            cursor = max(cursor, d)
        if cursor < b:
            result.append([cursor, b])
    return result


def clock(value):
    pieces = value.strip().replace(',', '.').split(':')
    if len(pieces) not in (2, 3):
        raise JuggleError('Invalid subtitle timestamp.')
    return sum(number(p) * 60 ** i for i, p in enumerate(reversed(pieces)))


def parse_subtitle(path):
    path = Path(path)
    if path.suffix.lower() not in ('.srt', '.vtt', '.json'):
        raise JuggleError('Convert this subtitle format to SRT before preparation; supported: SRT/VTT/Whisper JSON.')
    text = path.read_text(encoding='utf-8-sig')
    rows = []
    if path.suffix.lower() == '.json':
        data = json.loads(text)
        if 'transcription' in data:
            for s in data['transcription']:
                offsets = s.get('offsets', {})
                rows.append({'start': number(offsets['from']) / 1000,
                             'end': number(offsets['to']) / 1000, 'text': s['text'].strip()})
        elif 'segments' in data:
            rows = [{'start': number(s['start']), 'end': number(s['end']), 'text': s['text'].strip()}
                    for s in data['segments']]
        else:
            raise JuggleError('Supported JSON: whisper.cpp transcription or timestamped segments.')
    else:
        for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
            lines = block.splitlines()
            for i, line in enumerate(lines):
                if '-->' not in line:
                    continue
                a, b = line.split('-->', 1)
                body = '\n'.join(lines[i + 1:])
                body = html.unescape(re.sub(r'<[^>]*>', '', body)).strip()
                if body:
                    rows.append({'start': clock(a), 'end': clock(b.strip().split()[0]), 'text': body})
                break
    rows.sort(key=lambda s: (s['start'], s['end']))
    if any(s['end'] <= s['start'] or s['start'] < 0 for s in rows):
        raise JuggleError('Subtitle contains an invalid time range.')
    # YouTube rolling cues overlap and repeat text; retain raw input separately.
    out = []
    for s in rows:
        s = dict(s)
        if out and s['start'] < out[-1]['end'] + 0.05:
            previous = out[-1]
            if s['text'] == previous['text']:
                previous['end'] = max(previous['end'], s['end'])
                continue
            for length in range(min(len(previous['text']), len(s['text'])), 3, -1):
                if previous['text'][-length:] == s['text'][:length]:
                    s['text'] = s['text'][length:].strip()
                    break
        if s['text']:
            out.append(s)
    return out


def chunks(start, end, size, overlap):
    cursor = start
    while cursor < end - 0.001:
        stop = min(end, cursor + size)
        yield {'start': max(start, cursor - overlap), 'end': min(end, stop + overlap),
               'core_start': cursor, 'core_end': stop}
        cursor = stop


def map_asr(raw, chunk, scope, language):
    result = []
    for s in raw.get('transcription', []):
        a = chunk['start'] + number(s['offsets']['from']) / 1000
        b = chunk['start'] + number(s['offsets']['to']) / 1000
        midpoint = (a + b) / 2
        if not chunk['core_start'] <= midpoint < chunk['core_end']:
            continue
        a, b = max(scope[0], a), min(scope[1], b)
        text = s['text'].strip()
        if text and b > a:
            result.append({'start': a, 'end': b, 'text': text,
                           'language': raw.get('result', {}).get('language', language)})
    return result


@contextlib.contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    lock = folder / '.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise JuggleError('Job locked. Check the PID in .lock before recovering an interrupted job.')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def probe(media):
    stdout, _ = run([tool('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', media])
    data = json.loads(stdout)
    duration = number(data.get('format', {}).get('duration', 0))
    if duration <= 0:
        raise JuggleError('Finite positive media duration required.')
    return {'duration': duration, 'container_start': number(data['format'].get('start_time', 0)),
            'audio': any(s.get('codec_type') == 'audio' for s in data['streams']),
            'video': any(s.get('codec_type') == 'video' for s in data['streams']),
            'streams': [{'type': s.get('codec_type'), 'start': s.get('start_time'),
                         'codec': s.get('codec_name')} for s in data['streams']]}


def source_input(path, subtitle_paths):
    path = Path(path).expanduser().resolve()
    upstream = None
    subtitles = list(subtitle_paths)
    if path.suffix.lower() in ('.srt', '.vtt'):
        subtitles.append(str(path))
        return None, list(dict.fromkeys(str(Path(p).expanduser().resolve()) for p in subtitles)), None
    if path.suffix.lower() == '.json':
        upstream = read(path)
        if upstream.get('schema') != 'video-fetch/1':
            raise JuggleError('Expected a video-fetch/1 manifest or a local media file.')
        if upstream.get('status') not in ('complete', 'partial', 'subtitles_only'):
            raise JuggleError('Upstream media is not ready for analysis.')
        files = upstream.get('files', [])
        for f in files:
            p = Path(f['path'])
            if not p.is_file() or not f.get('sha256') or digest(p) != f['sha256']:
                raise JuggleError('Upstream file missing or hash mismatch; reacquire it.')
        media = [Path(f['path']) for f in files if f['kind'] in ('video', 'audio')]
        if len(media) > 1:
            raise JuggleError('Select one local media file from the upstream manifest.')
        subtitles += [f['path'] for f in files if f['kind'] == 'subtitle']
        path = media[0] if media else None
    if path is not None and not path.is_file():
        raise JuggleError('Local media does not exist; acquire URLs with circus-conjurer first.')
    subtitles = list(dict.fromkeys(str(Path(p).expanduser().resolve()) for p in subtitles))
    return path, subtitles, upstream


def frame_times(a, b, interval):
    # Include the beginning and near the end, even for a clip shorter than interval.
    times = [a + i * interval for i in range(int((b - a) / interval) + 1) if a + i * interval < b]
    times.append(max(a, b - min(0.1, (b - a) / 2)))
    return sorted(set(round(t, 3) for t in times))


def extract_frames(folder, media, times, width, index=None):
    index = index or []
    existing = {round(f['time'], 3): f for f in index}
    floor = min(times)
    for t in times:
        if t in existing and Path(existing[t]['path']).is_file() and digest(existing[t]['path']) == existing[t]['sha256']:
            continue
        # A/V durations and final frame PTS can differ. Bounded backoff keeps the
        # actual requested seek in the index rather than mislabelling a prior image.
        found = False
        for actual in dict.fromkeys([t, round(max(floor, t - 0.25), 3), round(max(floor, t - 1), 3)]):
            fid = f'f{int(round(actual * 1000)):010d}'
            target = folder / 'frames' / (fid + '.jpg')
            target.parent.mkdir(exist_ok=True)
            if actual in existing and target.is_file() and digest(target) == existing[actual]['sha256']:
                existing[actual].setdefault('requested_for', []).append(t)
                found = True
                break
            try:
                run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                     '-ss', actual, '-i', media, '-map', '0:v:0', '-frames:v', '1',
                     '-vf', f'scale=min({width}\\,iw):-2,format=yuvj420p', '-q:v', '3', target])
            except JuggleError:
                continue
            if not target.is_file() or target.stat().st_size == 0:
                continue
            existing[actual] = {'id': fid, 'time': actual, 'path': str(target), 'sha256': digest(target),
                               'requested_for': [t], 'time_basis': 'requested_seek_seconds_from_container_start', 'reviewed': False}
            found = True
            break
        if not found:
            raise JuggleError('Frame extraction returned no image.')
    return sorted(existing.values(), key=lambda f: f['time'])


def silence_intervals(wav, scope_start, scope_end):
    _, stderr = run([tool('ffmpeg'), '-hide_banner', '-nostdin', '-i', wav, '-af',
                     'silencedetect=noise=-40dB:d=1', '-f', 'null', '-'])
    out, active = [], None
    for key, val in re.findall(r'silence_(start|end):\s*([\d.]+)', stderr):
        t = min(scope_end, scope_start + float(val))
        if key == 'start':
            active = t
        elif active is not None:
            out.append([active, t])
            active = None
    if active is not None:
        out.append([active, scope_end])
    return union(out)


def anomalies(segments, quiet_intervals=()):
    out = []
    for i, s in enumerate(segments):
        quiet_overlap = sum(max(0, min(s['end'], b) - max(s['start'], a))
                            for a, b in union(quiet_intervals))
        if s['source'].startswith('asr-') and quiet_overlap >= 1 and quiet_overlap / (s['end'] - s['start']) >= .8:
            out.append({'kind': 'speech_on_estimated_quiet', 'segment_ids': [s['id']],
                        'start': s['start'], 'end': s['end']})
        if i and s['source'].startswith('asr-') and segments[i - 1]['source'].startswith('asr-') and s['source'] != segments[i - 1]['source'] and s['start'] < segments[i - 1]['end']:
            out.append({'kind': 'overlapping_chunk_timestamps', 'segment_ids': [segments[i - 1]['id'], s['id']],
                        'start': s['start'], 'end': segments[i - 1]['end']})
        if len(s['text']) > 30 and len(set(s['text'])) < 8:
            out.append({'kind': 'low_diversity_text', 'segment_ids': [s['id']], 'start': s['start'], 'end': s['end']})
        if i >= 2 and s['text'] == segments[i - 1]['text'] == segments[i - 2]['text']:
            out.append({'kind': 'repeated_text', 'segment_ids': [r['id'] for r in segments[i - 2:i + 1]],
                        'start': segments[i - 2]['start'], 'end': s['end']})
    return out


def artifact_hashes(folder):
    # Seal prepared artifacts; raw audio/chunk files are included to make resume verifiable.
    return {str(p.relative_to(folder)): digest(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.name not in ('.lock', 'manifest.json', 'review.json')
            and not any(x in {'final'} for x in p.relative_to(folder).parts)}


def check_materials(folder, manifest):
    media = manifest['source'].get('media')
    if media and (not Path(media).is_file() or digest(media) != manifest['source']['sha256']):
        raise JuggleError('Source media changed; prepare a new package.')
    upstream = manifest['source'].get('upstream_manifest')
    if upstream and (not Path(upstream['path']).is_file() or digest(upstream['path']) != upstream['sha256']):
        raise JuggleError('Upstream source evidence changed; prepare a new package.')
    for rel, sha in manifest['artifacts'].items():
        p = (folder / rel).resolve()
        if not p.is_relative_to(folder.resolve()) or not p.is_file() or digest(p) != sha:
            raise JuggleError('Prepared artifact changed or is missing; regenerate materials.')


def prepare(args):
    media, subtitles, upstream = source_input(args.source, args.subtitle)
    info = probe(media) if media else None
    tracks = []
    for i, p in enumerate(subtitles):
        rows = parse_subtitle(p)
        for n, s in enumerate(rows):
            s['start'] += args.subtitle_offset
            s['end'] += args.subtitle_offset
            s['id'] = f't{i + 1}s{n + 1:06d}'
        tracks.append({'id': f'track{i + 1}', 'path': p, 'sha256': digest(p), 'segments': rows})
    duration = info['duration'] if info else max((s['end'] for t in tracks for s in t['segments']), default=0)
    if duration <= 0:
        raise JuggleError('No media or nonempty timestamped subtitles.')
    start, end = (0, duration) if not args.range else [number(t) for t in args.range.split(':')]
    if start < 0 or not start < end <= duration + 0.05:
        raise JuggleError('Scope must be inside the video duration.')
    end = min(end, duration)
    if args.track:
        selected = next((t for t in tracks if t['id'] == args.track), None)
        if not selected:
            raise JuggleError('Unknown subtitle track; use track1, track2, etc. in supplied order.')
    else:
        selected = max(tracks, key=lambda t: sum(b - a for a, b in union(
            [[max(start, s['start']), min(end, s['end'])] for s in t['segments']])), default=None)
    source = {'media': str(media) if media else None, 'sha256': digest(media) if media else None,
              'upstream_status': upstream.get('status') if upstream else 'local_unverified',
              'duration': duration, 'scope': [start, end], 'probe': info}
    if upstream:
        upstream_path = Path(args.source).expanduser().resolve()
        source['upstream_manifest'] = {'path': str(upstream_path), 'sha256': digest(upstream_path)}
    config = {'source': source, 'subtitles': [{k: t[k] for k in ('id', 'path', 'sha256')} for t in tracks],
              'asr': args.asr, 'language': args.language, 'subtitle_offset': args.subtitle_offset,
              'track': selected['id'] if selected else None, 'frame_interval': args.frame_interval,
              'frame_width': args.frame_width, 'chunk_seconds': args.chunk_seconds, 'overlap': args.overlap,
              'model': str(Path(args.model).expanduser().resolve()) if args.model else None,
              'cpu': args.cpu, 'pipeline_sha256': digest(__file__)}
    folder = Path(args.output).expanduser().resolve()
    if media and media.is_relative_to(folder):
        raise JuggleError('Output must not contain the input media.')
    with locked(folder):
        prior = folder / 'config.json'
        if prior.exists() and read(prior) != config:
            raise JuggleError('Output belongs to different inputs/options; choose a new output directory.')
        if (folder / 'manifest.json').exists():
            manifest = read(folder / 'manifest.json')
            check_materials(folder, manifest)
            return manifest
        write(prior, config)
        raw = folder / 'raw'
        raw.mkdir(exist_ok=True)
        for t in tracks:
            target = raw / (t['id'] + Path(t['path']).suffix.lower())
            shutil.copy2(t['path'], target)
            t['raw_path'] = str(target)
        write(folder / 'subtitle-tracks.json', {'selection': config['track'], 'selection_verified': False, 'tracks': tracks})
        segments = []
        if selected:
            for s in selected['segments']:
                a, b = max(start, s['start']), min(end, s['end'])
                if b > a:
                    segments.append({'start': a, 'end': b, 'text': s['text'],
                                     'source': selected['id'], 'language': 'unspecified'})
        captions = union([[s['start'], s['end']] for s in segments])
        quiet, skipped_quiet, processed, empty_asr, warnings = [], [], [], [], []
        if len(tracks) > 1:
            warnings.append('Selected the subtitle track with greatest temporal coverage; Agent must verify language and source quality.')
        if info and info['audio']:
            wav = folder / 'audio-scope.wav'
            audio_meta = folder / 'audio-cache.json'
            if not (wav.exists() and audio_meta.exists() and read(audio_meta).get('sha256') == digest(wav)):
                run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', media,
                     '-map', '0:a:0', '-af', 'aresample=16000:async=1:first_pts=0,apad', '-ac', '1',
                     '-ss', start, '-t', end - start, '-c:a', 'pcm_s16le', wav])
                write(audio_meta, {'sha256': digest(wav)})
            quiet = silence_intervals(wav, start, end)
            desired = [[start, end]] if args.asr == 'always' else subtract([[start, end]], captions)
            # Only auto skips estimated quiet; always must actually process its whole scope.
            long_quiet = [[a, b] for a, b in quiet if b - a >= 10]
            skipped_quiet = subtract(desired, subtract(desired, long_quiet)) if args.asr == 'auto' else []
            jobs = (subtract(desired, long_quiet) if args.asr == 'auto' else desired) if args.asr != 'never' else []
            jobs = [[a, b] for a, b in jobs if b - a >= 0.25]
            model = Path(args.model).expanduser() if args.model else default_model()
            if jobs and (not model or not model.is_file() or not shutil.which('whisper-cli') and not os.environ.get('CIRCUS_WHISPER_CLI')):
                warnings.append('Local ASR unavailable; subtitle/visual materials retained. Install whisper.cpp and a multilingual model, then prepare in a new output directory.')
                jobs = []
            if jobs:
                model_sha = digest(model)
                write(folder / 'asr-backend.json', {'tool': tool('whisper-cli'), 'model': str(model.resolve()),
                                                   'sha256': model_sha, 'language': args.language, 'translate': False})
            for a, b in jobs:
                for chunk in chunks(a, b, args.chunk_seconds, args.overlap):
                    cid = f"asr-{int(round(chunk['core_start'] * 1000)):010d}-{int(round(chunk['core_end'] * 1000)):010d}"
                    output = raw / cid
                    marker = raw / (cid + '.cache.json')
                    cache_key = {'chunk': chunk, 'model_sha256': model_sha, 'language': args.language, 'cpu': args.cpu}
                    valid = (output.with_suffix('.json').exists() and marker.exists()
                             and read(marker).get('key') == cache_key
                             and read(marker).get('sha256') == digest(output.with_suffix('.json')))
                    if not valid:
                        piece = raw / (cid + '.wav')
                        run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                             '-ss', chunk['start'] - start, '-i', wav, '-t', chunk['end'] - chunk['start'],
                             '-c:a', 'pcm_s16le', piece])
                        print(json.dumps({'progress': 'asr', 'range': [chunk['core_start'], chunk['core_end']]}), file=sys.stderr, flush=True)
                        command = [tool('whisper-cli'), '-m', model, '-f', piece, '-l', args.language,
                                   '-oj', '-of', output, '-mc', '0', '-np']
                        if args.cpu:
                            command.append('-ng')
                        run(command)
                        write(marker, {'key': cache_key, 'sha256': digest(output.with_suffix('.json'))})
                        piece.unlink(missing_ok=True)
                    mapped = map_asr(read(output.with_suffix('.json')), chunk, [start, end], args.language)
                    for s in mapped:
                        s['source'] = cid
                    segments += mapped
                    processed.append([chunk['core_start'], chunk['core_end']])
                    if not mapped:
                        empty_asr.append([chunk['core_start'], chunk['core_end']])
        if args.asr == 'always' and processed:
            # Retain supplied captions as alternate raw tracks; primary is the fresh ASR.
            segments = [s for s in segments if s['source'].startswith('asr-')]
        segments.sort(key=lambda s: (s['start'], s['end'], s['source']))
        for i, s in enumerate(segments):
            s['id'] = f's{i + 1:06d}'
        frames = extract_frames(folder, media, frame_times(start, end, args.frame_interval), args.frame_width) if info and info['video'] else []
        flags = anomalies(segments, quiet)
        if quiet:
            warnings.append('Quiet intervals are amplitude estimates, not proof of no speech; inspect when context suggests missing content.')
        if skipped_quiet:
            warnings.append('Auto ASR skipped estimated quiet intervals; retry the suspect range with --asr always in a new directory.')
        if args.range:
            warnings.append('Only the requested range was prepared; full-video understanding cannot be declared.')
        write(folder / 'transcript-original.json', {'schema': SCHEMA, 'segments': segments, 'anomalies': flags})
        write(folder / 'visual-evidence.json', {'frames': frames, 'observations': []})
        coverage = {'scope': [start, end], 'subtitle_intervals': captions, 'asr_processed': union(processed),
                    'asr_empty_intervals': union(empty_asr), 'estimated_quiet': quiet,
                    'asr_skipped_quiet': skipped_quiet,
                    'audio_not_transcribed': subtract([[start, end]], captions + processed) if info and info['audio'] else [],
                    'unprocessed_audio': subtract([[start, end]], captions + processed + quiet) if info and info['audio'] else [],
                    'sampled_frame_times': [f['time'] for f in frames], 'reviewed_frame_ids': [],
                    'reviewed_segment_ids': [], 'not_frame_by_frame': True}
        write(folder / 'coverage.json', coverage)
        manifest = {'schema': SCHEMA, 'status': 'materials_ready', 'source': source, 'config': config,
                    'warnings': warnings, 'anomalies': flags, 'artifacts': artifact_hashes(folder),
                    'manifest_path': str(folder / 'manifest.json'), 'semantic_review_complete': False}
        write(folder / 'manifest.json', manifest)
        return manifest


def supplement(args):
    folder = Path(args.package).expanduser().resolve()
    with locked(folder):
        manifest = read(folder / 'manifest.json')
        check_materials(folder, manifest)
        a, b = [number(t) for t in args.range.split(':')]
        scope = manifest['source']['scope']
        if a < scope[0] or not a < b <= scope[1]:
            raise JuggleError('Supplement range must lie within the prepared scope.')
        if not manifest['source']['probe']['video']:
            raise JuggleError('Source has no video track.')
        evidence = read(folder / 'visual-evidence.json')
        evidence['frames'] = extract_frames(folder, Path(manifest['source']['media']),
            frame_times(a, b, args.interval), manifest['config']['frame_width'], evidence['frames'])
        write(folder / 'visual-evidence.json', evidence)
        coverage = read(folder / 'coverage.json')
        coverage['sampled_frame_times'] = [f['time'] for f in evidence['frames']]
        write(folder / 'coverage.json', coverage)
        manifest['artifacts'] = artifact_hashes(folder)
        manifest['status'] = 'materials_ready'
        manifest['semantic_review_complete'] = False
        write(folder / 'manifest.json', manifest)
        old_final = folder / 'final/manifest.json'
        if old_final.exists():
            old = read(old_final)
            old.update(status='stale', semantic_review_complete=False,
                       remaining=['prepared_materials_changed_requires_new_review'])
            write(old_final, old)
        return manifest


def audio_clip(args):
    folder = Path(args.package).expanduser().resolve()
    manifest = read(folder / 'manifest.json')
    check_materials(folder, manifest)
    a, b = [number(t) for t in args.range.split(':')]
    scope = manifest['source']['scope']
    if not scope[0] <= a < b <= scope[1] or not (folder / 'audio-scope.wav').is_file():
        raise JuggleError('Audio clip requires an audio track and a range within the prepared scope.')
    output = Path(args.output).expanduser().resolve()
    if output.is_relative_to(folder) or output == Path(manifest['source']['media']):
        raise JuggleError('Write listening clips outside the sealed material package and source.')
    if output.exists():
        raise JuggleError('Listening clip output already exists; select a new path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-ss', a - scope[0],
         '-i', folder / 'audio-scope.wav', '-t', b - a, '-c:a', 'pcm_s16le', output])
    return {'path': str(output), 'range': [a, b], 'sha256': digest(output)}


def validate_review(manifest, transcript, visual, coverage, review, tracks=None):
    segments = {s['id']: s for s in transcript['segments']}
    frames = {f['id']: f for f in visual['frames']}
    alternate = {s['id']: {**s, 'track_id': t['id']} for t in (tracks or {}).get('tracks', []) for s in t['segments']}
    known = {**segments, **frames, **alternate}
    scope = manifest['source']['scope']

    def refs(ids):
        if not isinstance(ids, list) or not ids or any(i not in known for i in ids):
            raise JuggleError('Each content/correction needs existing evidence IDs.')

    def within(row):
        a, b = number(row['start']), number(row['end'])
        if not scope[0] <= a < b <= scope[1] + 0.05:
            raise JuggleError('Review time range outside prepared scope.')
        return a, b

    if review.get('schema') != SCHEMA or not str(review.get('summary', '')).strip():
        raise JuggleError('Review requires schema and a nonempty summary.')
    reviewed_s = review.get('reviewed_segment_ids', [])
    reviewed_f = review.get('reviewed_frame_ids', [])
    reviewed_t = review.get('reviewed_subtitle_ids', [])
    if not isinstance(reviewed_s, list) or not isinstance(reviewed_f, list) or not isinstance(reviewed_t, list) or set(reviewed_s) - segments.keys() or set(reviewed_f) - frames.keys() or set(reviewed_t) - alternate.keys():
        raise JuggleError('Invalid reviewed IDs.')
    reviewed = set(reviewed_s + reviewed_f + reviewed_t)
    for check in review.get('audio_checks', []):
        within(check)
        if not str(check.get('observation', '')).strip():
            raise JuggleError('Audio checks require an actual listened observation.')
    observations = review.get('observations', [])
    for o in observations:
        if o.get('frame_id') not in set(reviewed_f) or not str(o.get('text', '')).strip():
            raise JuggleError('Visual observations must refer to a reviewed frame.')
    for c in review.get('corrections', []):
        sid = c.get('segment_id')
        if sid not in set(reviewed_s) or c.get('original') != segments[sid]['text']:
            raise JuggleError('Correction original must exactly match the reviewed source segment.')
        refs(c.get('evidence_ids'))
        if set(c['evidence_ids']) - reviewed or not str(c.get('reason', '')).strip() or not str(c.get('corrected', '')).strip():
            raise JuggleError('Correction requires reviewed evidence, reason and corrected text.')
        if c.get('certainty') not in ('confirmed', 'uncertain'):
            raise JuggleError('Correction certainty must be confirmed or uncertain.')
        basis = c.get('basis')
        if basis == 'visual':
            observed = {o['frame_id'] for o in observations}
            if not set(c['evidence_ids']) & observed:
                raise JuggleError('Visual correction needs a frame observation.')
        elif basis == 'audio':
            checks = review.get('audio_checks', [])
            for check in checks:
                within(check)
                if not str(check.get('observation', '')).strip():
                    raise JuggleError('Audio checks need an observation.')
            s = segments[sid]
            if subtract([[s['start'], s['end']]], [[r['start'], r['end']] for r in checks]):
                raise JuggleError('Audio correction needs a listened range covering its segment.')
        elif basis == 'cross_segment':
            if not (set(c['evidence_ids']) & segments.keys()) - {sid}:
                raise JuggleError('Cross-segment correction needs another transcript segment.')
        elif basis == 'subtitle':
            ids = set(c['evidence_ids']) & alternate.keys()
            verified = set(review.get('verified_subtitle_tracks', []))
            target = segments[sid]
            if not ids or any(alternate[eid]['track_id'] not in verified for eid in ids):
                raise JuggleError('Subtitle correction requires a reviewed, verified alternate track.')
            if not any(alternate[eid]['start'] < target['end'] and alternate[eid]['end'] > target['start'] for eid in ids):
                raise JuggleError('Subtitle correction must cite a temporally matching alternate cue.')
        else:
            raise JuggleError('Correction basis must be visual, audio, subtitle or cross_segment.')
    correction_ids = [c['segment_id'] for c in review.get('corrections', [])]
    if len(set(correction_ids)) != len(correction_ids):
        raise JuggleError('Multiple corrections for one segment are ambiguous.')
    if not review.get('chapters') or not review.get('content'):
        raise JuggleError('Review needs chapters and evidence-linked content.')
    for row in review['chapters']:
        within(row)
        if not str(row.get('title', '')).strip():
            raise JuggleError('Chapter needs title.')
    for row in review['content']:
        a, b = within(row)
        refs(row.get('evidence_ids'))
        if set(row['evidence_ids']) - reviewed or row.get('kind') not in ('source_claim', 'visual_observation', 'agent_interpretation') or not str(row.get('text', '')).strip():
            raise JuggleError('Content needs a type, text and reviewed references.')
        for eid in row['evidence_ids']:
            e = known[eid]
            left, right = (e['time'], e['time']) if eid in frames else (e['start'], e['end'])
            if right < a - 2 or left > b + 2:
                raise JuggleError('Content evidence is outside its stated time range.')
    for row in review.get('unresolved', []):
        within(row)
        if not str(row.get('reason', '')).strip():
            raise JuggleError('Unresolved range needs a reason.')
    chapter_gaps = subtract([scope], [[c['start'], c['end']] for c in review['chapters']])
    remaining = []
    if set(segments) - set(reviewed_s):
        remaining.append('unreviewed_transcript')
    if set(frames) - set(reviewed_f):
        remaining.append('unreviewed_sampled_frames')
    if chapter_gaps:
        remaining.append('chapter_gaps')
    if coverage['unprocessed_audio']:
        remaining.append('unprocessed_audio')
    if coverage['asr_empty_intervals']:
        remaining.append('empty_asr_requires_review')
    if manifest['source']['upstream_status'] in ('partial', 'subtitles_only'):
        remaining.append('upstream_' + manifest['source']['upstream_status'])
    if not manifest['source'].get('media'):
        remaining.append('subtitles_only')
    if scope[0] > 0 or scope[1] < manifest['source']['duration'] - 0.05:
        remaining.append('requested_range_only')
    if review.get('unresolved') or any(c['certainty'] == 'uncertain' for c in review.get('corrections', [])):
        remaining.append('unresolved_review')
    resolved_flags = review.get('resolved_anomalies', [])
    if set(resolved_flags) != set(range(len(transcript.get('anomalies', [])))):
        remaining.append('asr_anomalies_not_reviewed')
    if any(s.get('source', '').startswith('track') for s in segments.values()) and review.get('subtitle_selection_verified') is not True:
        remaining.append('subtitle_selection_unverified')
    # A boolean alone cannot attest that estimated silence was actually listened to.
    quiet_checked = (review.get('quiet_intervals_checked') is True
                     and not subtract(coverage['estimated_quiet'],
                                      [[c['start'], c['end']] for c in review.get('audio_checks', [])]))
    if coverage['estimated_quiet'] and not quiet_checked:
        remaining.append('quiet_intervals_not_checked')
    if not segments and not frames:
        remaining.append('no_evidence')
    return remaining


def finalize(args):
    folder = Path(args.package).expanduser().resolve()
    with locked(folder):
        manifest = read(folder / 'manifest.json')
        check_materials(folder, manifest)
        transcript = read(folder / 'transcript-original.json')
        visual = read(folder / 'visual-evidence.json')
        coverage = read(folder / 'coverage.json')
        review = read(args.review)
        remaining = validate_review(manifest, transcript, visual, coverage, review, read(folder / 'subtitle-tracks.json'))
        final = folder / 'final'
        final.mkdir(exist_ok=True)
        corrections = {c['segment_id']: c for c in review.get('corrections', [])}
        corrected = []
        for s in transcript['segments']:
            row = dict(s)
            if s['id'] in corrections:
                row['correction'] = corrections[s['id']]
                # Uncertain alternatives do not silently replace the source text.
                if corrections[s['id']]['certainty'] == 'confirmed':
                    row['text'] = corrections[s['id']]['corrected']
            corrected.append(row)
        write(final / 'review.json', review)
        write(final / 'transcript-corrected.json', {'schema': SCHEMA, 'segments': corrected})
        write(final / 'content.json', {'schema': SCHEMA, 'summary': review['summary'], 'chapters': review['chapters'],
                                       'content': review['content'], 'unresolved': review.get('unresolved', [])})
        write(final / 'visual-evidence.json', {'frames': [{**f, 'reviewed': f['id'] in review['reviewed_frame_ids']} for f in visual['frames']],
                                              'observations': review.get('observations', [])})
        write(final / 'coverage.json', {**coverage, 'reviewed_frame_ids': review['reviewed_frame_ids'],
                                        'reviewed_segment_ids': review['reviewed_segment_ids'],
                                        'reviewed_subtitle_ids': review.get('reviewed_subtitle_ids', []), 'remaining': remaining})
        result = {**manifest, 'status': 'partial' if remaining else 'complete',
                  'semantic_review_complete': not remaining, 'remaining': remaining,
                  'review_attestation': 'Agent-declared reading; references validated, semantic truth not mechanically proven.',
                  'files': {name: str(final / name) for name in ('transcript-corrected.json', 'content.json', 'visual-evidence.json', 'coverage.json', 'review.json')},
                  'final_artifacts': {p.name: digest(p) for p in final.iterdir() if p.is_file() and p.name != 'manifest.json'},
                  'manifest_path': str(final / 'manifest.json')}
        write(final / 'manifest.json', result)
        return result


def doctor(args):
    model = Path(args.model).expanduser() if args.model else default_model()
    found = {}
    for name in ('ffmpeg', 'ffprobe', 'whisper-cli'):
        try:
            path = tool(name)
            option = '--help' if name == 'whisper-cli' else '-version'
            stdout, stderr = run([path, option], timeout=30)
            lines = (stdout + stderr).strip().splitlines()
            found[name] = {'path': path, 'available': True, 'version_hint': lines[0] if lines else ''}
        except (JuggleError, OSError, subprocess.TimeoutExpired):
            found[name] = {'available': False}
    return {'tools': found, 'model': str(model) if model else None, 'model_available': bool(model and model.is_file()),
            'python': sys.version.split()[0], 'material_processing': 'local', 'agent_inference': 'host-dependent'}


def positive(value):
    n = number(value)
    if n <= 0:
        raise argparse.ArgumentTypeError('Must be positive.')
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor')
    d.add_argument('--model')
    d.set_defaults(func=doctor)
    q = sub.add_parser('prepare')
    q.add_argument('source')
    q.add_argument('--output', required=True)
    q.add_argument('--subtitle', action='append', default=[])
    q.add_argument('--subtitle-offset', type=float, default=0)
    q.add_argument('--track')
    q.add_argument('--range', help='Video timeline START:END in seconds')
    q.add_argument('--language', default='auto')
    q.add_argument('--asr', choices=('auto', 'always', 'never'), default='auto')
    q.add_argument('--model')
    q.add_argument('--cpu', action='store_true')
    q.add_argument('--frame-interval', type=positive, default=30)
    q.add_argument('--frame-width', type=int, default=1280)
    q.add_argument('--chunk-seconds', type=positive, default=300)
    q.add_argument('--overlap', type=float, default=2)
    q.set_defaults(func=prepare)
    f = sub.add_parser('frames')
    f.add_argument('package')
    f.add_argument('--range', required=True)
    f.add_argument('--interval', type=positive, default=1)
    f.set_defaults(func=supplement)
    r = sub.add_parser('finalize')
    r.add_argument('package')
    r.add_argument('--review', required=True)
    r.set_defaults(func=finalize)
    a = sub.add_parser('audio')
    a.add_argument('package')
    a.add_argument('--range', required=True)
    a.add_argument('--output', required=True)
    a.set_defaults(func=audio_clip)
    args = p.parse_args()
    try:
        if args.command == 'prepare' and (args.frame_width < 64 or args.overlap < 0 or args.overlap >= args.chunk_seconds / 2):
            raise JuggleError('Invalid frame width or overlap.')
        result = args.func(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (JuggleError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        message = str(e) if isinstance(e, JuggleError) else 'Invalid local input, JSON, dependency or timeout; inspect the task files.'
        print(json.dumps({'schema': SCHEMA, 'status': 'failed', 'message': message}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
