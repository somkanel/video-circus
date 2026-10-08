import argparse
import array
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/circus-juggler/scripts/juggle.py'
spec = importlib.util.spec_from_file_location('juggle', SCRIPT)
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)


class TimelineTests(unittest.TestCase):
    def test_gaps_keep_missing_ranges(self):
        self.assertEqual(j.subtract([[0, 10]], [[2, 4], [3, 7]]), [[0, 2], [7, 10]])

    def test_rolling_vtt_and_entities(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'cc.vtt'
            p.write_text('WEBVTT\n\n00:00.000 --> 00:02.000\nHello world\n\n00:01.000 --> 00:03.000\nHello world\n\n00:02.000 --> 00:04.000\nHello world &amp; friends\n')
            rows = j.parse_subtitle(p)
            self.assertEqual([s['text'] for s in rows], ['Hello world', '& friends'])
            self.assertEqual(rows[0]['end'], 3)

    def test_invalid_subtitle_range_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'cc.srt'
            p.write_text('1\n00:00:05,000 --> 00:00:02,000\nwrong\n')
            with self.assertRaises(j.JuggleError):
                j.parse_subtitle(p)

    def test_unsupported_subtitle_is_not_silently_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'cc.ass'
            p.write_text('[Events]\nDialogue: something')
            with self.assertRaises(j.JuggleError):
                j.parse_subtitle(p)

    def test_asr_overlap_maps_once_and_scope_absolute(self):
        chunks = list(j.chunks(60, 80, 10, 2))
        raw = {'transcription': [{'offsets': {'from': 8000, 'to': 10000}, 'text': 'overlap'}]}
        first = j.map_asr(raw, chunks[0], [60, 80], 'auto')
        self.assertEqual(first[0]['start'], 68)
        second_raw = {'transcription': [{'offsets': {'from': 0, 'to': 2000}, 'text': 'overlap'}]}
        self.assertEqual(j.map_asr(second_raw, chunks[1], [60, 80], 'auto'), [])

    def test_empty_and_nonfinite_inputs_rejected(self):
        with self.assertRaises(j.JuggleError):
            j.number(float('nan'))
        with self.assertRaises(j.JuggleError):
            j.number(True)

    def test_overlapping_asr_chunk_timestamps_are_review_flags(self):
        flags = j.anomalies([{'id': 's1', 'start': 9, 'end': 11, 'text': 'first', 'source': 'asr-0'},
                             {'id': 's2', 'start': 10, 'end': 12, 'text': 'second', 'source': 'asr-10'}])
        self.assertEqual(flags[0]['kind'], 'overlapping_chunk_timestamps')
        self.assertEqual((flags[0]['start'], flags[0]['end']), (10, 11))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class MaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.media = cls.root / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x90:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '3',
                        '-c:v', 'mpeg4', '-c:a', 'aac', cls.media], check=True, capture_output=True)
        cls.silent = cls.root / 'silent.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', cls.media, '-an', '-c:v', 'copy', cls.silent], check=True, capture_output=True)
        cls.sub = cls.root / 'cc.srt'
        cls.sub.write_text('1\n00:00:00,000 --> 00:00:03,000\nProduct Sobia\n')
        cls.quiet_audio = cls.root / 'quiet.wav'
        with wave.open(str(cls.quiet_audio), 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(b'\0\0' * 16000 * 16)
        cls.model = cls.root / 'test-model.bin'
        cls.model.write_bytes(b'fixture model')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)
        self.folder = Path(self.out.name)

    def args(self, **overrides):
        data = dict(source=str(self.media), output=str(self.folder), subtitle=[str(self.sub)],
                    subtitle_offset=0, range=None, track=None, language='auto', asr='never',
                    model=None, cpu=True, frame_interval=1, frame_width=1280, chunk_seconds=300, overlap=2)
        data.update(overrides)
        return argparse.Namespace(**data)

    def prepared(self, **overrides):
        m = j.prepare(self.args(**overrides))
        return m, j.read(self.folder / 'transcript-original.json'), j.read(self.folder / 'visual-evidence.json'), j.read(self.folder / 'coverage.json')

    def review(self, m, t, v):
        a, b = m['source']['scope']
        return {'schema': j.SCHEMA, 'summary': 'Fixture reviewed.',
                'reviewed_segment_ids': [s['id'] for s in t['segments']],
                'reviewed_frame_ids': [f['id'] for f in v['frames']],
                'subtitle_selection_verified': True, 'quiet_intervals_checked': True,
                'resolved_anomalies': [], 'chapters': [{'start': a, 'end': b, 'title': 'Product'}],
                'content': [{'start': a, 'end': b, 'kind': 'source_claim', 'text': 'Product name as spoken.',
                             'evidence_ids': [t['segments'][0]['id']] if t['segments'] else [v['frames'][0]['id']]}],
                'corrections': [], 'observations': [], 'unresolved': []}

    def test_materials_not_semantic_completion_and_cache(self):
        m, t, v, c = self.prepared()
        self.assertEqual(m['status'], 'materials_ready')
        self.assertFalse(m['semantic_review_complete'])
        self.assertTrue(all(not f['reviewed'] for f in v['frames']))
        self.assertEqual(j.prepare(self.args()), m)

    def test_unread_frames_never_complete(self):
        m, t, v, c = self.prepared()
        r = self.review(m, t, v)
        r['reviewed_frame_ids'] = []
        self.assertIn('unreviewed_sampled_frames', j.validate_review(m, t, v, c, r))

    def test_missing_audio_not_hidden(self):
        m, t, v, c = self.prepared(subtitle=[])
        r = self.review(m, t, v)
        self.assertEqual(c['unprocessed_audio'], [[0, 3]])
        self.assertIn('unprocessed_audio', j.validate_review(m, t, v, c, r))

    def test_always_processes_quiet_and_flags_suspect_text(self):
        calls = []
        real_run = j.run
        def backend(cmd, *args, **kwargs):
            if str(cmd[0]) == 'fixture-whisper':
                calls.append(cmd)
                target = Path(cmd[cmd.index('-of') + 1]).with_suffix('.json')
                j.write(target, {'transcription': [{'offsets': {'from': 0, 'to': 16000}, 'text': 'unsupported speech'}]})
                return '', ''
            return real_run(cmd, *args, **kwargs)
        with patch.dict('os.environ', {'CIRCUS_WHISPER_CLI': 'fixture-whisper'}), patch.object(j, 'run', side_effect=backend):
            m, t, v, c = self.prepared(source=str(self.quiet_audio), subtitle=[], asr='always', model=str(self.model))
        self.assertEqual(len(calls), 1)
        self.assertEqual(c['asr_processed'], [[0, 16]])
        self.assertEqual(c['asr_skipped_quiet'], [])
        self.assertEqual(c['audio_not_transcribed'], [])
        self.assertEqual(t['segments'][0]['text'], 'unsupported speech')
        self.assertEqual(t['anomalies'][0]['kind'], 'speech_on_estimated_quiet')
        r = self.review(m, t, v)
        self.assertIn('quiet_intervals_not_checked', j.validate_review(m, t, v, c, r))
        self.assertIn('asr_anomalies_not_reviewed', j.validate_review(m, t, v, c, r))
        r['audio_checks'] = [{'start': 0, 'end': 8, 'observation': 'First half actually listened.'}]
        self.assertIn('quiet_intervals_not_checked', j.validate_review(m, t, v, c, r))
        r['audio_checks'] = [{'start': 0, 'end': 16, 'observation': 'Whole estimated-quiet interval actually listened.'}]
        self.assertNotIn('quiet_intervals_not_checked', j.validate_review(m, t, v, c, r))

    def test_auto_quiet_skip_is_explicit(self):
        m, t, v, c = self.prepared(source=str(self.quiet_audio), subtitle=[], asr='auto')
        self.assertEqual(c['asr_processed'], [])
        self.assertEqual(c['asr_skipped_quiet'], [[0, 16]])
        self.assertEqual(c['audio_not_transcribed'], [[0, 16]])
        self.assertTrue(any('Auto ASR skipped' in x for x in m['warnings']))

    def test_upstream_partial_remains_partial(self):
        p = self.folder.parent / (self.folder.name + '-upstream.json')
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        j.write(p, {'schema': 'video-fetch/1', 'status': 'partial', 'files': [
            {'kind': 'video', 'path': str(self.media), 'sha256': j.digest(self.media)}]})
        m, t, v, c = self.prepared(source=str(p))
        self.assertIn('upstream_partial', j.validate_review(m, t, v, c, self.review(m, t, v)))

    def test_upstream_hash_mismatch_stops(self):
        p = self.folder / 'upstream.json'
        j.write(p, {'schema': 'video-fetch/1', 'status': 'complete', 'files': [
            {'kind': 'video', 'path': str(self.media), 'sha256': 'wrong'}]})
        with self.assertRaises(j.JuggleError):
            j.prepare(self.args(source=str(p)))

    def test_upstream_evidence_change_invalidates_prepared_package(self):
        p = self.folder.parent / (self.folder.name + '-origin-manifest.json')
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        original = {'schema': 'video-fetch/1', 'status': 'complete', 'metadata': {'title': 'Observed title'},
                    'files': [{'kind': 'video', 'path': str(self.media), 'sha256': j.digest(self.media)}]}
        j.write(p, original)
        m, *_ = self.prepared(source=str(p))
        self.assertEqual(m['source']['upstream_manifest']['sha256'], j.digest(p))
        original['metadata']['title'] = 'Different title'
        j.write(p, original)
        with self.assertRaises(j.JuggleError):
            j.check_materials(self.folder, m)

    def test_changed_artifact_rejected(self):
        m, *_ = self.prepared()
        (self.folder / 'transcript-original.json').write_text('{}')
        with self.assertRaises(j.JuggleError):
            j.check_materials(self.folder, m)

    def test_bad_reference_and_outside_time_rejected(self):
        m, t, v, c = self.prepared()
        r = self.review(m, t, v)
        r['content'][0]['evidence_ids'] = ['invented']
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, r)
        r = self.review(m, t, v)
        r['chapters'][0]['end'] = 99
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, r)

    def test_correction_requires_actual_evidence_and_exact_original(self):
        m, t, v, c = self.prepared()
        r = self.review(m, t, v)
        correction = {'segment_id': t['segments'][0]['id'], 'original': 'Product Sobia', 'corrected': 'Product Solvea',
                      'reason': 'Screen confirms spelling.', 'certainty': 'confirmed', 'basis': 'visual',
                      'evidence_ids': [v['frames'][0]['id']]}
        r['corrections'] = [correction]
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, r)
        r['observations'] = [{'frame_id': v['frames'][0]['id'], 'text': 'Solvea visible.'}]
        self.assertEqual(j.validate_review(m, t, v, c, r), [])
        r['corrections'][0]['original'] = 'imagined'
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, r)

    def test_audio_correction_needs_listened_range(self):
        m, t, v, c = self.prepared()
        r = self.review(m, t, v)
        r['corrections'] = [{'segment_id': t['segments'][0]['id'], 'original': 'Product Sobia',
            'corrected': 'Product Solvea', 'reason': 'Replayed audio.', 'certainty': 'confirmed',
            'basis': 'audio', 'evidence_ids': [t['segments'][0]['id']]}]
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, r)
        r['audio_checks'] = [{'start': 0, 'end': 3, 'observation': 'Speaker clearly says Solvea.'}]
        self.assertEqual(j.validate_review(m, t, v, c, r), [])

    def test_finalize_preserves_original(self):
        m, t, v, c = self.prepared()
        r = self.review(m, t, v)
        r['corrections'] = [{'segment_id': t['segments'][0]['id'], 'original': 'Product Sobia', 'corrected': 'Product Solvea',
                            'reason': 'Screen text.', 'certainty': 'confirmed', 'basis': 'visual', 'evidence_ids': [v['frames'][0]['id']]}]
        r['observations'] = [{'frame_id': v['frames'][0]['id'], 'text': 'Screen: Solvea'}]
        path = self.folder / 'review.json'
        j.write(path, r)
        out = j.finalize(argparse.Namespace(package=str(self.folder), review=str(path)))
        self.assertEqual(out['status'], 'complete')
        self.assertEqual(j.read(self.folder / 'transcript-original.json')['segments'][0]['text'], 'Product Sobia')
        self.assertEqual(j.read(self.folder / 'final/transcript-corrected.json')['segments'][0]['text'], 'Product Solvea')

    def test_subtitle_offset_and_scope_keep_video_time(self):
        m, t, v, c = self.prepared(range='1:2', subtitle_offset=0.5)
        self.assertEqual((t['segments'][0]['start'], t['segments'][0]['end']), (1, 2))
        self.assertEqual(v['frames'][0]['time'], 1)
        self.assertIn('requested_range_only', j.validate_review(m, t, v, c, self.review(m, t, v)))

    def test_silent_video_visual_only_and_supplement(self):
        m, t, v, c = self.prepared(source=str(self.silent), subtitle=[])
        self.assertFalse(m['source']['probe']['audio'])
        j.supplement(argparse.Namespace(package=str(self.folder), range='0:2', interval=0.25))
        frames = j.read(self.folder / 'visual-evidence.json')['frames']
        self.assertGreater(len(frames), len(v['frames']))
        self.assertEqual(j.read(self.folder / 'manifest.json')['status'], 'materials_ready')

    def test_audio_delay_preserved_on_common_video_timeline(self):
        media = self.folder.parent / (self.folder.name + '-delayed.mp4')
        self.addCleanup(lambda: media.unlink(missing_ok=True))
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x90:rate=10',
                        '-itsoffset', '1', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000',
                        '-t', '3', '-c:v', 'mpeg4', '-c:a', 'aac', media], check=True, capture_output=True)
        manifest, *_ = self.prepared(source=str(media), subtitle=[])
        with wave.open(str(self.folder / 'audio-scope.wav')) as f:
            samples = array.array('h', f.readframes(f.getnframes()))
            rate = f.getframerate()
        early = samples[:int(rate * 0.5)]
        later = samples[int(rate * 1.3):int(rate * 1.5)]
        self.assertLess(sum(abs(s) for s in early) / len(early), 1)
        self.assertGreater(sum(abs(s) for s in later) / len(later), 100)
        self.assertAlmostEqual(len(samples) / rate, manifest['source']['duration'], places=2)

    def test_supplement_invalidates_prior_final_manifest(self):
        m, t, v, c = self.prepared()
        review_path = self.folder / 'review.json'
        j.write(review_path, self.review(m, t, v))
        j.finalize(argparse.Namespace(package=str(self.folder), review=str(review_path)))
        j.supplement(argparse.Namespace(package=str(self.folder), range='0:1', interval=0.25))
        self.assertEqual(j.read(self.folder / 'final/manifest.json')['status'], 'stale')

    def test_uncertain_correction_never_replaces_source(self):
        m, t, v, c = self.prepared()
        review = self.review(m, t, v)
        review['corrections'] = [{'segment_id': t['segments'][0]['id'], 'original': 'Product Sobia',
            'corrected': 'Product Solvea', 'reason': 'Screen text is blurry.', 'certainty': 'uncertain',
            'basis': 'visual', 'evidence_ids': [v['frames'][0]['id']]}]
        review['observations'] = [{'frame_id': v['frames'][0]['id'], 'text': 'Possible Solvea.'}]
        review_path = self.folder / 'review.json'
        j.write(review_path, review)
        out = j.finalize(argparse.Namespace(package=str(self.folder), review=str(review_path)))
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(j.read(self.folder / 'final/transcript-corrected.json')['segments'][0]['text'], 'Product Sobia')

    def test_alternate_subtitle_correction_requires_verified_source(self):
        alternate = self.folder.parent / (self.folder.name + '-alternate.srt')
        alternate.write_text('1\n00:00:00,000 --> 00:00:03,000\nProduct Solvea\n')
        self.addCleanup(lambda: alternate.unlink(missing_ok=True))
        m, t, v, c = self.prepared(subtitle=[str(self.sub), str(alternate)])
        tracks = j.read(self.folder / 'subtitle-tracks.json')
        aid = tracks['tracks'][1]['segments'][0]['id']
        review = self.review(m, t, v)
        review['reviewed_subtitle_ids'] = [aid]
        review['corrections'] = [{'segment_id': t['segments'][0]['id'], 'original': 'Product Sobia',
            'corrected': 'Product Solvea', 'reason': 'Alternate original caption matches this moment.',
            'certainty': 'confirmed', 'basis': 'subtitle', 'evidence_ids': [aid]}]
        with self.assertRaises(j.JuggleError):
            j.validate_review(m, t, v, c, review, tracks)
        review['verified_subtitle_tracks'] = ['track2']
        self.assertEqual(j.validate_review(m, t, v, c, review, tracks), [])

    def test_subtitles_only_is_partial(self):
        m, t, v, c = self.prepared(source=str(self.sub), subtitle=[])
        self.assertEqual(v['frames'], [])
        self.assertIn('subtitles_only', j.validate_review(m, t, v, c, self.review(m, t, v)))

    def test_output_reuse_different_config_rejected(self):
        self.prepared()
        with self.assertRaises(j.JuggleError):
            j.prepare(self.args(language='zh'))


if __name__ == '__main__':
    unittest.main()
