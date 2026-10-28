"""Windows Ultimate Launcher UI. Run through ttt2-launcher.exe or Python 3 + Tk."""
from pathlib import Path
import argparse
import datetime
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import contextlib
import webbrowser

from backend import Settings, built_by, fighters, worker
import self_update


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--worker', choices=('setup', 'build', 'install', 'update', 'import', 'remove', 'launcher'))
    parser.add_argument('--cancel-file', type=Path)
    parser.add_argument('--ui-smoke-test', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('fighters', nargs='*')
    args = parser.parse_args()
    settings = Settings(args.build_dir, args.config)
    if args.worker:
        cancelled = lambda: bool(args.cancel_file and args.cancel_file.exists())
        # (The launcher's update stops only where it can: never half-way through replacing the .exe.)
        if args.cancel_file and args.worker != 'launcher':
            def watch_cancel():
                import _thread
                while not args.cancel_file.exists():
                    threading.Event().wait(.2)
                _thread.interrupt_main()
            threading.Thread(target=watch_cancel, daemon=True).start()
        try:
            worker(settings, args.worker, args.fighters, cancelled)
        except KeyboardInterrupt:
            print('Cancelled. Completed extraction data is kept.', flush=True)
            return 130
        except self_update.Cancelled:
            print('Update cancelled. The launcher is as it was.', flush=True)
            return 130
        except self_update.UpdateError as error:
            print('@error ' + str(error), flush=True)
            return 1
        return 0
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    if args.check:
        print('Windows Ultimate Launcher: Python/Tk and backend available')
        return 0

    window = tk.Tk()
    window.title('Ultimate Launcher — Windows')
    window.geometry('1120x790')
    window.minsize(850, 700)
    style = ttk.Style(window)
    if 'vista' in style.theme_names(): style.theme_use('vista')
    style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
    style.configure('TButton', padding=(10, 6))
    frame = ttk.Frame(window, padding=18); frame.pack(fill='both', expand=True)
    launcher_exe = self_update.running_exe()
    header = ttk.Frame(frame); header.pack(fill='x'); header.columnconfigure(0, weight=1)
    ttk.Label(header, text='Tekken Tag Tournament 2', style='Title.TLabel').grid(row=0, column=0, sticky='w')
    ttk.Label(header, text='Ultimate Edition  •  Windows  •  Ultimate Launcher ' + self_update.version(),
              font=('Segoe UI', 11)).grid(row=1, column=0, sticky='w', pady=(0, 12))
    # The release .exe's own update (self_update.py): a notice when a newer
    # version is out, and a button that also looks for one any time.
    update_button = ttk.Button(header, text='Check for Updates', command=lambda: update_launcher())
    if launcher_exe: update_button.grid(row=0, column=1, rowspan=2, sticky='ne')
    notice = ttk.Frame(frame, padding=(12, 8), relief='solid', borderwidth=1); notice.columnconfigure(0, weight=1)
    notice_title, notice_detail = tk.StringVar(), tk.StringVar()
    ttk.Label(notice, textvariable=notice_title, font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='w')
    ttk.Label(notice, textvariable=notice_detail).grid(row=1, column=0, sticky='w')
    whats_new = ttk.Button(notice, text="What's New", command=lambda: open_release_page())
    whats_new.grid(row=0, column=1, rowspan=2, padx=(8, 0))
    notice_update = ttk.Button(notice, text='Update', command=lambda: update_launcher())
    notice_update.grid(row=0, column=2, rowspan=2, padx=(8, 0))
    tabs = ttk.Notebook(frame); tabs.pack(fill='both', expand=True)
    home = ttk.Frame(tabs, padding=14); tabs.add(home, text='Game & Fighters')
    paths_tab = ttk.Frame(tabs, padding=14); tabs.add(paths_tab, text='Paths')
    display_tab = ttk.Frame(tabs, padding=14); tabs.add(display_tab, text='Settings')
    events = queue.Queue()
    state = dict(process=None, game=None, log=None, cancel=None, action=None, error='', updated='')
    fields = {k: tk.StringVar(value=v) for k, v in settings.values.items()}
    buttons = [update_button, notice_update]
    status = tk.StringVar(value='Ready')
    game_status = tk.StringVar()
    ttk.Label(home, textvariable=game_status, wraplength=880).pack(anchor='w', pady=(0, 8))
    bar = ttk.Frame(home); bar.pack(fill='x')

    def save_paths():
        if state['process']: raise ValueError('Wait for the current task before changing paths.')
        settings.values.update({k: v.get().strip() for k, v in fields.items()})
        settings.save()

    def show_error(error):
        messagebox.showerror('Ultimate Launcher', str(error), parent=window)

    def read_settings():
        data = Path(settings.values['data'])
        if data.name != 'TTT2Ultimate':
            raise ValueError('The data folder must end in TTT2Ultimate so the game and launcher share settings.')
        return data / 'config'

    def refresh():
        folder = settings.installed()
        text = 'Installed: ' + str(folder) if folder else 'Development build: ' + str(settings.build)
        built = built_by(settings)
        if built and built != self_update.version():
            text += ('\nThe game was built by Ultimate Launcher %s; this is %s. Click Build / Rebuild, then '
                     'Update installed game, to bring its changes to the game.' % (built, self_update.version()))
        game_status.set(text)
        selected = tree.selection()
        tree.delete(*tree.get_children())
        try:
            for name, label, game, installed in fighters(settings):
                tree.insert('', 'end', iid=name, values=(label, game, installed))
            tree.selection_set([s for s in selected if tree.exists(s)])
        except Exception as error:
            status.set(str(error))

    def launch_game():
        try:
            if state['game'] and state['game'].poll() is None:
                raise ValueError('The game is already running from this launcher.')
            save_paths()
            command = settings.game_command()
            logdir = Path(settings.values['data']) / 'logs'; logdir.mkdir(parents=True, exist_ok=True)
            with (logdir / 'game-latest.log').open('w', encoding='utf-8') as log:
                state['game'] = subprocess.Popen(command, cwd=Path(command[0]).parent,
                    env=settings.environment(), stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            status.set('Game started. Its output is saved in logs/game-latest.log.')
        except Exception as error: show_error(error)

    def start(action, names=()):
        try:
            if state['process']: raise ValueError('Another task is running.')
            if action != 'launcher' and state['game'] and state['game'].poll() is None:
                raise ValueError('Close the game before building, installing, or changing fighters.')
            save_paths()
            if action == 'setup':
                from setup_game import validate_setup_paths
                validate_setup_paths(settings)
            if action in ('import', 'remove'): settings.import_command(names, action == 'remove')
            if action in ('install', 'update'): settings.installer_command(action == 'update')
            if action == 'remove' and not messagebox.askyesno('Remove fighters',
                    'Remove the selected fighter packs? Your saves will be kept.', parent=window): return
            logdir = Path(settings.values['data']) / 'logs'; logdir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            logfile = logdir / (action + '-' + stamp + '.log')
            cancel = logdir / (action + '-' + stamp + '.cancel')
            command = [sys.executable, '-u', str(Path(__file__).resolve()), '--build-dir', str(settings.build),
                       '--config', str(settings.file), '--worker', action, '--cancel-file', str(cancel), *names]
            state['process'] = subprocess.Popen(command, cwd=settings.root, env=settings.environment(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            state['cancel'] = cancel
            state['log'] = logfile
            state.update(action=action, error='', updated='')
            label = 'Launcher update' if action == 'launcher' else action.capitalize()
            output.delete('1.0', 'end'); status.set(label + ' running. Log: ' + str(logfile))
            for button in buttons: button.configure(state='disabled')
            cancel_button.configure(state='normal' if action in ('import', 'remove', 'launcher') else 'disabled',
                                    text='Cancel update' if action == 'launcher' else 'Cancel import')
            progress.configure(mode='indeterminate'); progress.start(12)
            process = state['process']
            def collect():
                with logfile.open('w', encoding='utf-8') as log:
                    for line in process.stdout:
                        log.write(line); log.flush(); events.put(('line', line))
                events.put(('done', process.wait()))
            threading.Thread(target=collect, daemon=True).start()
        except Exception as error: show_error(error)

    def button(parent, label, command):
        item = ttk.Button(parent, text=label, command=command); item.pack(side='left', padx=(0, 6))
        buttons.append(item); return item

    def first_setup():
        if state['process']: return
        source = filedialog.askopenfilename(parent=window, title='Choose your European Wii U TTT2 archive (update v16)',
                    filetypes=[('Wii U game archive', '*.wua')])
        if not source: return
        folder = filedialog.askdirectory(parent=window, title='Choose where to install TTT2 Ultimate')
        if not folder: return
        if not messagebox.askokcancel('Set Up Game',
                'The launcher will download missing tools, build the game from your archive, and install it. '
                'This first setup needs internet, at least 30 GB of free space and may take a while. '
                'Your original archive is kept. Continue?', parent=window): return
        fields['source'].set(source); fields['install'].set(folder)
        start('setup')

    release = dict(newer=None, checking=False, time=time.monotonic())  # (the first check is below, at the start)
    def show_update_notice():
        newer = release['newer']
        if launcher_exe and newer:
            notice_title.set('Version %s of the launcher is out' % newer.version)
            notice_detail.set('You have %s. Update replaces this launcher with it and opens it.' % self_update.version())
            if newer.page.startswith('https://') or (self_update.custom_releases() and newer.page): whats_new.grid()
            else: whats_new.grid_remove()
            update_button.configure(text='Update to ' + newer.version)
            notice.pack(fill='x', pady=(0, 10), before=tabs)
        else:
            notice.pack_forget(); update_button.configure(text='Check for Updates')
    def release_known(answer):
        # (A newer release without its .exe yet is not offered.)
        if answer.none: release['newer'] = None
        elif answer.release:
            newer = self_update.compare_versions(answer.release.version, self_update.version()) > 0
            release['newer'] = answer.release if newer else None
        show_update_notice()
    def check_release():
        if not launcher_exe or release['checking']: return
        release.update(checking=True, time=time.monotonic())
        def ask():
            # (Quietly: no notice when GitHub cannot be asked now.)
            try:
                answer = self_update.ask()
                if answer.error: print('Ultimate Launcher:', answer.error, flush=True)
            except Exception as error:
                print('Ultimate Launcher: GitHub cannot be asked for a newer version:', self_update.reason(error), flush=True)
                answer = None
            events.put(('release', answer))
        threading.Thread(target=ask, daemon=True).start()
    def open_release_page():
        if release['newer'] and release['newer'].page: webbrowser.open(release['newer'].page)
    def update_launcher():
        why = self_update.cannot_replace(launcher_exe)
        if why:
            return show_error('The launcher cannot update itself: its folder, %s, cannot be written to (%s). '
                              'Move it to a folder of yours, then update it.' % (launcher_exe.parent, why))
        start('launcher')

    button(bar, 'Set Up Game', first_setup)
    button(bar, 'Play', launch_game)
    button(bar, 'Build / Rebuild', lambda: start('build'))
    button(bar, 'Install from Wii U source', lambda: start('install'))
    button(bar, 'Update installed game', lambda: start('update'))
    button(bar, 'Refresh', refresh)
    ttk.Label(home, text='Fighters', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(14, 4))
    ttk.Label(home, text='Select fighters below. Importing uses your own Steam games and the shared character rules.').pack(anchor='w')
    tree = ttk.Treeview(home, columns=('fighter', 'game', 'status'), show='headings', height=9, selectmode='extended')
    for column, title, width in [('fighter', 'Fighter', 360), ('game', 'Source game', 140), ('status', 'Pack', 230)]:
        tree.heading(column, text=title); tree.column(column, width=width)
    tree.pack(fill='both', expand=True, pady=8)
    row = ttk.Frame(home); row.pack(fill='x')
    button(row, 'Import / Update selected', lambda: start('import', tree.selection()))
    button(row, 'Remove selected', lambda: start('remove', tree.selection()))
    button(row, 'Select Tekken 7', lambda: tree.selection_set([n for n in tree.get_children() if tree.set(n, 'game') == 'Tekken 7']))
    button(row, 'Select Tekken 8', lambda: tree.selection_set([n for n in tree.get_children() if tree.set(n, 'game') == 'Tekken 8']))

    descriptions = [('source', 'Wii U .wua archive', False), ('title', 'Extracted Wii U title (for development imports)', True),
                    ('install', 'Installation folder', True), ('data', 'User data folder (ends in TTT2Ultimate)', True),
                    ('packs', 'Fighter packs', True), ('saves', 'Save files', True), ('tools', 'Windows build tools folder', True)]
    paths_tab.columnconfigure(1, weight=1)
    for i, (key, label, directory) in enumerate(descriptions):
        ttk.Label(paths_tab, text=label).grid(row=i*2, column=0, columnspan=3, sticky='w', pady=(7, 2))
        ttk.Entry(paths_tab, textvariable=fields[key]).grid(row=i*2+1, column=0, columnspan=2, sticky='ew')
        def browse(k=key, folder=directory):
            value = filedialog.askdirectory(parent=window) if folder else filedialog.askopenfilename(parent=window,
                        filetypes=[('Wii U archive', '*.wua'), ('All files', '*.*')])
            if value: fields[k].set(value)
        ttk.Button(paths_tab, text='Browse…', command=browse).grid(row=i*2+1, column=2, padx=(8, 0))
    def save_clicked():
        try: save_paths(); refresh(); status.set('Paths saved.'); load_display()
        except Exception as error: show_error(error)
    ttk.Button(paths_tab, text='Save paths', command=save_clicked).grid(row=15, column=0, sticky='w', pady=12)

    display_values = {key: tk.BooleanVar(value=default) for key, default in
                      [('fullscreen', True), ('interpolation', True), ('input_delay', False)]}
    resolution = tk.StringVar(value='auto')
    for key, label in [('fullscreen', 'Fullscreen (F11 also switches in game)'),
                       ('interpolation', 'Frame interpolation on high refresh displays'),
                       ('input_delay', 'Original Wii U input delay')]:
        ttk.Checkbutton(display_tab, text=label, variable=display_values[key]).pack(anchor='w', pady=7)
    ttk.Label(display_tab, text='Rendering resolution').pack(anchor='w', pady=(12, 4))
    ttk.Combobox(display_tab, state='readonly', textvariable=resolution,
                 values=('auto', '1280x720', '1920x1080', '2560x1440', '3840x2160', '5120x2880')).pack(anchor='w')
    ttk.Label(display_tab, text='Keyboard mappings use the same keyboard.ini format as the game.\n'
              'Settings take effect the next time the game starts.', wraplength=800).pack(anchor='w', pady=14)
    def load_display():
        file = read_settings() / 'display.ini'
        if file.exists():
            for line in file.read_text(encoding='utf-8-sig').splitlines():
                key, separator, value = line.split('#', 1)[0].partition('=')
                key=key.strip(); value=value.strip()
                if separator and key in display_values: display_values[key].set(value in ('yes', 'true', '1'))
                if separator and key == 'resolution': resolution.set(value)
    def save_display():
        try:
            save_paths(); folder = read_settings(); folder.mkdir(parents=True, exist_ok=True)
            text = '# Written by Ultimate Launcher for Windows\n' + ''.join(
                key + ' = ' + ('yes' if value.get() else 'no') + '\n' for key, value in display_values.items())
            part = folder / 'display.ini.part'; part.write_text(text + 'resolution = ' + resolution.get() + '\n', encoding='utf-8')
            part.replace(folder / 'display.ini'); status.set('Display settings saved.')
        except Exception as error: show_error(error)
    def edit_keyboard():
        try:
            folder = read_settings(); folder.mkdir(parents=True, exist_ok=True)
            file = folder / 'keyboard.ini'
            if not file.exists(): file.write_text('# SDL key names, for example: face_bottom = J\n', encoding='utf-8')
            os.startfile(file)
        except Exception as error: show_error(error)
    settings_bar = ttk.Frame(display_tab); settings_bar.pack(anchor='w', pady=8)
    def performance_preset():
        resolution.set('1280x720')
        display_values['interpolation'].set(False)
        save_display()
    button(settings_bar, '720p performance preset', performance_preset)
    button(settings_bar, 'Save display settings', save_display)
    button(settings_bar, 'Edit keyboard mappings', edit_keyboard)

    ttk.Label(frame, textvariable=status, wraplength=940).pack(anchor='w', pady=(10, 4))
    progress = ttk.Progressbar(frame); progress.pack(fill='x')
    output = tk.Text(frame, height=8, wrap='word', font=('Consolas', 9)); output.pack(fill='both', pady=7)
    bottom = ttk.Frame(frame); bottom.pack(fill='x')
    def cancel():
        if state['cancel']:
            state['cancel'].touch()
            status.set('Stopping the update…' if state['action'] == 'launcher' else
                       'Stopping after the current operation; waiting for importer cleanup…')
            cancel_button.configure(state='disabled')
    cancel_button = ttk.Button(bottom, text='Cancel import', command=cancel, state='disabled'); cancel_button.pack(side='left')
    def open_logs():
        folder = Path(settings.values['data']) / 'logs'; folder.mkdir(parents=True, exist_ok=True); os.startfile(folder)
    def open_latest_log():
        try:
            logfile = state['log']
            if not logfile:
                folder = Path(settings.values['data']) / 'logs'
                logs = list(folder.glob('*.log'))
                if not logs: raise ValueError('No task logs yet. Run setup or an import first.')
                logfile = max(logs, key=lambda path: path.stat().st_mtime)
            os.startfile(logfile)
        except Exception as error: show_error(error)
    ttk.Button(bottom, text='Open latest log', command=open_latest_log).pack(side='right')
    ttk.Button(bottom, text='Open logs folder', command=open_logs).pack(side='right')
    def pump():
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == 'release':
                    release['checking'] = False
                    if payload: release_known(payload)
                elif kind == 'line':
                    if payload.startswith('@error '): state['error'] = payload[7:].strip()
                    elif payload.startswith('@launcher-updated '): state['updated'] = payload[18:].strip()
                    output.insert('end', payload); output.see('end')
                    if payload.startswith('@progress '):
                        words=payload.split()
                        try:
                            done, total = int(words[1]), int(words[2])
                            if total:
                                progress.stop(); progress.configure(mode='determinate', maximum=total, value=done)
                        except (ValueError, IndexError): pass
                    elif payload.startswith('@step '): status.set(payload[6:].strip())
                else:
                    state['process'] = None
                    progress.stop(); progress.configure(mode='determinate', maximum=100, value=100 if payload == 0 else 0)
                    cancel_button.configure(state='disabled')
                    for item in buttons: item.configure(state='normal')
                    # The installer may choose a child directory for a nonempty destination.
                    settings.values.update(json.loads(settings.file.read_text(encoding='utf-8')))
                    for key, value in settings.values.items(): fields[key].set(value)
                    if state['action'] != 'launcher':
                        status.set('Task complete.' if payload == 0 else 'Task stopped (code %s). See the saved log.' % payload)
                    elif payload == 130: status.set('Update cancelled. The launcher is as it was.')
                    elif payload != 0: status.set(state['error'] or 'Update failed (code %s). See the saved log.' % payload)
                    # (Else its last step says how it went.)
                    refresh()
                    if state['updated'] and payload == 0:
                        # The new launcher opens once this one has closed.
                        try:
                            self_update.open_updated(launcher_exe)
                            window.destroy(); return
                        except OSError as error:
                            status.set('Updated to %s, but it cannot be opened. Start the launcher again.' % state['updated'])
                            messagebox.showerror('Ultimate Launcher', 'Updated to %s, but it cannot be opened (%s). '
                                                 'Start the launcher again.' % (state['updated'], self_update.reason(error)),
                                                 parent=window)
                    elif state['error']:
                        messagebox.showerror('Update failed', state['error'], parent=window)
                    elif payload not in (0, 130):
                        messagebox.showerror('Task failed',
                            'The task could not finish. Your error details were saved to:\n\n' +
                            str(state['log']) + '\n\nClick Open latest log below and send that file for help. '
                            'After fixing the cause, run the task again; completed downloads are reused.', parent=window)
        except queue.Empty: pass
        window.after(100, pump)
    def close():
        if state['process']:
            messagebox.showinfo('Task running', 'Wait for this task to finish, or cancel the import first. '
                                'The launcher stays open so cleanup and logging can finish.', parent=window)
        else: window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    # A newer launcher is looked for when the window opens, and again when it
    # is back in front after a while.
    window.bind('<FocusIn>', lambda event: check_release()
                if time.monotonic() - release['time'] >= self_update.CHECK_SECONDS else None, add='+')
    refresh(); load_display(); pump()
    if launcher_exe and not args.ui_smoke_test: window.after(1000, check_release)
    smoke_errors = []
    if args.ui_smoke_test:
        def smoke_body():
            from ttt2char.characters import CHARACTERS
            assert len(tree.get_children()) == len(CHARACTERS)
            tree.selection_set(['reina']); assert tree.selection() == ('reina',)
            tabs.select(paths_tab); assert fields['packs'].get() == settings.values['packs']
            tabs.select(display_tab); assert resolution.get()
            tabs.select(home)
            args.ui_smoke_test.write_text(json.dumps(dict(window=window.title(), fighters=len(CHARACTERS), tabs=3,
                selected=list(tree.selection()), paths=settings.values), indent=2), encoding='utf-8')
        def smoke():
            try: smoke_body()
            except Exception as error: smoke_errors.append(error)
            finally: window.destroy()
        window.after(500, smoke)
    window.mainloop()
    if smoke_errors: raise smoke_errors[0]
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        text = traceback.format_exc()
        folder = Path(__file__).resolve().parents[2] / 'local'
        folder.mkdir(exist_ok=True)
        with (folder / 'windows-launcher-errors.log').open('a', encoding='utf-8') as log: log.write(text)
        if sys.stderr: sys.stderr.write(text)
        if sys.platform == 'win32' and not sys.stderr:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'The launcher could not start. See local/windows-launcher-errors.log.', 'Ultimate Launcher', 16)
        raise SystemExit(1)
