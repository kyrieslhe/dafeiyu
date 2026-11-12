import io
import json
import tempfile
import unittest
from unittest.mock import patch

from dafeiyu.core import Fish, ModelError
from dafeiyu.youtube import canonical, description, _read, page_source, LIMIT

URL = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'


def body(status='OK', identifier='jNQXAC9IVRw'):
    return '<script>var ytInitialPlayerResponse = ' + json.dumps({
        'playabilityStatus': {'status': status},
        'videoDetails': {'videoId': identifier, 'title': 'Fixture', 'author': 'Creator', 'shortDescription': 'Public description'},
        'streamingData': {'private_url': 'must not reach model'},
    }) + ';</script>'


class YouTube(unittest.TestCase):
    def test_canonical_removes_tracking_and_rejects_non_video_urls(self):
        for url in (URL+'&feature=share', 'https://youtu.be/jNQXAC9IVRw?si=tracking',
                    'https://m.youtube.com/shorts/jNQXAC9IVRw', 'https://youtube.com/embed/jNQXAC9IVRw'):
            self.assertEqual(canonical(url), URL)
        for url in ('http://youtu.be/jNQXAC9IVRw', 'https://youtube.com.evil.test/watch?v=jNQXAC9IVRw',
                    'https://user@youtube.com/watch?v=jNQXAC9IVRw', 'https://youtube.com/account',
                    URL+'&v=abcdefghijk', 'https://youtu.be/jNQXAC9IVRw/extra', URL.replace('www.', 'www.:444/')):
            with self.assertRaises(ValueError):canonical(url)

    def test_parser_checks_identity_and_access_and_discards_playback_data(self):
        result = description(body(), URL)
        self.assertIn('Public description', result['text'])
        self.assertNotIn('must not reach model', json.dumps(result))
        self.assertEqual(result['method'], 'public_metadata_only')
        self.assertFalse(result['complete_video_view'])
        for value in (body('LOGIN_REQUIRED'), body('UNPLAYABLE'), body(identifier='abcdefghijk'), '<script>broken</script>'):
            with self.assertRaises(ModelError):description(value, URL)

    def test_bounded_single_get_never_follows_login_redirect(self):
        from urllib.parse import urlsplit
        class Response(io.BytesIO):
            status = 200
            def getheader(self, key, default=None):return 'text/html' if key == 'Content-Type' else default
        response = Response(body().encode())
        connection = unittest.mock.Mock()
        connection.getresponse.return_value = response
        with patch('dafeiyu.research.target', return_value=(urlsplit(URL), '1.1.1.1')), patch('dafeiyu.research.PinnedHTTPS', return_value=connection):
            self.assertEqual(_read(URL)['title'], 'Fixture')
            headers = connection.request.call_args.kwargs['headers']
            self.assertNotIn('Cookie', headers);self.assertNotIn('Authorization', headers)
            for status, data in ((302, b''), (200, b'x'*(LIMIT+1))):
                response = Response(data);response.status = status;connection.getresponse.return_value = response
                with self.assertRaises(ModelError):_read(URL)
        self.assertTrue(response.closed)

    def test_cancelled_read_never_launches_process(self):
        with patch('dafeiyu.youtube.subprocess.run') as launch:
            with self.assertRaises(ModelError):page_source(URL, lambda: True)
            launch.assert_not_called()

    def test_manual_discovery_validates_results_and_never_samples_video(self):
        class Backend:
            ready = True
            def search(self, messages):self.query = messages;return 'https://youtube.com/account '+URL
            def reply(self, messages):self.messages = messages;return '本鱼读到作者的简介。'
        with tempfile.TemporaryDirectory() as home:
            model = Backend();fish = Fish(home, model);self.addCleanup(fish.close)
            with patch('dafeiyu.youtube.page_source', return_value=description(body(), URL)), patch('dafeiyu.watching.sampled') as sample:
                from dafeiyu.platforms import read
                report, metadata = read(fish, 'youtube', '动物', 'manual-test')
                sample.assert_not_called()
            self.assertIn('watch?v=', str(model.query));self.assertIn('没有播放', str(model.messages))
            self.assertEqual(metadata['scope'], 'text_only_not_video');self.assertIn(URL, report)
            self.assertFalse(metadata['complete_video_view'])

    def test_natural_request_and_command_enqueue_youtube_without_io(self):
        from dafeiyu.actions import execute
        with tempfile.TemporaryDirectory() as home:
            fish = Fish(home);self.addCleanup(fish.close)
            execute(fish, '去 YouTube 找个有趣的视频', {}, 'browse', '动物', True)
            self.assertEqual(fish.command('/tasks')[0]['kind'], 'platform')
            goal = fish.db.execute('SELECT goal FROM tasks').fetchone()[0]
            self.assertEqual(goal, 'youtube 动物')
