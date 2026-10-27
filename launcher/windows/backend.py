"""Windows launcher backend; GTK/Linux code and character conversion stay shared."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix('.part')
    part.write_text(json.dumps(value, indent=2), encoding='utf-8')
    part.replace(path)

class Settings:
    def __init__(self, build=None, file=None, root=ROOT):
        self.root = Path(root).resolve()
        self.build = Path(build or self.root / 'build-windows-tools').resolve()
        local = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'TTT2Ultimate'
        self.file = Path(file or (self.root / 'local/windows-launcher.json' if (self.root / 'local').is_dir() else local / 'launcher.json'))
        data = self.root / 'local/windows-userdata/TTT2Ultimate'
        if not data.exists(): data = local
        def first(path):
            return path.read_text(encoding='utf-8').splitlines()[0] if path.is_file() and path.stat().st_size else ''
        tools = ''
        cache = self.build / 'CMakeCache.txt'
        if cache.exists():
            for line in cache.read_text(encoding='utf-8').splitlines():
                if line.startswith('CMAKE_CXX_COMPILER:') and '=' in line:
                    tools = str(Path(line.split('=', 1)[1]).parent.parent.parent)
        title = self.root / 'local/wua-game/0000000000000000_v0'
        saves = self.root / 'local/windows-save'
        self.values = dict(source=first(self.build / 'ttt2-game.txt'), title=str(title) if title.exists() else '',
                           install=first(local / 'installed'), data=str(data), packs=str(data / 'characters'),
                           saves=str(saves if saves.exists() else data / 'save'), tools=tools or str(self.root / 'local/windows-tools'))
        if self.file.exists(): self.values.update(json.loads(self.file.read_text(encoding='utf-8')))

    def save(self):
        if Path(self.values['data']).name != 'TTT2Ultimate':
            raise ValueError('The data folder must end in TTT2Ultimate so runtime settings use the same location.')
        for key in ('data', 'packs', 'saves'):
            if not Path(self.values[key]).is_absolute(): raise ValueError(key + ' must be an absolute path')
        write_json(self.file, self.values)

    def environment(self):
        env = dict(os.environ, TTT2_DATA_DIR=self.values['data'], TTT2_CHARACTERS=self.values['packs'],
                   TTT2_SAVE_DIR=self.values['saves'], PYTHONUTF8='1', PYTHONUNBUFFERED='1')
        env['PYTHONPATH'] = os.pathsep.join([str(self.root / 'local/windows-python'), str(Path(self.values['tools']) / 'python'), env.get('PYTHONPATH', '')])
        compiler = Path(self.values['tools']) / 'llvm-mingw-20261020-ucrt-x86_64/bin/clang.exe'
        if compiler.exists():
            env['TTT2_HELPER_CC'] = str(compiler)
            env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
        data = Path(self.values['data'])
        if data.name == 'TTT2Ultimate': env['LOCALAPPDATA'] = str(data.parent)
        return env

    def installed(self):
        folder = Path(self.values['install']) if self.values['install'] else None
        return folder if folder and (folder / '.ttt2-install').is_file() else None

    def game_command(self):
        folder = self.installed()
        if folder:
            exe = folder / 'TTT2 Ultimate.exe'
            if not exe.is_file(): raise ValueError('Installed game executable is missing. Build and update it first.')
            return [str(exe)]
        exe = self.build / 'ttt2-ultimate.exe'
        game = self.values['source'] or self.values['title']
        if not exe.is_file() or not game or not Path(game).exists():
            raise ValueError('Choose your Wii U source and build the Windows game first.')
        return [str(exe), game]

    def title(self):
        installed = self.installed()
        title = installed / 'game' if installed else Path(self.values['title'])
        if not (title / 'code/Tekken.rpx').is_file() or not (title / 'content/hdd/data000.ofs').is_file():
            raise ValueError('Choose an extracted title containing code/Tekken.rpx and content/hdd/data000.ofs, '
                             'or install your .wua first.')
        return title

    def installer_command(self, update=False):
        exe = self.build / 'ttt2-ultimate.exe'
        if not exe.is_file(): raise ValueError('Build the Windows game first.')
        if update:
            folder = self.installed()
            if not folder: raise ValueError('Choose a complete installation before updating.')
            return [str(exe), '--update', str(folder)]
        source = self.values['source'] or self.values['title']
        if not source or not Path(source).exists() or not self.values['install']:
            raise ValueError('Choose the Wii U source and destination in Paths first.')
        return [str(exe), '--install', source, self.values['install']]

    def import_command(self, names, remove=False):
        if not names: raise ValueError('Select one or more fighters.')
        return [sys.executable, '-u', str(self.root / 'tools/characters/import_character.py'), *names,
                '--game', str(self.title()), '--out', self.values['packs'], '--progress',
                *(['--remove'] if remove else [])]


def run_command(command, settings):
    print('Starting:', subprocess.list2cmdline(command), flush=True)
    with subprocess.Popen(command, cwd=settings.root, env=settings.environment(), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                if line.startswith('@folder '):
                    settings.values['install'] = line[8:].strip(); settings.save()
            result = process.wait()
        except BaseException:
            process.terminate(); process.wait(); raise
    if result: raise RuntimeError('Task exited with code %d; see the log above.' % result)


def worker(settings, action, names):
    os.environ.update(settings.environment())
    sys.path[:0] = [str(settings.root / 'local/windows-python'), str(settings.root / 'tools/characters'), str(Path(settings.values['tools']) / 'python')]
    if action == 'setup':
        from setup_game import setup
        setup(settings, run_command)
    elif action == 'build':
        tools = Path(settings.values['tools'])
        if not (tools / 'python/cmake/data/bin/cmake.exe').is_file():
            raise ValueError('Select the Windows build tools folder in Paths first.')
        run_command(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                     str(settings.root / 'tools/build_windows_runtime.ps1'), '-ToolsRoot', str(tools)], settings)
    elif action in ('install', 'update'):
        run_command(settings.installer_command(action == 'update'), settings)
    elif action in ('import', 'remove'):
        command = settings.import_command(names, action == 'remove')
        if action == 'import':
            from ttt2char.characters import definition, game_of
            selected = [definition(name) for name in names]
            t8_fighters = [d for d in selected if game_of(d) == 'tekken8']
            if t8_fighters:
                from ttt2char.tekken8 import autodump as t8
                game = t8.find_tekken8()
                ids = [d.TEKKEN8_ID for d in t8_fighters]
                t8.dump(ids, references=[fid for fid in t8.ROSTER if fid not in ids])
                version = t8.game_version(game.game, game.library)
                for d in t8_fighters:
                    if not t8.whole(t8.saved_files(d.TEKKEN8_CODE, t8.MOVESETS, version)):
                        raise RuntimeError(d.NAME + ' extraction is incomplete; existing packs were not changed.')
        import runpy
        sys.argv = command[2:]
        runpy.run_path(command[2], run_name='__main__')
    else: raise ValueError('Unknown task: ' + action)


def fighters(settings):
    sys.path.insert(0, str(settings.root / 'tools/characters'))
    from ttt2char.characters import CHARACTERS, definition, game_of
    from ttt2char import pack
    loaded = {p['code']: p for _, p in pack.loaded(pack.installed(settings.values['packs']))}
    rows = []
    for name in CHARACTERS:
        d = definition(name); found = loaded.get(d.CODE); state = 'Not added'
        if found:
            state = 'Update available' if found['revision'] < pack.revision(d) else 'Added'
            if found.get('stand_in'): state = 'Stand-in moves: reimport'
        rows.append((name, d.NAME, 'Tekken 8' if game_of(d) == 'tekken8' else 'Tekken 7', state))
    return rows
