#!/usr/bin/env python3
"""Makes the Windows release's launcher, as make_appimage.sh makes the Linux one.

    python3 launcher/windows/make_launcher_exe.py [--stub EXE | --cxx COMPILER] [--allow-dirty] OUTPUT

OUTPUT is the .exe to write (Ultimate_Launcher-x86_64.exe for a release). It is
launcher/windows/entry.cpp compiled for 64-bit Windows, with this project's
files appended: Git's tracked files as they are in the working tree, batch
files with Windows line ends. Nothing of the game is in it: the game is built
on the player's PC from their own .wua. On the player's PC the .exe keeps the
files in %LOCALAPPDATA%\\TTT2Ultimate\\launcher, opens the launcher from there,
and that launcher updates the .exe from this repository's releases
(self_update.py).

--stub EXE      entry.cpp as CMake built it for Windows (build-windows-*/ttt2-launcher.exe)
--cxx COMPILER  else it is compiled here: with x86_64-w64-mingw32-g++ by default,
                with the launcher's icon and version details when windres and
                rsvg-convert are there too
--allow-dirty   pack the working tree as it is, with uncommitted changes and new
                files Git does not ignore (tests: a release is made from a commit)

The version is TTT2_LAUNCHER_VERSION in launcher/builder/CMakeLists.txt, the
AppImage's: a release is tagged v<version> with both attached.
"""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from self_update import BUILD_COMMIT, MAGIC, TRAILER, is_launcher_exe, version  # noqa: E402

ICON = REPO / 'launcher/app/io.github.petexy.TekkenTag2UltimateEdition.svg'
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def die(message):
    sys.exit('make_launcher_exe.py: ' + message)


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], check=True, capture_output=True).stdout


def tracked(allow_dirty):
    """{path: bytes} of Git's tracked files, as they are in the working tree
    (with `allow_dirty`, also the new files it does not ignore)."""
    if not allow_dirty and git('status', '--porcelain', '--untracked-files=no').strip():
        die('the working tree has uncommitted changes: commit them, or pass --allow-dirty (tests only)')
    entries = [line.split(b'\t', 1) for line in git('ls-files', '-s', '-z').split(b'\0') if line]
    if allow_dirty:
        entries += [[b'100644', path] for path in git('ls-files', '-o', '--exclude-standard', '-z').split(b'\0') if path]
    files = {}
    for info, path in entries:
        mode, path = info.split()[0], path.decode('utf-8')
        if mode not in (b'100644', b'100755'): die(path + ' is not a plain file (a link or a submodule)')
        file = REPO / path
        if not file.is_file():
            if allow_dirty: continue
            die(path + ' is missing from the working tree')
        data = file.read_bytes()
        # cmd.exe can miss a batch file's labels when its lines end in LF only.
        if path.lower().endswith(('.cmd', '.bat')): data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        files[path] = data
    return files


def payload(files):
    """entry.cpp's appended part: each file's path and bytes, then its trailer."""
    out = bytearray()
    for path in sorted(files):
        name = path.encode('utf-8')
        out += struct.pack('<I', len(name)) + name + struct.pack('<Q', len(files[path])) + files[path]
    return bytes(out) + TRAILER.pack(len(out), len(files), hashlib.sha256(out).digest(), MAGIC)


def ico(pngs):
    """An .ico of PNG images (each {size: bytes})."""
    head = struct.pack('<HHH', 0, 1, len(pngs))
    offset, entries, data = 6 + 16 * len(pngs), b'', b''
    for size, png in sorted(pngs.items()):
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return head + entries + data


def resource(cxx, windres, number, work):
    """The icon, version details and manifest as an object file; None
    (with why) when the tools for it are missing."""
    rsvg = shutil.which('rsvg-convert')
    windres = windres or shutil.which(cxx.rsplit('-', 1)[0] + '-windres') or shutil.which('windres') or shutil.which('llvm-windres')
    if not rsvg or not windres:
        print('make_launcher_exe.py: no icon or version details: needs rsvg-convert and windres', file=sys.stderr)
        return None
    pngs = {}
    for size in ICON_SIZES:
        png = work / ('icon-%d.png' % size)
        subprocess.run([rsvg, '-w', str(size), '-h', str(size), '-o', str(png), str(ICON)], check=True)
        pngs[size] = png.read_bytes()
    (work / 'launcher.ico').write_bytes(ico(pngs))
    (work / 'launcher.manifest').write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
    <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
  </requestedPrivileges></security></trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
    <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
  </application></compatibility>
</assembly>
''', encoding='utf-8')
    numbers = ','.join((number.split('.') + ['0'] * 4)[:4])
    (work / 'launcher.rc').write_text('''1 ICON "launcher.ico"
1 24 "launcher.manifest"
1 VERSIONINFO
FILEVERSION %(numbers)s
PRODUCTVERSION %(numbers)s
FILEOS 0x40004
FILETYPE 0x1
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904B0"
    BEGIN
      VALUE "FileDescription", "Ultimate Launcher"
      VALUE "FileVersion", "%(version)s"
      VALUE "InternalName", "ttt2-launcher"
      VALUE "OriginalFilename", "Ultimate_Launcher-x86_64.exe"
      VALUE "ProductName", "Tekken Tag 2 Ultimate Edition"
      VALUE "ProductVersion", "%(version)s"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
''' % dict(numbers=numbers, version=number), encoding='utf-8')
    subprocess.run([windres, '-O', 'coff', '-i', 'launcher.rc', '-o', 'launcher.res.o'], cwd=work, check=True)
    return work / 'launcher.res.o'


def compile_stub(cxx, windres, number, work):
    if not shutil.which(cxx): die(cxx + ' is not installed (MinGW-w64, or pass --cxx or --stub)')
    objects = [str(o) for o in [resource(cxx, windres, number, work)] if o]
    out = work / 'stub.exe'
    subprocess.run([cxx, '-std=c++20', '-O2', '-municode', '-mwindows', '-static', '-s',
                    '-DTTT2_LAUNCHER_VERSION="%s"' % number, str(HERE / 'entry.cpp'), *objects,
                    '-o', str(out), '-ladvapi32', '-lbcrypt', '-lshell32'], check=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('output', type=Path)
    which = parser.add_mutually_exclusive_group()
    which.add_argument('--stub', type=Path)
    which.add_argument('--cxx', default='x86_64-w64-mingw32-g++')
    parser.add_argument('--windres')
    parser.add_argument('--allow-dirty', action='store_true')
    args = parser.parse_args()
    number = version(REPO)
    output = args.output.resolve()
    if not output.parent.is_dir(): die('%s is not a folder' % output.parent)
    files = tracked(args.allow_dirty)
    # (Its build's commit: the launcher asks GitHub what main has beyond it, self_update.build_commit.)
    files[BUILD_COMMIT] = git('rev-parse', 'HEAD').strip() + b'\n'
    for needed in ('launcher/windows/main.py', 'Start Ultimate Launcher.cmd', 'launcher/builder/CMakeLists.txt'):
        if needed not in files: die('the project lacks ' + needed)
    with tempfile.TemporaryDirectory(prefix='ttt2-launcher-exe-') as temporary:
        stub = args.stub or compile_stub(args.cxx, args.windres, number, Path(temporary))
        program = Path(stub).read_bytes()
        if program[:2] != b'MZ': die('%s is not a Windows program' % stub)
        if program[-TRAILER.size:][-len(MAGIC):] == MAGIC: die('%s already holds files: give the launcher as built' % stub)
        part = output.with_name(output.name + '.part')
        part.write_bytes(program + payload(files))
    if not is_launcher_exe(part):
        part.unlink(); die('the .exe made is not a 64-bit Windows launcher')
    os.replace(part, output)
    print('Made %s: Ultimate Launcher %s, %d files (%.1f MB)'
          % (output, number, len(files), output.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
