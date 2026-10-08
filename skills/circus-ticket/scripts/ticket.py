#!/usr/bin/env python3
"""Render a verified, reviewed video content package into a local reading report."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
from pathlib import Path
import sys

SCHEMA = 'circus-ticket/1'
KINDS = {'source_claim': '讲师说明', 'visual_observation': '画面观察', 'agent_interpretation': '整理者归纳'}
class TicketError(Exception): pass

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()
def escaped(value): return html.escape(str(value), quote=True)
def clock(value):
    seconds = int(value)
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}' if seconds >= 3600 else f'{seconds//60:02d}:{seconds%60:02d}'
def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TicketError('Expected finite timestamps.')
    return value

def check_seals(folder, hashes):
    if not isinstance(hashes, dict) or not hashes: raise TicketError('Artifact seals are required.')
    for rel, expected in hashes.items():
        p = (folder / rel).resolve()
        if not p.is_relative_to(folder.resolve()) or not p.is_file() or sha(p) != expected:
            raise TicketError('An input artifact is missing, changed or outside its package.')

def load_package(path):
    path = Path(path).expanduser().resolve()
    m = read(path)
    if m.get('schema') != 'circus-juggler/1' or m.get('status') not in ('complete', 'partial'):
        raise TicketError('Use a reviewed final manifest; materials_ready and stale are not report inputs.')
    folder, root = path.parent, path.parent.parent
    check_seals(folder, m.get('final_artifacts'))
    required = {'content.json', 'transcript-corrected.json', 'visual-evidence.json', 'review.json', 'coverage.json'}
    if not required <= m['final_artifacts'].keys():
        raise TicketError('Required final artifacts must all be sealed.')
    prepared = read(root / 'manifest.json')
    if m.get('artifacts') != prepared.get('artifacts') or m.get('source') != prepared.get('source'):
        raise TicketError('Final review does not match its prepared source.')
    check_seals(root, prepared.get('artifacts'))
    media = m['source'].get('media')
    if media and (not Path(media).is_file() or sha(media) != m['source']['sha256']):
        raise TicketError('Source media changed or is unavailable.')
    upstream = m['source'].get('upstream_manifest')
    if upstream and (not Path(upstream['path']).is_file() or sha(upstream['path']) != upstream['sha256']):
        raise TicketError('Upstream source evidence changed.')
    scope = m['source']['scope']
    if not 0 <= finite(scope[0]) < finite(scope[1]): raise TicketError('Invalid source scope.')
    content, transcript, visual, review = [read(folder / name) for name in
        ('content.json', 'transcript-corrected.json', 'visual-evidence.json', 'review.json')]
    evidence = {}
    reviewed = set(review['reviewed_segment_ids'] + review['reviewed_frame_ids'])
    for s in transcript['segments']:
        if s['id'] in reviewed:
            evidence[s['id']] = {'type': 'transcript', 'start': s['start'], 'end': s['end'], 'text': s['text']}
    if review.get('reviewed_subtitle_ids'):
        if 'subtitle-tracks.json' not in prepared['artifacts']:
            raise TicketError('Alternate subtitle evidence must be sealed.')
        tracks = read(root / 'subtitle-tracks.json')
        verified = set(review.get('verified_subtitle_tracks', []))
        for track in tracks['tracks']:
            if track['id'] not in verified: continue
            for s in track['segments']:
                if s['id'] in review['reviewed_subtitle_ids'] and s['id'] not in evidence:
                    evidence[s['id']] = {'type': 'subtitle', 'track': track['id'],
                        'start': s['start'], 'end': s['end'], 'text': s['text']}
    observations = {o['frame_id']: o['text'] for o in visual['observations']}
    for f in visual['frames']:
        if f['id'] not in reviewed or f['id'] not in observations: continue
        image = Path(f['path']).resolve()
        if not image.is_relative_to(root) or not image.is_file() or sha(image) != f['sha256']:
            raise TicketError('A cited frame is missing, changed or outside the input package.')
        mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(image.suffix.lower())
        if not mime: raise TicketError('Unsupported frame image type.')
        evidence[f['id']] = {'type': 'frame', 'start': f['time'], 'end': f['time'],
            'text': observations[f['id']], 'image': f'data:{mime};base64,' + base64.b64encode(image.read_bytes()).decode()}
    for row in content['content']:
        if row.get('kind') not in KINDS: raise TicketError('Invalid content kind.')
        check_refs(row, evidence)
    return m, content, transcript, evidence

def check_refs(row, evidence):
    ids = row.get('evidence_ids')
    if not isinstance(ids, list) or not ids or any(i not in evidence for i in ids):
        raise TicketError('Editorial/content references must be reviewed transcript or observed frame IDs.')

def editorial_input(path, evidence):
    d = read(path)
    if not isinstance(d.get('title'), str) or not d['title'].strip(): raise TicketError('A report title is required.')
    for key in ('brief', 'highlights', 'boundaries', 'applications', 'faq'):
        rows = d.get(key, [])
        if not isinstance(rows, list) or key == 'brief' and not rows: raise TicketError('The brief needs evidence-linked entries.')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not row['text'].strip() or row.get('kind') not in KINDS:
                raise TicketError('Each editorial entry needs text and an explicit claim type.')
            check_refs(row, evidence)
    return d

def safe_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')

def render(args):
    path = Path(args.manifest).expanduser().resolve()
    m, c, transcript, evidence = load_package(path)
    d = editorial_input(args.editorial, evidence)
    out = Path(args.output).expanduser().resolve()
    root = path.parent.parent
    if out == root or out.is_relative_to(root) or root.is_relative_to(out):
        raise TicketError('Use a separate report directory outside the input package.')
    if out.exists() and any(out.iterdir()): raise TicketError('Report directory must be empty; preserve prior reports.')
    def refs(row):
        ids = escaped(json.dumps(row['evidence_ids'], ensure_ascii=False))
        return f'<button class="evidence-link" data-evidence="{ids}">查看依据 ↗</button>'
    def entry(row):
        title = f'<h3>{escaped(row["title"])}</h3>' if row.get('title') else ''
        return f'<article class="entry">{title}<p>{escaped(row["text"])}</p><span class="kind">{KINDS[row["kind"]]}</span> {refs(row)}</article>'
    def section(key, title, number):
        rows = d.get(key, [])
        if not rows: return ''
        return f'<section id="{key}"><div class="section-no">{number} / READING NOTES</div><h2>{title}</h2>' + ''.join(entry(row) for row in rows) + '</section>'
    chapters, nav, md = [], [], [f'# 🎫 {d["title"]}', '', f'内容审阅状态：{m["status"]}。采样审阅不等于逐帧确认。', '']
    for n, ch in enumerate(c['chapters'], 1):
        ident = f'ch{n:02d}'
        rows = [r for r in c['content'] if r['kind'] != 'visual_observation' and r['start'] < ch['end'] and r['end'] > ch['start']]
        body = ''.join(entry(r) for r in rows)
        pictures = [r for r in c['content'] if r['kind'] == 'visual_observation' and ch['start'] <= r['start'] < ch['end']]
        for r in pictures:
            for eid in r['evidence_ids']:
                ev = evidence[eid]
                if ev['type'] == 'frame':
                    body += f'<figure><img loading="lazy" src="{ev["image"]}" alt="{escaped(ev["text"])}"><figcaption>{clock(ev["start"])} · {escaped(ev["text"])} {refs(r)}</figcaption></figure>'
                    break
        chapters.append(f'<details class="chapter" id="{ident}" open><summary><span class="section-no">CHAPTER {n:02d} · {clock(ch["start"])}–{clock(ch["end"])}</span><h3>{escaped(ch["title"])}</h3></summary><div class="chapter-body">{body}</div></details>')
        nav.append(f'<a href="#{ident}"><b>{n:02d}</b> {escaped(ch["title"])}</a>')
        md += [f'## {clock(ch["start"])}–{clock(ch["end"])} · {ch["title"]}', '']
        for row in rows: md += [f'{KINDS[row["kind"]]}：{row["text"]}', '依据：' + ', '.join(row['evidence_ids']), '']
    tr = ''.join(f'<article class="transcript-row" id="{escaped(s["id"])}"><span>{clock(s["start"])}<small>{escaped(s["id"])}</small>'
        + ('<small>未审阅</small>' if s['id'] not in evidence else '')
        + f'</span><p>{escaped(s["text"])}</p></article>' for s in transcript['segments'])
    unresolved = ''.join(f'<li><span>{clock(r["start"])}–{clock(r["end"])}</span> {escaped(r["reason"])}</li>' for r in c['unresolved'])
    gaps = '<section id="uncertainty"><div class="section-no">REVIEW / OPEN QUESTIONS</div><h2>待确认事项</h2><ul>' + unresolved + '</ul></section>' if unresolved else ''
    optional_nav = ''.join(f'<a href="#{key}">{label}</a>' for key, label in
        [('highlights', '关键观点'), ('boundaries', '能力与边界'), ('applications', '应用建议'), ('faq', '复习问答')]
        if d.get(key))
    if unresolved: optional_nav += '<a href="#uncertainty">待确认事项</a>'
    source = f'<p>视频总长 {clock(m["source"]["duration"])}；本包范围 {clock(m["source"]["scope"][0])}–{clock(m["source"]["scope"][1])}。内容状态：{m["status"]}。</p><p>文字来自最终校正稿，未审阅段另行标记；原文及校正依据由上游保留。画面来自已查看且有观察记录的采样帧，不表示逐帧覆盖。产品和竞争说法按讲师主张呈现。</p>'
    status = '仍有待确认事项' if m['status'] == 'partial' else '已完成有采样边界的内容审阅'
    template = Path(__file__).resolve().parents[1] / 'assets/report.html'
    values = {'TITLE': escaped(d['title']), 'SUBTITLE': escaped(d.get('subtitle', '视频内容阅读报告')), 'STATUS': status,
              'DURATION': clock(m['source']['duration']), 'NAV': ''.join(nav), 'OPTIONALNAV': optional_nav, 'COUNT': str(len(chapters)),
              'BRIEF': ''.join(entry(r) for r in d['brief']), 'CHAPTERS': ''.join(chapters),
              'EXTRAS': section('highlights', '值得记住的观点', '03') + section('boundaries', '能力、主张与边界', '04') + section('applications', '如何用于后续工作', '05') + section('faq', '复习与问答', '06') + gaps,
              'TRANSCRIPT': tr, 'SOURCE': source,
              'DATA': safe_json(evidence), 'REMAINING': escaped(' / '.join(m.get('remaining', [])))}
    page = re.sub(r'@@([A-Z]+)@@', lambda match: values[match[1]], template.read_text())
    # Every output is derived locally; no original local paths or signed source URLs are exported.
    document = {'schema': SCHEMA, 'source_status': m['status'], 'source_scope': m['source']['scope'],
                'remaining': m.get('remaining', []), 'editorial': d, 'content': c,
                'evidence': {k: {a: b for a, b in v.items() if a != 'image'} for k, v in evidence.items()}}
    out.mkdir(parents=True, exist_ok=True); os.chmod(out, 0o700)
    (out / 'report.html').write_text(page, encoding='utf-8')
    for key in ('brief', 'highlights', 'boundaries', 'applications', 'faq'):
        if d.get(key):
            md += ['## ' + {'brief':'简报','highlights':'关键观点','boundaries':'边界','applications':'应用建议','faq':'复习问答'}[key], '']
            for row in d[key]:md += [row.get('title', ''), row['text'], '依据：' + ', '.join(row['evidence_ids']), '']
    md += ['## 待确认事项', ''] + [f'{clock(r["start"])}–{clock(r["end"])}：{r["reason"]}' for r in c['unresolved']]
    (out / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    (out / 'report.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'schema': SCHEMA, 'status': 'rendered', 'source_status': m['status'], 'visual_qa': 'not_performed',
              'input_manifest_sha256': sha(path), 'editorial_sha256': sha(args.editorial),
              'files': {n: sha(out / n) for n in ('report.html','report.md','report.json')},
              'report_path': str(out / 'report.html')}
    (out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for p in out.iterdir():os.chmod(p, 0o600)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest'); p.add_argument('--editorial', required=True); p.add_argument('--output', required=True)
    args = p.parse_args()
    try: result = render(args)
    except (TicketError, OSError, ValueError, KeyError, TypeError) as e:
        result = {'schema': SCHEMA, 'status': 'failed', 'message': str(e) if isinstance(e, TicketError) else 'Invalid local report input; inspect the source package.'}
        print(json.dumps(result, ensure_ascii=False)); return 2
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
if __name__ == '__main__':sys.exit(main())
