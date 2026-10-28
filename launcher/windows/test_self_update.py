"""The Windows launcher's own update (self_update.py), against a stand-in for
GitHub on this PC. Nothing is run that needs Windows."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
import hashlib
import json
import os
import struct
import tempfile
import threading
import unittest

import self_update
from self_update import Cancelled, UpdateError, compare_versions, parse_release, version_in

def fake_exe(body=b'', files=True):
    """A 64-bit Windows program's header, then `body`, then a trailer when `files`."""
    head = bytearray(0x80); head[:2] = b'MZ'; struct.pack_into('<I', head, 0x3C, 0x40)
    head[0x40:0x46] = b'PE\0\0\x64\x86'
    part = bytes(head) + body
    return part + (self_update.TRAILER.pack(0, 0, bytes(32), self_update.MAGIC) if files else b'')

class Release(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(compare_versions('v0.3.1', '0.3.1'), 0)
        self.assertEqual(compare_versions('0.3', '0.3.0'), 0)
        self.assertLess(compare_versions('0.3.1', '0.10.0'), 0)
        self.assertGreater(compare_versions('1.0', '0.99.9'), 0)
        self.assertIsNone(compare_versions('0.3-beta', '0.3'))
        self.assertIsNone(compare_versions('', '0.3'))
        self.assertEqual(self_update.version(), self_update.version(self_update.ROOT))
    def test_exe_of_newest_release(self):
        assets = [dict(name='Ultimate_Launcher-x86_64.AppImage', browser_download_url='https://x/a', size=5),
                  dict(name='Ultimate_Launcher-x86_64.exe', browser_download_url='https://x/e', size=7,
                       digest='sha256:' + 'A' * 64)]
        answer = parse_release(json.dumps(dict(tag_name='v0.4.0', html_url='https://x/r', assets=assets)))
        self.assertEqual((answer.release.version, answer.release.url, answer.release.size, answer.release.sha256),
                         ('0.4.0', 'https://x/e', 7, 'a' * 64))
        plain = parse_release(json.dumps(dict(tag_name='0.4', assets=[dict(name='Launcher.exe', browser_download_url='u')])))
        self.assertEqual(plain.release.asset, 'Launcher.exe')
        two = [dict(name='a.exe', browser_download_url='u'), dict(name='b.exe', browser_download_url='u')]
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=two))).error)
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=assets[:1]))).error)
        uploading = [dict(assets[1], state='starter')]
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=uploading))).error)
    def test_github_errors(self):
        self.assertTrue(parse_release('{"message": "Not Found"}').none)
        self.assertIn('try again later', parse_release('{"message": "API rate limit exceeded for 1.2.3.4"}').error)
        self.assertIn('not named as a version', parse_release('{"tag_name": "latest"}').error)
        self.assertIn('not readable', parse_release('<html>').error)
    def test_launcher_exe_and_its_version(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'a.exe'
            exe.write_bytes(fake_exe(b'program')); self.assertTrue(self_update.is_launcher_exe(exe))
            exe.write_bytes(fake_exe(b'program', files=False)); self.assertFalse(self_update.is_launcher_exe(exe))
            exe.write_bytes(b'<html>not found</html>'); self.assertFalse(self_update.is_launcher_exe(exe))
        self.assertEqual(version_in('ttt2-launcher 0.4.0\r\n'), '0.4.0')
        self.assertEqual(version_in('Python 3.13'), '')

class GitHub(BaseHTTPRequestHandler):
    """The release (`answer`) and its .exe (`files`), as GitHub gives them."""
    answer, status, files = b'', 200, {}
    def do_GET(self):
        body, status = (self.answer, self.status) if self.path == '/latest' else (self.files.get(self.path), 200)
        if body is None: body, status = b'{"message": "Not Found"}', 404
        self.send_response(status); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass

class Update(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.exe = self.folder / 'Ultimate_Launcher-x86_64.exe'; self.exe.write_bytes(fake_exe(b'old'))
        self.new = fake_exe(b'new' * 100000)
        handler = type('Handler', (GitHub,), dict(files={'/new.exe': self.new}))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler); self.handler = handler
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        environment = mock.patch.dict(os.environ, TTT2_LAUNCHER_RELEASES=self.base + '/latest'); environment.start()
        self.addCleanup(environment.stop)
        self.lines = []
    def release(self, version='99.0.0', sha256=None, size=None, status=200):
        asset = dict(name='Ultimate_Launcher-x86_64.exe', browser_download_url=self.base + '/new.exe',
                     size=len(self.new) if size is None else size,
                     digest='sha256:' + (sha256 or hashlib.sha256(self.new).hexdigest()))
        self.handler.answer = json.dumps(dict(tag_name='v' + version, html_url=self.base, assets=[asset])).encode()
        self.handler.status = status
    def update(self, said='99.0.0', cancelled=lambda: False):
        with mock.patch.object(self_update, 'said_version', return_value=(0, said)):
            return self_update.update(self.exe, cancelled, self.lines.append)
    def assertUnchanged(self):
        self.assertEqual(self.exe.read_bytes(), fake_exe(b'old'))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), [self.exe.name])
    def test_newer_release_replaces_exe(self):
        self.release()
        self.assertEqual(self.update(), '99.0.0')
        self.assertEqual(self.exe.read_bytes(), self.new)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), [self.exe.name])
        self.assertIn('@launcher-updated 99.0.0', self.lines)
        self.assertTrue(any(line.startswith('@progress ') for line in self.lines))
    def test_newest_already(self):
        self.release(self_update.version())
        self.assertIsNone(self.update()); self.assertUnchanged()
        self.handler.answer, self.handler.status = b'{"message": "Not Found"}', 404
        self.assertIsNone(self.update()); self.assertUnchanged()
    def test_damaged_or_wrong_download_changes_nothing(self):
        for release, said, why in [(dict(sha256='0' * 64), '99.0.0', 'damaged'),
                                   (dict(size=len(self.new) + 1), '99.0.0', 'incomplete'),
                                   ({}, '98.0.0', 'is version 98.0.0'),
                                   ({}, '', 'does not start')]:
            with self.subTest(why):
                self.release(**release)
                with self.assertRaisesRegex(UpdateError, why): self.update(said)
                self.assertUnchanged()
        self.handler.files = {'/new.exe': b'<html>'}; self.release(sha256=hashlib.sha256(b'<html>').hexdigest(), size=6)
        with self.assertRaisesRegex(UpdateError, 'not a Windows launcher'): self.update()
        self.assertUnchanged()
    def test_cancel_and_failures_leave_exe(self):
        self.release()
        with self.assertRaises(Cancelled): self.update(cancelled=lambda: True)
        self.assertUnchanged()
        self.handler.answer, self.handler.status = b'{"message": "API rate limit exceeded"}', 403
        with self.assertRaisesRegex(UpdateError, 'try again later'): self.update()
        with mock.patch.dict(os.environ, TTT2_LAUNCHER_RELEASES='http://127.0.0.1:9/latest'):
            with self.assertRaisesRegex(UpdateError, 'GitHub cannot be reached'): self.update()
        self.assertUnchanged()
    def test_old_exe_back_when_new_cannot_take_its_place(self):
        update = self_update.update_file(self.exe); update.write_bytes(self.new)
        real = os.replace
        def refuse(source, target):
            if Path(source) == update: raise PermissionError(13, 'Access is denied')
            real(source, target)
        with mock.patch('os.replace', side_effect=refuse), self.assertRaises(PermissionError):
            self_update.replace(update, self.exe)
        self.assertEqual(self.exe.read_bytes(), fake_exe(b'old'))
        self.assertFalse(self_update.old_file(self.exe).exists())

if __name__ == '__main__': unittest.main()
