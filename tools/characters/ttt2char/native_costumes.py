"""Costume-only packs for native Paul. No roster, moveset or save replacement."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from types import SimpleNamespace

from . import InputError, pack, signals

PRESETS = [('DefaultCos1P', 'Tekken 7 default (1P)'), ('DefaultCos2P', 'Tekken 7 default (2P)'),
           ('1P_c1', 'Default alternate colour'), ('cb', 'Cowboy'), ('cb_c1', 'Cowboy alternate colour'),
           ('cb_poncho', 'Cowboy poncho'), ('fire_jersey', 'Flame jersey'), ('ninjya', 'Ninja'),
           ('riders', 'Biker'), ('riders_silver', 'Silver biker')]
MAX_SELECTED = 6
# Keep the title's 0x10 texture class; added fighter presets end below 0x10d00000.
TEXTURE_BASE = 0x10e00000
PREVIEW_BASE = 0x10e10000


def selection(names):
    names = list(dict.fromkeys(names))
    known = {name for name, _ in PRESETS}
    if not names or len(names) > MAX_SELECTED or set(names) - known:
        raise InputError('Choose one to six listed Paul presets.')
    return [name for name, _ in PRESETS if name in names]


def body_code(name):
    return 'pv' + chr(ord('a') + [preset for preset, _ in PRESETS].index(name))


def installed(folder):
    target = Path(folder) / 'native/pau'
    try:
        data = json.loads((target / 'presets.json').read_text(encoding='utf-8'))
        return selection(data['presets']) if (target / 'native.ini').is_file() else []
    except (OSError, ValueError, KeyError, InputError):
        return []


def rename(source, target):
    """Allow a short Windows scanner/sync lock to release, without hiding other errors."""
    for attempt in range(21):
        try:
            return source.rename(target)
        except OSError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 20:
                raise
            time.sleep(.1)


def publish(temporary, target):
    """Atomic directory switch with a retained backup and rollback on failure."""
    temporary, target = Path(temporary), Path(target)
    if temporary.resolve().parent != target.resolve().parent or temporary.is_symlink() or target.is_symlink():
        raise InputError('Native costume folders must be ordinary sibling directories.')
    if target.exists() and not (target / 'native.ini').is_file():
        raise InputError('Refusing to replace an unrecognised native costume directory: ' + str(target))
    backup = target.with_name('.pau-backup-' + uuid.uuid4().hex)
    with signals.deferred():
        if target.exists():
            rename(target, backup)
        try:
            rename(temporary, target)
        except BaseException:
            if backup.exists():
                rename(backup, target)
            raise
    return target


def remove(folder):
    target = Path(folder) / 'native/pau'
    if not target.exists():
        return
    if target.is_symlink() or not (target / 'native.ini').is_file():
        raise InputError('Refusing to remove an unrecognised native costume directory.')
    rename(target, target.with_name('.pau-backup-' + uuid.uuid4().hex))


def build(game, tekken7, folder, names, log=print, cached=None):
    from . import importer
    from .characters import claudio
    from .convert import art, chains, effects, face, itemdb, model, outfits, tiger
    from .source import Tekken7Source
    from .tekken7.pak import Paks
    from .ttt2 import bone, nud, nut
    from .ttt2.archive import key_of
    names = selection(names)
    folder = Path(pack.output_folder(str(folder)))
    target = folder / 'native/pau'
    target.parent.mkdir(parents=True, exist_ok=True)
    paks = Paks(importer.tekken7_paks(str(tekken7)))
    archives = importer._archives(importer.ttt2_folder(str(game)))
    temporary = None
    try:
        source = Tekken7Source(paks)
        rpx = importer._rpx(importer.ttt2_folder(str(game)))
        entries, native_count = rpx.u32(0x103B4B84), rpx.u32(0x103B4B88)
        if native_count != 3:
            raise InputError('This experiment supports the EU v16 Paul costume table (three native presets).')
        preview_key = rpx.u32(0x10161590)
        previews = nut.read(archives.read(preview_key))['textures']
        if len(previews) < native_count:
            raise InputError('Paul native costume previews are incomplete.')
        previews = previews[:native_count]
        donor_bon = archives.read_name('pau.bon')
        donor_xml = archives.read_name('pau.xml')
        xml = itemdb.body_only(donor_xml)
        effect_files, _, _ = effects.copy_files(archives, 'pau', itemdb.effect_names(donor_xml), {}, log=log)
        base = SimpleNamespace(CODE='pau', DONOR='pau', NAME='Paul Phoenix', SEX='male', TEKKEN7_CODE='pau',
                               TEKKEN7={'costume': '', 'parts': [], 'merge_order': ['fac', 'bdl', 'bdu', 'har', 'fah']},
                               MESHES={}, MATERIALS={}, TEMPLATES=claudio.TEMPLATES,
                               TEMPLATE_TEXTURES=claudio.TEMPLATE_TEXTURES)
        files = {}
        labels = dict(PRESETS)
        for index, preset in enumerate(names):
            log('@step fighter paul %d %d' % (index + 1, len(names)))
            log('Paul preset: ' + labels[preset])
            costume = '/Game/Character/Item/Sets/PAU/CS_PAU_' + preset
            definition = outfits.definition(paks, base, costume)
            if cached:
                path = Path(cached) / ('CS_PAU_' + preset)
                mesh, textures, skeleton = [(path / ('pau' + ext)).read_bytes() for ext in ('.nud', '.nut', '.bon')]
                spring_path = path / 'pau.mop'
                mop = spring_path.read_bytes() if spring_path.is_file() else importer.spring_file(archives, definition, skeleton, None)
            else:
                mesh, textures, skeleton, _, springs = model.convert(source, archives, definition, 128 + index, log=log)
                mop = importer.spring_file(archives, definition, skeleton, springs)
            skeleton = face.same_joints(skeleton, donor_bon)
            if bone.read(skeleton)['names'][:len(bone.read(donor_bon)['names'])] != bone.read(donor_bon)['names']:
                raise InputError('Paul native skeleton layout changed during conversion.')
            mesh, textures = outfits.relocate(mesh, textures, TEXTURE_BASE + PRESETS.index((preset, labels[preset])) * 0x1000)
            # Read back the output before the old pack can be replaced.
            nud.read(mesh)
            nut.read(textures)
            code = body_code(preset)
            files.update({code + '.nud': mesh, code + '.nut': textures, code + '.bon': skeleton, code + '.xml': xml})
            if mop is None:
                mop = archives.read_name('pau.mop') if archives.has(key_of('pau.mop')) else chains.empty_spring_file(
                    archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop'))
            files[code + '.mop'] = mop
            if archives.has(key_of('pau.havok.xml')):
                files[code + '.havok.xml'] = archives.read_name('pau.havok.xml')
            for name, data in effect_files.items():
                files[code + '/' + name] = data
            suffix = {'DefaultCos1P': '01', 'DefaultCos2P': '02'}.get(preset, preset.upper())
            definition.ART = {'costume': '/Game/UI_common/Texture2D/ReplaceImages/CS_CH_SLOT/CS_CH_SLOT_PAU_' + suffix}
            preview = art.costume_previews(source, archives, rpx, definition, 128 + index)
            if preview is None:
                raise InputError('Missing Paul preset preview: ' + preset)
            texture = nut.read(preview)['textures'][0]
            texture['gidx'] = PREVIEW_BASE + PRESETS.index((preset, labels[preset]))
            texture.pop('ext', None)
            previews.append(texture)
        files['art/costumes.nut'] = nut.write(previews)
        codes = [body_code(name) for name in names]
        files['native.ini'] = ('format = 1\ntarget = pau\noutfits = ' + ','.join(codes) + '\n').encode()
        files['presets.json'] = (json.dumps({'format': 1, 'source': 'tekken7', 'presets': names}, indent=2) + '\n').encode()
        temporary = Path(tempfile.mkdtemp(prefix='.pau-import-', dir=target.parent))
        for name, data in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        destination = publish(temporary, target)
        log('Paul presets installed: ' + str(destination))
        log('@done')
        return destination
    finally:
        archives.close()
        paks.close()
        if temporary is not None and temporary.exists():
            # A failed unpublished import is retained for diagnosis, never loaded.
            log('Unpublished temporary assets retained: ' + str(temporary))
