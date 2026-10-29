"""First-run setup regressions; all fixtures are synthetic and asset-free."""
from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest import mock
import zipfile
from backend import Settings
from setup_game import download, unzip, verified_rpx, setup, validate_setup_paths

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

class PathPreflight(unittest.TestCase):
    def settings(self, root='D:/TTT2', tools='D:/TTT2/local/windows-tools'):
        from types import SimpleNamespace
        return SimpleNamespace(root=root, values={'tools':tools})
    def test_short_project_and_tools_are_accepted(self):
        validate_setup_paths(self.settings())
    def test_reported_nested_project_is_rejected_with_user_instructions(self):
        root='D:/Nuova cartella/' + 'Tekken-Tag-2-Ultimate-Edition-codex-native-windows-t7-reina(1)/' + 'Tekken-Tag-2-Ultimate-Edition-codex-native-windows-t7-reina'
        with self.assertRaisesRegex(ValueError, 'D:/TTT2'):
            validate_setup_paths(self.settings(root))
    def test_custom_tools_path_is_checked_separately(self):
        with self.assertRaisesRegex(ValueError,'tools folder path'):
            validate_setup_paths(self.settings(tools='D:/'+'x'*160))
    def test_letters_cmd_cannot_read_are_rejected(self):
        # (A tester's: CMake's batch files lost the à, "path not found".)
        root='C:/Users/Player/Desktop/Novit\u00e0/Tekken-Tag-2-Ultimate-Edition-dev-0-4-0'
        with self.assertRaisesRegex(ValueError, 'project folder path has letters .*\\(\u00e0\\).*C:/TTT2'):
            validate_setup_paths(self.settings(root, tools='C:/TTT2/local/windows-tools'))
        with self.assertRaisesRegex(ValueError, 'Windows tools folder path has letters'):
            validate_setup_paths(self.settings(tools='C:/Users/Jos\u00e9/tools'))
    def test_install_folder_the_installer_cannot_be_given(self):
        settings=self.settings(); settings.values.update(install='C:/\u6e38\u620f', source='C:/TTT2.wua')
        with self.assertRaisesRegex(ValueError, 'installation folder path has letters'):
            validate_setup_paths(settings)
        settings.values['install']='C:/Users/Player/Desktop/Novit\u00e0/TTT2'
        validate_setup_paths(settings)
    def test_windows_utf16_length_is_used(self):
        with self.assertRaisesRegex(ValueError,'project folder path'):
            validate_setup_paths(self.settings(root='D:/'+'\U0001f600'*55))

class DependencyCheckout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        path=Path(__file__).resolve().parents[2]/'tools/setup_deps.py'
        spec=importlib.util.spec_from_file_location('dependency_setup_tested',path)
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
    def test_windows_git_gets_process_local_longpath_option(self):
        with mock.patch.object(self.module.os,'name','nt'), mock.patch.object(self.module.subprocess,'run') as run:
            self.module.git('dependency','status')
            self.assertEqual(run.call_args.args[0][:5],['git','-c','core.longpaths=true','-C','dependency'])
    def test_only_missing_files_are_restored(self):
        from types import SimpleNamespace
        with mock.patch.object(self.module.os,'name','nt'), mock.patch.object(self.module,'git',return_value=SimpleNamespace(stdout='source/missing header.h\0')) as git:
            self.module.repair_missing_windows_files('dependency')
            self.assertEqual(git.call_args_list[1].args,('dependency','restore','--source=HEAD','--worktree','--','source/missing header.h'))
    def test_linux_checkout_behavior_is_unchanged(self):
        with mock.patch.object(self.module.os,'name','posix'), mock.patch.object(self.module,'git') as git:
            self.module.repair_missing_windows_files('dependency')
            git.assert_not_called()

if __name__=='__main__':unittest.main()
