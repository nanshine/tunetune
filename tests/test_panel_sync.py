"""The panel's state stays cheap to poll and trial pictures stay panel scratch."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "plugins" / "tunetune" / "skills" / "research-workspace" / "scripts" / "workspace.py"
SPEC = importlib.util.spec_from_file_location('sync_workspace', SOURCE)
wb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wb)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class PanelSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'project'
        self.assets = self.base / 'assets'
        self.root.mkdir()
        self.assets.mkdir()
        (self.assets / 'index.html').write_text('<title>Research</title>')
        self.write('project.json', {'name': 'Sync', 'deliveries': []})
        self.server = wb.make_server(self.root, self.assets)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else json.dumps(content), encoding='utf-8')
        return target

    def request(self, method, path, body=None, headers=None):
        port = self.server.server_address[1]
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(method, path, body=body, headers={'Origin': f'http://127.0.0.1:{port}', **(headers or {})})
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else None

    def state(self, since=None):
        return self.request('GET', '/api/state' + (f'?since={since}' if since else ''))

    def test_an_unchanged_revision_is_answered_without_the_records(self):
        status, full = self.state()
        self.assertEqual(status, 200)
        self.assertIn('project.json', full['files'])
        status, light = self.state(full['revision'])
        self.assertEqual(status, 200)
        self.assertTrue(light['unchanged'])
        self.assertEqual(light['revision'], full['revision'])
        for key in ('files', 'paged', 'omitted'):
            self.assertNotIn(key, light)
        for key in ('observations', 'view', 'acceptance', 'models'):
            self.assertIn(key, light)
        # Any change, even one keeping the size, sends the records again.
        self.write('project.json', {'name': 'Snyc', 'deliveries': []})
        status, changed = self.state(full['revision'])
        self.assertNotIn('unchanged', changed)
        self.assertEqual(changed['files']['project.json']['content']['name'], 'Snyc')
        self.assertNotEqual(changed['revision'], full['revision'])
        for bad in ('?since=abc', f"?since={full['revision']}&since={full['revision']}", '?other=1'):
            self.assertEqual(self.request('GET', '/api/state' + bad)[0], 400)

    def test_a_large_sample_file_is_paged_instead_of_resent_with_every_poll(self):
        rows = ''.join(json.dumps({'sample_id': f's{i}', 'input': 'x' * 200, 'reference': 'y'}) + '\n' for i in range(6000))
        self.assertGreater(len(rows), wb.MAX_INLINE_ROWS_BYTES)
        self.assertLess(len(rows), wb.MAX_FILE_BYTES)
        self.write('evaluation/v1/samples.jsonl', rows)
        self.write('evaluation/v1/small.jsonl', '')
        self.write('comparison/inputs.jsonl', json.dumps({'sample_id': 'a', 'input': 'x'}) + '\n')
        _, state = self.state()
        self.assertNotIn('evaluation/v1/samples.jsonl', state['files'])
        self.assertEqual(state['paged']['evaluation/v1/samples.jsonl']['rows'], 6000)
        self.assertIn('comparison/inputs.jsonl', state['files'])

    def test_cached_records_follow_rewrites(self):
        reader = wb.Reader(self.root)
        first = reader.snapshot()
        self.assertIs(reader.snapshot()['files']['project.json'], first['files']['project.json'])
        path = self.write('project.json', {'name': 'Next', 'deliveries': []})
        os.utime(path, ns=(0, 0))
        self.assertEqual(reader.snapshot()['files']['project.json']['content']['name'], 'Next')
        path.unlink()
        self.assertIn('project.json', reader.snapshot()['error'])

    def upload(self, data, kind='image', ext='png', **headers):
        return self.request('POST', f'/api/try/media?kind={kind}&ext={ext}', data, {'Content-Type': 'application/octet-stream', **headers})

    def test_trial_attachments_are_checked_named_by_content_and_kept_as_scratch(self):
        status, answer = self.upload(PNG)
        self.assertEqual(status, 200)
        self.assertEqual(answer['type'], 'image')
        self.assertRegex(answer['path'], r'^\.workspace/runtime/trial-[0-9a-f]{32}\.png$')
        self.assertEqual((self.root / answer['path']).read_bytes(), PNG)
        self.assertEqual(self.upload(PNG)[1], answer)
        samples = {('audio', 'wav'): b'RIFF\x00\x00\x00\x00WAVEfmt ' + b'\x00' * 16, ('audio', 'mp3'): b'ID3\x04' + b'\x00' * 20,
                   ('audio', 'flac'): b'fLaC' + b'\x00' * 20, ('video', 'mp4'): b'\x00\x00\x00\x18ftypisom' + b'\x00' * 16,
                   ('video', 'webm'): b'\x1a\x45\xdf\xa3' + b'\x00' * 20, ('file', 'pdf'): b'%PDF-1.7 anything', ('file', 'glb'): b'x'}
        for (kind, ext), data in samples.items():
            with self.subTest(kind=kind, ext=ext):
                status, answer = self.upload(data, kind, ext)
                self.assertEqual(status, 200)
                self.assertEqual(answer['type'], kind)
                self.assertTrue(answer['path'].endswith('.' + ext))
        # Content is checked against its declared format, and each kind accepts only its own formats.
        for kind, ext, data in (('image', 'jpg', PNG), ('audio', 'wav', PNG), ('video', 'mp4', b'RIFF....WAVE' + b'\x00' * 8),
                                ('image', 'svg', b'<svg/>'), ('audio', 'mp4', PNG), ('file', 'p.df', b'x'), ('file', '', b'x')):
            with self.subTest(refused=(kind, ext)):
                self.assertEqual(self.upload(data, kind, ext)[0], 415)
        self.assertEqual(self.request('POST', '/api/try/media?kind=model&ext=bin', b'x', {})[0], 400)
        self.assertEqual(self.request('POST', '/api/try/media?kind=image', PNG, {})[0], 400)
        self.assertEqual(self.upload(PNG, Origin='http://evil.test')[0], 403)
        self.assertEqual([name for name in os.listdir(self.root / '.workspace' / 'runtime') if name.endswith('.part')], [])
        # A trial attachment is never served as research media.
        self.assertEqual(self.request('GET', '/api/media?path=' + answer['path'])[0], 404)

    def test_trial_attachment_size_is_limited_by_kind(self):
        port = self.server.server_address[1]
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest('POST', '/api/try/media?kind=image&ext=png')
        connection.putheader('Origin', f'http://127.0.0.1:{port}')
        connection.putheader('Content-Length', str(wb.TRIAL_LIMITS['image'] + 1))
        connection.endheaders()
        self.assertEqual(connection.getresponse().status, 413)

    def test_old_trial_attachments_are_pruned(self):
        for index in range(wb.KEEP_TRIAL_MEDIA + 5):
            status, _ = self.upload(PNG + index.to_bytes(4, 'big'))
            self.assertEqual(status, 200)
        kept = [name for name in os.listdir(self.root / '.workspace' / 'runtime') if name.startswith('trial-')]
        self.assertEqual(len(kept), wb.KEEP_TRIAL_MEDIA)


if __name__ == '__main__':
    unittest.main()
