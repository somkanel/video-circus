"""Observable behavior using generated media, a local HTTP server and platform stubs."""
import argparse
import functools
import http.server
import importlib.util
import json
import io
from email.message import Message
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/circus-conjurer/scripts/fetch.py'
spec = importlib.util.spec_from_file_location('fetch', SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe required')
class FetchIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='video-fetch-tests-')
        cls.root = Path(cls.tmp.name)
        cls.media = cls.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x90:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000', '-t', '2',
                        '-c:v', 'mpeg4', '-c:a', 'aac', str(cls.media)], check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(cls.media), '-c:v', 'libx264',
                        '-c:a', 'aac', '-g', '10', '-hls_time', '1', '-hls_list_size', '0',
                        str(cls.root / 'playlist.m3u8')], check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(cls.media), '-c:v', 'libx264',
                        '-c:a', 'aac', '-g', '10', '-f', 'dash', '-seg_duration', '1',
                        str(cls.root / 'manifest.mpd')], check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(cls.media), '-an', '-c:v', 'copy',
                        str(cls.root / 'silent.mp4')], check=True, capture_output=True)
        (cls.root / 'nested.html').write_text('<iframe src="inner.html"></iframe>')
        (cls.root / 'inner.html').write_text('<video><source src="clip.mp4"></video>')
        (cls.root / 'multiple.html').write_text('<video src="clip.mp4"></video><video src="other.mp4"></video>')
        shutil.copy(cls.media, cls.root / 'other.mp4')
        (cls.root / 'dynamic.html').write_text('<video src="blob:example"></video><script>/* runtime player */</script>')
        (cls.root / 'fake.mp4').write_text('<html>not a video</html>')
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(cls.root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def setUp(self):
        self.out = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.out.cleanup)

    def args(self, source, **changes):
        values = dict(source=source, output=self.out.name, mode='video', quality='best', langs='all',
                      audio_format='mp3', cookies_browser=None, headers_file=None, referer=None,
                      candidates_file=None, candidate=None, timeout=30, quick=False, force=False)
        values.update(changes)
        return argparse.Namespace(**values)

    def no_extractor(self):
        return patch.object(fetch, 'extract_info', side_effect=fetch.FetchError('extractor_failed', 'fixture'))

    def test_local_reference_and_full_decode(self):
        result = fetch.acquire(self.args(str(self.media)))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['files'][0]['path'], str(self.media.resolve()))
        self.assertEqual(result['files'][0]['decode_check'], 'full')
        self.assertTrue(result['files'][0]['audio'])

    def origin(self, **changes):
        data = dict(page_url='https://user:secret@example.com/lesson?token=PRIVATE_SECRET#fragment',
                    title='Host-observed lesson', duration=2, acquisition_method='host_download',
                    observed_by='fixture browser', media_sha256=fetch.digest_file(self.media))
        data.update(changes)
        p = Path(self.out.name) / 'origin.json'
        p.write_text(json.dumps(data))
        return str(p)

    def test_host_origin_bound_redacted_and_duration_checked(self):
        result = fetch.acquire(self.args(str(self.media), origin_file=self.origin()))
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['files'][0]['duration_matches_source'])
        self.assertEqual(result['source']['page_url'], 'https://example.com/lesson')
        self.assertEqual(result['source']['origin']['evidence_basis'], 'host_observation')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(result))
        self.assertNotIn('user:secret', json.dumps(result))
        changed = fetch.acquire(self.args(str(self.media), origin_file=self.origin(duration=20)))
        self.assertEqual(changed['status'], 'partial')
        self.assertNotEqual(changed['job_id'], result['job_id'])
        self.assertFalse(changed['files'][0]['duration_matches_source'])

    def test_host_origin_rejects_wrong_media_secrets_and_bad_duration(self):
        for values in [{'media_sha256': 'wrong'}, {'Cookie': 'secret'}, {'duration': float('nan')},
                       {'duration': True}, {'duration': -1}]:
            with self.subTest(values=values), self.assertRaises(fetch.FetchError):
                fetch.acquire(self.args(str(self.media), origin_file=self.origin(**values)))

    def test_host_origin_cannot_override_remote_extractor(self):
        with self.assertRaises(fetch.FetchError):
            fetch.acquire(self.args(self.url + '/clip.mp4', origin_file=self.origin()))

    def test_cache_rejects_modified_input(self):
        args = self.args(str(self.media))
        first = fetch.acquire(args)
        self.assertTrue(fetch.acquire(args)['cached'])
        # Corrupt stored hash without touching the user's original video.
        path = Path(first['manifest_path'])
        manifest = json.loads(path.read_text())
        manifest['files'][0]['sha256'] = 'invalid'
        path.write_text(json.dumps(manifest))
        self.assertFalse(fetch.acquire(args)['cached'])

    def test_direct_url_verified_and_signed_query_redacted(self):
        result = fetch.acquire(self.args(self.url + '/clip.mp4?token=PRIVATE_SECRET'))
        self.assertEqual(result['status'], 'complete')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(result))
        self.assertAlmostEqual(result['files'][0]['duration_seconds'], 2, delta=.2)

    def test_hls_remux(self):
        result = fetch.acquire(self.args(self.url + '/playlist.m3u8'))
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['files'][0]['video'])
        self.assertTrue(result['files'][0]['audio'])

    def test_dash_remux(self):
        result = fetch.acquire(self.args(self.url + '/manifest.mpd'))
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['files'][0]['video'])
        self.assertTrue(result['files'][0]['audio'])

    def test_silent_video_is_valid_with_explicit_warning(self):
        result = fetch.acquire(self.args(str(self.root / 'silent.mp4')))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['files'][0]['audio'], [])
        self.assertTrue(any('No audio' in warning for warning in result['warnings']))

    def test_required_audio_missing_is_validation_failure(self):
        def download(source, folder, args, headers):
            shutil.copy(self.root / 'silent.mp4', folder / 'media.mp4')
        with patch.object(fetch, 'extract_info', return_value={'duration': 2, 'acodec': 'aac'}), patch.object(fetch, 'download_ytdlp', side_effect=download):
            result = fetch.acquire(self.args('https://example.test/watch'))
        self.assertEqual(result['status'], 'validation_failed')


    def test_nested_iframe_download(self):
        with self.no_extractor():
            result = fetch.acquire(self.args(self.url + '/nested.html'))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['method'], 'direct')

    def test_multiple_candidates_require_selection(self):
        with self.no_extractor():
            result = fetch.acquire(self.args(self.url + '/multiple.html'))
            selected = fetch.acquire(self.args(self.url + '/multiple.html', candidate=1))
        self.assertEqual(result['status'], 'selection_required')
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(selected['status'], 'complete')

    def test_blob_requires_browser_not_fake_success(self):
        with self.no_extractor():
            result = fetch.acquire(self.args(self.url + '/dynamic.html'))
        self.assertEqual(result['status'], 'browser_required')
        self.assertEqual(result['files'], [])

    def test_browser_handoff_secret_and_permissions(self):
        candidates = Path(self.out.name) / 'input.private.json'
        candidates.write_text(json.dumps([{'url': self.url + '/clip.mp4?token=SECRET', 'kind': 'media', 'page': self.url + '/dynamic.html'}]))
        result = fetch.acquire(self.args(self.url + '/dynamic.html', candidates_file=str(candidates)))
        self.assertEqual(result['status'], 'complete')
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(Path(result['manifest_path']).stat().st_mode & 0o777, 0o600)

    def test_html_disguised_as_video_fails(self):
        result = fetch.acquire(self.args(self.url + '/fake.mp4'))
        self.assertEqual(result['status'], 'validation_failed')
        self.assertEqual(result['files'], [])

    def test_quick_is_partial(self):
        result = fetch.acquire(self.args(str(self.media), quick=True))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['files'][0]['decode_check'], 'probe_only')

    def test_audio_extraction(self):
        result = fetch.acquire(self.args(str(self.media), mode='audio'))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['files'][0]['kind'], 'audio')
        self.assertEqual(result['files'][0]['video'], [])

    def test_mismatched_platform_duration_is_partial(self):
        def download(source, folder, args, headers):
            shutil.copy(self.media, folder / 'media.mp4')
        with patch.object(fetch, 'extract_info', return_value={'duration': 200, 'acodec': 'aac'}), patch.object(fetch, 'download_ytdlp', side_effect=download):
            result = fetch.acquire(self.args('https://example.test/watch'))
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['files'][0]['duration_matches_source'])

    def test_platform_subtitle_handoff(self):
        def download(source, folder, args, headers):
            shutil.copy(self.media, folder / 'media.mp4')
            (folder / 'media.zh.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:01.000\n你好\n')
        with patch.object(fetch, 'extract_info', return_value={'duration': 2, 'acodec': 'aac', 'title': '课程'}), patch.object(fetch, 'download_ytdlp', side_effect=download):
            result = fetch.acquire(self.args('https://example.test/watch'))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([f['kind'] for f in result['files']], ['video', 'subtitle'])

    def test_invalid_candidates_rejected(self):
        candidates = Path(self.out.name) / 'input.private.json'
        candidates.write_text('[{"url":"file:///etc/passwd"}]')
        result = fetch.acquire(self.args(self.url + '/dynamic.html', candidates_file=str(candidates)))
        self.assertEqual(result['status'], 'invalid_input')

    def test_drm_stops_without_static_fallback(self):
        with patch.object(fetch, 'extract_info', side_effect=fetch.FetchError('unsupported_drm', 'protected')), patch.object(fetch, 'discover') as discovery:
            result = fetch.acquire(self.args('https://example.test/watch'))
        self.assertEqual(result['status'], 'unsupported_drm')
        discovery.assert_not_called()


class FetchUnit(unittest.TestCase):
    def test_cross_origin_redirect_does_not_forward_credentials(self):
        request = fetch.urllib.request.Request('https://example.test/file', headers={'Cookie': 'secret', 'Authorization': 'Bearer secret', 'X-Api-Key': 'secret', 'User-Agent': 'test'})
        redirected = fetch.ScopedRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://cdn.test/file')
        self.assertEqual(redirected.get_header('User-agent'), 'test')
        self.assertFalse(any('secret' in v for v in redirected.headers.values()))

    def test_auto_subtitles_keep_original_not_all_translations(self):
        selector = fetch.subtitle_selection({'subtitles': {'ja': [], 'live_chat': []}, 'automatic_captions': {'en-orig': [], 'en': [], 'ab-en': []}}, 'auto')
        self.assertEqual(selector, 'en-orig,ja')

    def test_subtitle_failure_does_not_discard_video(self):
        args = argparse.Namespace(cookies_browser=None, referer=None, mode='video', quality='best', langs='en', timeout=30)
        with tempfile.TemporaryDirectory() as root, patch.object(fetch, 'run', side_effect=[subprocess.CompletedProcess([], 0, '', ''), subprocess.CompletedProcess([], 1, '', '429')]) as calls:
            warning = fetch.download_ytdlp('https://example.test/watch', Path(root), args, {})
        self.assertIn('subtitles', warning)
        self.assertNotIn('--write-subs', calls.call_args_list[0].args[0])
        self.assertIn('--write-subs', calls.call_args_list[1].args[0])

    def test_interrupted_file_resumes_with_validator(self):
        payload = b'example-media-bytes'

        class Response:
            def __init__(self, data, status, fail=False):
                self.body = io.BytesIO(data)
                self.status, self.fail, self.calls = status, fail, 0
                self.headers = Message()
                self.headers['Content-Type'] = 'video/mp4'
                self.headers['ETag'] = '"stable"'
                self.headers['Content-Length'] = str(len(payload) if fail else len(data))
                if status == 206:
                    self.headers['Content-Range'] = f'bytes 7-{len(payload)-1}/{len(payload)}'

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self, count):
                self.calls += 1
                if self.fail and self.calls > 1:
                    raise OSError('connection interrupted')
                return self.body.read(7 if self.fail else count)

        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            with patch.object(fetch, 'open_url', return_value=Response(payload, 200, True)):
                with self.assertRaises(fetch.FetchError):
                    fetch.http_file('https://example.test/clip.mp4', folder, 30, {})
            self.assertEqual((folder / 'http.download.part').read_bytes(), payload[:7])
            with patch.object(fetch, 'open_url', return_value=Response(payload[7:], 206)) as request:
                final = fetch.http_file('https://example.test/clip.mp4', folder, 30, {})
            self.assertEqual(request.call_args.args[0].get_header('Range'), 'bytes=7-')
            self.assertEqual(request.call_args.args[0].get_header('If-range'), '"stable"')
            self.assertEqual(final.read_bytes(), payload)

    def test_player_alternative_sources_are_one_video(self):
        parser = fetch.EmbeddedMedia()
        parser.feed('<video><source src="a.mp4"><source src="a.webm"></video><video src="b.mp4"></video>')
        self.assertEqual(parser.media, ['a.mp4', 'b.mp4'])

    def test_format_selection_uses_expression(self):
        self.assertEqual(fetch.format_selection('best'), 'bv*+ba/b')
        self.assertIn('height<=1080', fetch.format_selection('1080p'))

    def test_metadata_strips_nested_signed_urls(self):
        result = fetch.public_metadata({'chapters': [{'title': 'A', 'start_time': 0, 'end_time': 2, 'thumbnail': 'https://x/?token=secret'}]})
        self.assertNotIn('secret', json.dumps(result))

    def test_secret_tool_stderr_not_exported(self):
        with patch.object(fetch, 'run', return_value=subprocess.CompletedProcess([], 1, '', '403 https://x/?token=SECRET')):
            with self.assertRaises(fetch.FetchError) as context:
                fetch.tool_json(['anything'])
        self.assertEqual(context.exception.status, 'access_required')
        self.assertNotIn('SECRET', str(context.exception))

    def test_lock_does_not_remove_other_owner(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / '.lock').write_text('another owner')
            with self.assertRaises(fetch.FetchError):
                with fetch.job_lock(folder):
                    pass
            self.assertEqual((folder / '.lock').read_text(), 'another owner')


if __name__ == '__main__':
    unittest.main()
