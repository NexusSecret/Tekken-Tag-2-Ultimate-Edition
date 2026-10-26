"""First-run setup regressions; all fixtures are synthetic and asset-free."""
from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest import mock
import zipfile
from backend import Settings
from setup_game import download, unzip, verified_rpx, setup

class FirstRun(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_checked_download_and_corrupt_cache_repair(self):
        source=self.root/'source';source.write_bytes(b'verified runtime')
        asset=dict(url=source.as_uri(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        out=self.root/'cache/runtime';out.parent.mkdir();out.write_bytes(b'interrupted')
        self.assertEqual(download(asset,out).read_bytes(),source.read_bytes())
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('cache should be reused')):
            self.assertEqual(download(asset,out),out)
    def test_hash_failure_never_replaces_cached_file(self):
        source=self.root/'source';source.write_bytes(b'bad bytes')
        out=self.root/'cache';out.write_bytes(b'previous')
        with self.assertRaisesRegex(ValueError,'checksum'):
            download(dict(url=source.as_uri(),sha256='0'*64),out)
        self.assertEqual(out.read_bytes(),b'previous')
    def test_downloaded_zip_cannot_escape_tools_folder(self):
        archive=self.root/'test.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.exe',b'bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            unzip(archive,self.root/'tools')
        self.assertFalse((self.root/'escape.exe').exists())
    def test_valid_tool_zip_extracts(self):
        archive=self.root/'test.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('bin/tool.exe',b'fake')
        unzip(archive,self.root/'tools')
        self.assertEqual((self.root/'tools/bin/tool.exe').read_bytes(),b'fake')
    def test_only_matching_game_revision_is_selected(self):
        wrong=self.root/'base/code/Tekken.rpx';wrong.parent.mkdir(parents=True);wrong.write_bytes(b'base')
        right=self.root/'update/code/Tekken.rpx';right.parent.mkdir(parents=True);right.write_bytes(b'update')
        expected=hashlib.sha256(b'update').hexdigest()
        self.assertEqual(verified_rpx(self.root,expected),right)
        with self.assertRaisesRegex(ValueError,'v16'):verified_rpx(self.root,'0'*64)
    def test_missing_inputs_stop_before_downloading_tools(self):
        settings=Settings(self.root/'build-windows-tools',self.root/'config.json',self.root)
        settings.values.update(source='',title='',install='')
        with mock.patch('setup_game.ensure_tools') as tools:
            with self.assertRaises(ValueError):setup(settings,mock.Mock())
            tools.assert_not_called()

if __name__=='__main__':unittest.main()
