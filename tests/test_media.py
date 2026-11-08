"""Explicit research attachments stay confined to current display records."""
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import quote

SOURCE = Path(__file__).resolve().parents[1] / "plugins" / "tunetune" / "skills" / "research-workspace" / "scripts" / "workspace.py"
SPEC = importlib.util.spec_from_file_location('media_workspace', SOURCE)
wb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wb)


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'project'
        self.assets = self.base / 'assets'
        self.root.mkdir()
        self.assets.mkdir()
        (self.assets / 'index.html').write_text('<title>Research</title>')
        self.write('project.json', {'name': 'Media', 'deliveries': []})
        self.server = wb.make_server(self.root, self.assets)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            target.write_text(json.dumps(content), encoding='utf-8')
        else:
            target.write_bytes(content)
        return target

    def request(self, path):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        self.addCleanup(connection.close)
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())

    def media(self, path):
        return self.request('/api/media?path=' + quote(path, safe=''))

    def reference(self, *references):
        self.write('proposal.json', {'summary': '', 'examples': [{'input': list(references)}]})

    def test_only_explicit_references_authorize_supported_media(self):
        cases = [('image', 'data/中文 image.png', b'\x89PNG\r\n\x1a\n', 'image/png'),
                 ('audio', 'data/sample.wav', b'RIFF audio', 'audio/wav'),
                 ('video', 'data/sample.mp4', b'video', 'video/mp4'),
                 ('file', 'data/object.glb', b'glTF', 'application/octet-stream')]
        for kind, path, content, mime in cases:
            with self.subTest(kind=kind):
                self.write(path, content)
                self.assertEqual(self.media(path)[0], 404)
                self.reference({'type': kind, 'path': path})
                status, actual, headers = self.media(path)
                self.assertEqual(status, 200)
                self.assertEqual(actual, content)
                self.assertEqual(headers['Content-Type'], mime)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_active_content_extensions_are_never_exposed(self):
        for suffix in ('svg', 'html', 'js', 'pdf', 'pem'):
            path = 'data/file.' + suffix
            self.write(path, b'<script>unsafe()</script>')
            self.reference({'type': 'file', 'path': path})
            self.assertEqual(self.media(path)[0], 404)

    def test_paths_cannot_escape_or_reach_hidden_files(self):
        (self.base / 'outside.png').write_bytes(b'private')
        self.write('data/.hidden.png', b'private')
        self.write('.private/file.png', b'private')
        for path in ('../outside.png', str(self.base / 'outside.png'), 'data/.hidden.png',
                     '.private/file.png', 'data/../outside.png', 'data\\outside.png'):
            self.reference({'type': 'image', 'path': path})
            self.assertEqual(self.media(path)[0], 404, path)

    def test_file_and_parent_symlinks_are_not_followed(self):
        target = self.base / 'private.png'
        target.write_bytes(b'private')
        (self.root / 'link.png').symlink_to(target)
        (self.root / 'linked').symlink_to(self.base, target_is_directory=True)
        for path in ('link.png', 'linked/private.png'):
            self.reference({'type': 'image', 'path': path})
            self.assertEqual(self.media(path)[0], 404)

    def test_invalid_current_snapshot_never_serves_a_stale_reference(self):
        path = 'data/image.png'
        self.write(path, b'image')
        self.reference({'type': 'image', 'path': path})
        self.assertEqual(self.media(path)[0], 200)
        self.write('proposal.json', b'{broken')
        self.assertEqual(self.media(path)[0], 404)
        self.reference({'type': 'image', 'path': path})
        self.assertEqual(self.media(path)[0], 200)
        self.reference()
        self.assertEqual(self.media(path)[0], 404)

    def test_non_displayed_metadata_does_not_authorize_media(self):
        path = 'private/image.png'
        self.write(path, b'private')
        self.write('proposal.json', {'summary': '', 'examples': [],
                                     'metadata': {'type': 'image', 'path': path}})
        self.assertEqual(self.media(path)[0], 404)
        self.write('proposal.json', {'summary': '', 'examples': [{'input': 'text', 'metadata': {'type': 'image', 'path': path}}]})
        self.assertEqual(self.media(path)[0], 404)
        self.write('experiments/e/config.json', {'parameters': {'type': 'image', 'path': path}})
        self.assertEqual(self.media(path)[0], 404)

    def test_unrendered_deep_reference_is_not_shared(self):
        path = 'private/deep.png'
        self.write(path, b'private')
        value = {'type': 'image', 'path': path}
        for _ in range(20):
            value = {'nested': value}
        self.reference(value)
        self.assertEqual(self.media(path)[0], 404)

    def test_wrong_or_ambiguous_queries_fail_closed(self):
        path = 'data/image.png'
        self.write(path, b'image')
        self.reference({'type': 'image', 'path': path})
        for query in ('', '?path=', '?file=data%2Fimage.png', '?path=data%2Fimage.png&path=data%2Fimage.png',
                      '?path=data%2Fimage.png&other=1', '?path=data%252Fimage.png'):
            self.assertEqual(self.request('/api/media' + query)[0], 404)

    def test_document_policy_allows_only_same_origin_media_and_no_frames(self):
        status, _, headers = self.request('/')
        self.assertEqual(status, 200)
        policy = headers['Content-Security-Policy']
        self.assertIn("media-src 'self' blob:;", policy)
        # Only page-made blob: URLs are added, so a picked trial file can be previewed before upload.
        self.assertIn("img-src 'self' data: blob:;", policy)
        self.assertNotIn("script-src 'self' blob:", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn('https:', policy)


if __name__ == '__main__':
    unittest.main()
