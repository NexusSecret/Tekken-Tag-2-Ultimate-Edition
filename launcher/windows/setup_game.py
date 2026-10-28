"""First-run Windows setup, using this extracted project and the player's RPX.

All downloaded tools stay private under local/. No second source checkout,
admin installation, system PATH change, game download, or Linux launcher change.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(asset, cache):
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file() and digest(cache) == asset['sha256']:
        return cache
    part = cache.with_suffix(cache.suffix + '.part')
    print('Downloading ' + asset['url'].rsplit('/', 1)[-1], flush=True)
    with urllib.request.urlopen(asset['url'], timeout=120) as response, part.open('wb') as output:
        shutil.copyfileobj(response, output, 1024 * 1024)
    if digest(part) != asset['sha256']:
        raise ValueError('Download checksum mismatch: ' + cache.name)
    part.replace(cache)
    return cache


def unzip(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as reader:
        for item in reader.infolist():
            path = (target / item.filename).resolve()
            if not path.is_relative_to(target.resolve()) or ':' in item.filename or '\\' in item.filename:
                raise ValueError('Unsafe downloaded archive path: ' + item.filename)
        reader.extractall(target)


def manifest(settings):
    return json.loads((settings.root / 'tools/windows-bootstrap.lock.json').read_text(encoding='utf-8-sig'))


def powershell(script, *args):
    return ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), *map(str,args)]


def ensure_tools(settings, run):
    lock = manifest(settings)
    tools = Path(settings.values['tools'] or settings.root / 'local/windows-tools').resolve()
    settings.values['tools'] = str(tools); settings.save()
    downloads = settings.root / 'local/windows-downloads'
    compiler = tools / lock['compiler']['folder'] / 'bin/clang.exe'
    if not compiler.is_file():
        archive = download(lock['compiler'], downloads / 'llvm-mingw.zip')
        unzip(archive, tools)
    git = tools / 'git/cmd/git.exe'
    if not git.is_file() and not shutil.which('git'):
        unzip(download(lock['git'], downloads / 'mingit.zip'), tools / 'git')
    if git.is_file():
        os.environ['PATH'] = str(git.parent) + os.pathsep + os.environ.get('PATH','')
    # Existing scripts use python on PATH; prefer this launcher's portable
    # interpreter, never a Store alias or a different system Python.
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + str(compiler.parent) + os.pathsep + os.environ.get('PATH','')
    package_dir = tools / 'python'
    stamp = package_dir / '.ttt2-packages.json'
    if not stamp.exists() or json.loads(stamp.read_text()) != lock['packages']:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
             '--upgrade', '--target', str(package_dir), *lock['packages']], settings)
        stamp.write_text(json.dumps(lock['packages']), encoding='utf-8')
    ninja = package_dir / 'ninja/data/bin/ninja.exe'
    (package_dir / 'bin').mkdir(exist_ok=True)
    if not (package_dir / 'bin/ninja.exe').is_file():
        shutil.copy2(ninja, package_dir / 'bin/ninja.exe')
    os.environ.update(settings.environment())
    sys.path.insert(0, str(package_dir))
    return tools


def verified_rpx(root, expected):
    for candidate in root.rglob('Tekken.rpx'):
        if digest(candidate) == expected: return candidate
    raise ValueError('This game source does not contain the supported European Wii U update v16 executable.')


def prepare_rpx(settings, run):
    source_text = settings.values['source'] or settings.values['title']
    if not source_text or not Path(source_text).exists():
        raise ValueError('Choose your European Wii U game archive with update v16 first.')
    source = Path(source_text)
    expected = manifest(settings)['rpx_sha256']
    destination = settings.root / 'local/windows-setup/Tekken.rpx'
    # Always check the currently selected source, even after an earlier setup.
    if source.is_dir():
        selected = verified_rpx(source, expected)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected, destination)
    else:
        workspace = settings.root / 'local/windows-setup'
        workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='analysis-', dir=workspace) as temporary:
            run([str(settings.build / 'wua_extract.exe'), 'extract-analysis', str(source), temporary], settings)
            selected = verified_rpx(Path(temporary), expected)
            part = destination.with_suffix('.part'); shutil.copy2(selected, part); part.replace(destination)
    return destination


# Conservatively bound paths before Git/CMake can leave an incomplete checkout.
# Windows long-path support is not uniform across these independently built tools.
MAX_PROJECT_PATH = 110
MAX_TOOLS_PATH = 150

def validate_setup_paths(settings):
    def windows_length(path):
        return len(str(path).encode('utf-16-le')) // 2
    if windows_length(settings.root) > MAX_PROJECT_PATH:
        raise ValueError(
            'The extracted project folder path is too long for Windows build tools. '
            'Extract a fresh copy into a short folder such as D:/TTT2 or C:/Games/TTT2 '
            '(Start Ultimate Launcher.cmd must be directly inside that folder), then start setup again. '
            'Your game archive does not need to move. Current project: ' + str(settings.root))
    tools = settings.values.get('tools') or settings.root / 'local/windows-tools'
    if windows_length(tools) > MAX_TOOLS_PATH:
        raise ValueError('The Windows tools folder path is too long. Choose a shorter tools folder '
                         'in Paths, or use a fresh project copy in D:/TTT2. Current tools: ' + str(tools))


def setup(settings, run):
    # Refuse missing inputs before downloading large developer tools.
    source = settings.values['source'] or settings.values['title']
    if not source or not Path(source).exists() or not settings.values['install']:
        raise ValueError('Choose your Wii U game source and installation folder first.')
    if settings.build != settings.root / 'build-windows-tools':
        raise ValueError('First-time setup requires the project build-windows-tools folder.')
    validate_setup_paths(settings)
    print('@step tools Getting the missing Windows tools ready', flush=True)
    tools = ensure_tools(settings, run)
    print('@step dependencies Preparing graphics libraries', flush=True)
    run(powershell(settings.root / 'tools/setup_windows_runtime.ps1', '-ToolsRoot', tools), settings)
    print('@step tools Building game preparation tools', flush=True)
    run(powershell(settings.root / 'tools/build_windows_tools.ps1', '-ToolsRoot', tools), settings)
    print('@step source Checking your own Wii U game', flush=True)
    rpx = prepare_rpx(settings, run)
    generated = settings.root / 'generated/ttt2-windows'
    print('@step generate Preparing game code from your own copy', flush=True)
    run([str(settings.build / 'recomp/cafe-recomp.exe'), str(rpx), str(generated)], settings)
    print('@step build Building the Windows game', flush=True)
    run(powershell(settings.root / 'tools/build_windows_runtime.ps1', '-ToolsRoot', tools,
                   '-Rpx', rpx), settings)
    print('@step install Installing the game', flush=True)
    # The project already has its launcher entry point. Do not require writing
    # a system/desktop shortcut to finish a portable first-time setup.
    run(settings.installer_command() + ['--no-launcher'], settings)
    print('Setup complete. You can now click Play.', flush=True)
