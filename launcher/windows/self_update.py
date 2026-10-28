"""The Windows launcher's own updates, as the Linux AppImage's
(launcher/core/release.cpp, launcher/app/self_update.cpp).

The release's Ultimate_Launcher-x86_64.exe (entry.cpp with the project's
files appended, make_launcher_exe.py) opens this launcher with
TTT2_LAUNCHER_EXE naming it. Only then is GitHub asked for this repository's
newest release; when that one is newer, Update downloads its .exe beside the
one that was started, checks it (its size, the SHA-256 GitHub gives, that it
is a 64-bit Windows program with its files, and that it says it is the
version it was released as), puts it in that one's place and opens it as this
launcher closes. Anything failing leaves the .exe as it was.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import contextlib
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
# The newest release as GitHub's API gives it (drafts and pre-releases are
# never it). $TTT2_LAUNCHER_RELEASES is asked instead when set (tests).
LATEST = 'https://api.github.com/repos/Petexy/Tekken-Tag-2-Ultimate-Edition/releases/latest'
# The .exe this launcher was opened from (entry.cpp sets it).
EXE_VARIABLE = 'TTT2_LAUNCHER_EXE'
# The pid of the launcher an update replaces: the new .exe waits for it to end.
REPLACES_VARIABLE = 'TTT2_LAUNCHER_AFTER'
# entry.cpp's trailer after the appended files: their size, count, SHA-256, magic.
TRAILER = struct.Struct('<QQ32s8s')
MAGIC = b'TTT2PAY1'
# How long the new .exe may take to say its version.
VERSION_SECONDS = 60
# How long between two quiet questions to GitHub, while the window stays open.
CHECK_SECONDS = 6 * 3600
# The commit the release .exe was made from (make_launcher_exe.py writes it into its files).
BUILD_COMMIT = 'launcher/windows/build-commit'


class UpdateError(Exception):
    """Why the launcher cannot be updated, as a sentence for the player."""


class Cancelled(Exception):
    pass


@lru_cache(maxsize=None)
def version(root=ROOT):
    """This launcher's version: the Linux launcher's (one release has both)."""
    text = (Path(root) / 'launcher/builder/CMakeLists.txt').read_text(encoding='utf-8')
    found = re.search(r'^set\(TTT2_LAUNCHER_VERSION ([0-9.]+)\)', text, re.M)
    if not found: raise ValueError('launcher/builder/CMakeLists.txt names no TTT2_LAUNCHER_VERSION')
    return found.group(1)


def build_commit(root=ROOT):
    """The commit these files are: the release .exe's, else a Git checkout's HEAD; None when not known
    (a project ZIP)."""
    file = Path(root) / BUILD_COMMIT
    if file.is_file(): return file.read_text(encoding='utf-8').strip() or None
    git = Path(root) / '.git'
    try:
        if git.is_file():       # (a worktree: its Git folder is named there, its branches in the shared one)
            git = (Path(root) / git.read_text(encoding='utf-8').split('gitdir:', 1)[1].strip()).resolve()
        shared = (git / (git / 'commondir').read_text(encoding='utf-8').strip()).resolve() \
            if (git / 'commondir').is_file() else git
        head = (git / 'HEAD').read_text(encoding='utf-8').strip()
        if not head.startswith('ref: '): return head
        ref = head[5:]
        for folder in (git, shared):
            if (folder / ref).is_file(): return (folder / ref).read_text(encoding='utf-8').strip()
        for line in (shared / 'packed-refs').read_text(encoding='utf-8').splitlines():
            if line.endswith(' ' + ref): return line.split()[0]
    except (OSError, IndexError):
        pass
    return None


def version_numbers(text):
    """A version's numbers ("0.1.0", "v0.2", "V1.10.3"); None when it is not one."""
    if text[:1] in ('v', 'V'): text = text[1:]
    parts = text.split('.')
    if not all(p.isascii() and p.isdigit() and len(p) <= 9 for p in parts): return None
    return [int(p) for p in parts]


def compare_versions(a, b):
    """Below 0, 0, above 0 as `a` is older than, the same as or newer than `b`
    (a missing number is 0); None when either is not a version."""
    x, y = version_numbers(a), version_numbers(b)
    if x is None or y is None: return None
    n = max(len(x), len(y))
    x, y = x + [0] * (n - len(x)), y + [0] * (n - len(y))
    return (x > y) - (x < y)


@dataclass
class Release:
    version: str
    tag: str
    page: str       # its page on GitHub (what is new in it)
    asset: str      # the .exe's file name
    url: str        # where it is downloaded from
    size: int = 0
    sha256: str = ''  # lowercase hex, when GitHub gives one


@dataclass
class Answer:
    """GitHub's answer: the release with its .exe, `none` when no release is
    published, else why it cannot be updated to."""
    release: Release = None
    none: bool = False
    error: str = ''


def parse_release(text):
    try:
        root = json.loads(text)
    except ValueError as error:
        return Answer(error="GitHub's answer is not readable (%s)" % error)
    if not isinstance(root, dict):
        return Answer(error="GitHub's answer is not readable (not an object)")
    if not isinstance(root.get('tag_name'), str):
        # An error: its message says which.
        message = root.get('message') if isinstance(root.get('message'), str) else ''
        if message == 'Not Found': return Answer(none=True)
        if 'rate limit' in message.lower():
            return Answer(error='GitHub answers only so many questions from one network an hour: try again later')
        return Answer(error='GitHub answered "%s"' % message if message else "GitHub's answer names no release")
    tag = root['tag_name']
    number = tag[1:] if tag[:1] in ('v', 'V') else tag
    if version_numbers(number) is None:
        return Answer(error='the newest release, %s, is not named as a version (such as v0.2.0)' % tag)
    # Its .exe for this kind of PC: one named for x86-64, else the only one
    # named for no processor.
    named, plain = None, []
    for asset in root.get('assets') or []:
        if not isinstance(asset, dict): continue
        name = str(asset.get('name', '')).lower()
        if not name.endswith('.exe') or asset.get('state', 'uploaded') != 'uploaded' or not asset.get('browser_download_url'):
            continue
        if any(word in name for word in ('x86_64', 'x86-64', 'amd64', 'x64')):
            named = named or asset
        elif not any(word in name for word in ('aarch64', 'arm', 'i686', 'i386', 'win32')):
            plain.append(asset)
    chosen = named or (plain[0] if len(plain) == 1 else None)
    if not chosen: return Answer(error='version %s has no Windows launcher (.exe) to download' % number)
    size = chosen.get('size')
    digest = str(chosen.get('digest') or '').lower()
    return Answer(release=Release(
        version=number, tag=tag, page=str(root.get('html_url') or ''), asset=str(chosen['name']),
        url=str(chosen['browser_download_url']), size=size if isinstance(size, int) and size > 0 else 0,
        sha256=digest[7:] if digest.startswith('sha256:') and len(digest) == 7 + 64 else ''))


def custom_releases():
    return bool(os.environ.get('TTT2_LAUNCHER_RELEASES'))


def releases_url():
    return os.environ.get('TTT2_LAUNCHER_RELEASES') or LATEST


def user_agent():
    return 'ttt2-launcher/' + version()


def running_exe():
    """The release .exe this launcher was opened from; None otherwise (a
    project ZIP or a build: those are updated as a whole, not by this)."""
    value = os.environ.get(EXE_VARIABLE)
    return Path(value) if value and Path(value).is_absolute() and Path(value).is_file() else None


def reason(error):
    """Why a download failed, without Python's wrapping."""
    if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
        error = error.reason
    if isinstance(error, OSError) and error.strerror: return error.strerror
    return str(error) or type(error).__name__


def sentence(text):
    text = text[:1].upper() + text[1:]
    return text if text.endswith('.') else text + '.'


def ask(url=None):
    """GitHub's answer about the newest release. OSError when it cannot be asked."""
    request = urllib.request.Request(url or releases_url(), headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return parse_release(response.read())
    except urllib.error.HTTPError as error:
        # (It says why: no release yet, or too many questions.)
        with error: body = error.read()
        if not body: raise
        return parse_release(body)


def update_file(exe):
    """Where the new .exe is downloaded to: beside the old one (one drive, so
    that it can be renamed over it)."""
    return exe.with_name(exe.stem + '.new.exe')


def old_file(exe):
    """Where the old .exe goes while the new one takes its place: a running
    .exe can be renamed but not replaced. The new one deletes it (entry.cpp)."""
    return exe.with_name(exe.stem + '.old.exe')


def cannot_replace(exe):
    """Why a new .exe cannot be put in the place of `exe` (its folder cannot
    be written to); empty when it can."""
    try:
        with tempfile.TemporaryFile(dir=exe.parent): pass
    except OSError as error:
        return reason(error)
    return ''


def is_launcher_exe(file):
    """Whether `file` is a 64-bit Windows program with a launcher's files
    appended (entry.cpp's trailer)."""
    try:
        with open(file, 'rb') as stream:
            head = stream.read(64)
            if len(head) < 64 or head[:2] != b'MZ': return False
            stream.seek(struct.unpack_from('<I', head, 0x3C)[0])
            if stream.read(6) != b'PE\0\0\x64\x86': return False
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            if end < TRAILER.size: return False
            stream.seek(end - TRAILER.size)
            size, _, _, magic = TRAILER.unpack(stream.read(TRAILER.size))
            return magic == MAGIC and size <= end - TRAILER.size
    except OSError:
        return False


def version_in(output):
    """The version a launcher's --version names ("ttt2-launcher 0.2.0"), or ''."""
    for line in output.splitlines():
        words = line.split()
        if len(words) == 2 and words[0] == 'ttt2-launcher' and version_numbers(words[1]) is not None:
            return words[1]
    return ''


def sha256_of(file):
    with open(file, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(release, file, cancelled, say):
    request = urllib.request.Request(release.url, headers={'User-Agent': user_agent()})
    with urllib.request.urlopen(request, timeout=60) as response, open(file, 'wb') as out:
        total = release.size or int(response.headers.get('Content-Length') or 0)
        done, shown = 0, 0.0
        while chunk := response.read(1 << 16):
            if cancelled(): raise Cancelled()
            out.write(chunk)
            done += len(chunk)
            if total and (time.monotonic() - shown > 0.25 or done == total):
                say('@progress %d %d' % (done, total)); shown = time.monotonic()


def said_version(file, cancelled):
    """What the .exe says its version is, asked as the launcher asks it."""
    process = subprocess.Popen([str(file), '--version'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        end = time.monotonic() + VERSION_SECONDS
        while process.poll() is None:
            if cancelled(): raise Cancelled()
            if time.monotonic() > end:
                raise UpdateError('It does not start: it did not answer within %d seconds.' % VERSION_SECONDS)
            time.sleep(0.1)
        return process.returncode, version_in(process.stdout.read().decode('utf-8', 'replace'))
    finally:
        if process.poll() is None: process.kill(); process.wait()
        process.stdout.close()


def replace(update, exe):
    """`update` put in the place of `exe`; `exe` back as it was when it cannot be."""
    old = old_file(exe)
    with contextlib.suppress(FileNotFoundError): old.unlink()
    moved = exe.exists()
    if moved: os.replace(exe, old)
    try:
        os.replace(update, exe)
    except OSError:
        if moved: os.replace(old, exe)
        raise
    with contextlib.suppress(OSError): old.unlink()


def update(exe, cancelled=lambda: False, say=lambda line: print(line, flush=True)):
    """Updates `exe` to the newest release. Its version, or None when this one
    is the newest. UpdateError says why it cannot; Cancelled when cancelled."""
    current = version()
    say('@step update Looking for a newer version')
    try:
        answer = ask()
    except OSError as error:
        raise UpdateError('GitHub cannot be reached: %s.' % reason(error))
    release = answer.release
    if answer.none or (release and compare_versions(release.version, current) <= 0):
        say('No release is published yet.' if answer.none else 'The newest release is %s.' % release.tag)
        say('@step update The launcher is up to date: version %s is the newest.' % current)
        return None
    if not release: raise UpdateError(sentence(answer.error))
    if not custom_releases() and not release.url.startswith('https://'):
        raise UpdateError('Version %s is not offered over HTTPS.' % release.version)
    if why := cannot_replace(exe):
        raise UpdateError('Its folder, %s, cannot be written to (%s): move the launcher to a folder of yours, '
                          'then update it.' % (exe.parent, why))
    file = update_file(exe)
    try:
        with contextlib.suppress(FileNotFoundError): file.unlink()  # (one stopped half-way)
        say('@step update Downloading version ' + release.version)
        try:
            download(release, file, cancelled, say)
        except (OSError, ValueError) as error:
            raise UpdateError('Version %s cannot be downloaded: %s.' % (release.version, reason(error)))
        size = file.stat().st_size
        if release.size and size != release.size:
            raise UpdateError('The download of version %s is incomplete (%d of %d bytes).'
                              % (release.version, size, release.size))
        if release.sha256 and sha256_of(file) != release.sha256:
            raise UpdateError("The download of version %s is damaged: its SHA-256 is not GitHub's." % release.version)
        if not is_launcher_exe(file):
            raise UpdateError('What was downloaded for version %s is not a Windows launcher.' % release.version)
        # It runs on this PC, and is the version it was released as (else each
        # update would download it again).
        say('@step update Checking version ' + release.version)
        try:
            code, said = said_version(file, cancelled)
        except OSError as error:
            raise UpdateError('Version %s does not start on this PC: %s.' % (release.version, reason(error)))
        except UpdateError as error:
            raise UpdateError('Version %s does not start on this PC. %s' % (release.version, error))
        if code != 0 or not said:
            raise UpdateError('Version %s does not start on this PC (code %d).' % (release.version, code))
        if compare_versions(said, release.version) != 0:
            raise UpdateError('The launcher released as version %s is version %s.' % (release.version, said))
        try:
            replace(file, exe)
        except OSError as error:
            raise UpdateError('It cannot replace %s (%s).' % (exe, reason(error)))
    except BaseException:
        with contextlib.suppress(OSError): file.unlink()
        raise
    say('Version %s is in %s.' % (release.version, exe))
    say('@launcher-updated ' + release.version)
    return release.version


def open_updated(exe):
    """The new .exe opened; it waits for this launcher to end first."""
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen([str(exe)], cwd=exe.parent, env=dict(os.environ, **{REPLACES_VARIABLE: str(os.getpid())}),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=flags)
