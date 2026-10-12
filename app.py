"""Cross-platform desktop application for Instagram export follower comparisons."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tracker import connect, import_export, list_names

APP_NAME = 'Instagram Follower Tracker'


def storage_folder():
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        return root / 'InstagramFollowerTracker'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'InstagramFollowerTracker'
    return Path.home() / '.local' / 'share' / 'InstagramFollowerTracker'


DATA = storage_folder()
INBOX = DATA / 'inbox'
REPORTS = DATA / 'reports'
DB = DATA / 'tracker.sqlite3'


def open_folder(path):
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(str(path))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('900x640')
        self.minsize(760, 530)
        DATA.mkdir(parents=True, exist_ok=True)
        INBOX.mkdir(exist_ok=True)
        REPORTS.mkdir(exist_ok=True)
        self.events = queue.Queue()
        self.busy = False
        self.watch_enabled = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Ready. Select an official Instagram JSON export ZIP.')
        self.stats = tk.StringVar(value='No snapshots yet')
        self.category = tk.StringVar(value='Not following back')
        self.entries = []
        self.render()
        self.refresh()
        self.after(150, self.poll_events)
        self.after(1500, self.watch)

    def render(self):
        style = ttk.Style(self)
        style.configure('Heading.TLabel', font=('Arial', 18, 'bold'))
        style.configure('Info.TLabel', font=('Arial', 10))
        container = ttk.Frame(self, padding=18)
        container.pack(fill='both', expand=True)
        ttk.Label(container, text='Instagram Follower Tracker', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(container, text='Private, local analysis of official Instagram JSON exports. No account login required.', style='Info.TLabel').pack(anchor='w', pady=(4, 14))
        actions = ttk.Frame(container)
        actions.pack(fill='x', pady=(0, 10))
        self.import_button = ttk.Button(actions, text='Import Instagram ZIP…', command=self.choose_zip)
        self.import_button.pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Open Inbox', command=lambda: open_folder(INBOX)).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Open Reports', command=lambda: open_folder(REPORTS)).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Refresh', command=self.refresh).pack(side='left')
        ttk.Checkbutton(container, text='Automatically check Inbox every 30 seconds', variable=self.watch_enabled).pack(anchor='w', pady=(0, 12))
        ttk.Label(container, textvariable=self.stats).pack(anchor='w', pady=(0, 6))
        chooser = ttk.Frame(container)
        chooser.pack(fill='x', pady=(0, 10))
        ttk.Label(chooser, text='Show:').pack(side='left', padx=(0, 7))
        self.selector = ttk.Combobox(chooser, state='readonly', width=42, textvariable=self.category, values=[
            'Not following back', 'You do not follow back', 'Lost followers since previous export', 'New followers since previous export'])
        self.selector.pack(side='left')
        self.selector.bind('<<ComboboxSelected>>', lambda _e: self.show_names())
        ttk.Label(chooser, text='Search:').pack(side='left', padx=(20, 7))
        self.search = tk.StringVar()
        search_entry = ttk.Entry(chooser, textvariable=self.search)
        search_entry.pack(side='left', fill='x', expand=True)
        self.search.trace_add('write', lambda *_: self.apply_filter())
        frame = ttk.Frame(container)
        frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(frame, columns=('username',), show='headings', selectmode='browse')
        self.table.heading('username', text='Instagram username')
        self.table.column('username', anchor='w')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.table.bind('<Double-1>', self.open_selected)
        ttk.Label(container, text='Double-click a username to open their Instagram profile. Results are based on export snapshots; renames and deleted accounts can appear as lost followers.', wraplength=840).pack(anchor='w', pady=(8, 4))
        ttk.Separator(container).pack(fill='x', pady=(6, 8))
        ttk.Label(container, textvariable=self.status, wraplength=840).pack(anchor='w')

    def choose_zip(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(title='Choose Instagram JSON export ZIP', filetypes=[('ZIP archives', '*.zip')])
        if filename:
            self.start_import(Path(filename))

    def start_import(self, path):
        if self.busy:
            return
        self.busy = True
        self.import_button.configure(state='disabled')
        self.status.set(f'Importing {path.name}…')

        def worker():
            try:
                changed = import_export(path, DB, REPORTS)
                self.events.put(('imported', changed, path.name))
            except Exception as error:
                self.events.put(('error', str(error), path.name))

        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self):
        try:
            while True:
                kind, result, name = self.events.get_nowait()
                self.busy = False
                self.import_button.configure(state='normal')
                if kind == 'error':
                    self.status.set(f'Failed to import {name}: {result}')
                    messagebox.showerror('Import failed', f'{name}\n\n{result}')
                else:
                    self.status.set(f'{name}: ' + ('imported successfully.' if result else 'already imported; skipped.'))
                    self.refresh()
        except queue.Empty:
            pass
        self.after(150, self.poll_events)

    def watch(self):
        if self.watch_enabled.get() and not self.busy:
            # Names are not enough to determine whether a file was previously imported;
            # sha256 is validated by tracker.import_export. Avoid unnecessary repeated work
            # by recording processed file signatures for this application session.
            for item in sorted(INBOX.glob('*.zip')):
                try:
                    signature = (str(item), item.stat().st_size, item.stat().st_mtime_ns)
                except OSError:
                    continue
                if signature not in getattr(self, '_seen', set()):
                    self._seen = getattr(self, '_seen', set())
                    self._seen.add(signature)
                    self.start_import(item)
                    break
        self.after(30000, self.watch)

    def refresh(self):
        with connect(DB) as con:
            rows = con.execute('SELECT id, imported_at, followers_count, following_count FROM snapshots ORDER BY id DESC LIMIT 2').fetchall()
        if rows:
            item = rows[0]
            self.stats.set(f'Snapshot #{item[0]}  •  Followers: {item[2]:,}  •  Following: {item[3]:,}  •  Imported: {item[1][:19].replace("T", " ")} UTC')
        else:
            self.stats.set('No snapshots yet. Import your first ZIP to see results.')
        self.show_names()

    def show_names(self):
        with connect(DB) as con:
            rows = con.execute('SELECT id FROM snapshots ORDER BY id DESC LIMIT 2').fetchall()
            if not rows:
                self.entries = []
            else:
                current = rows[0][0]
                followers = list_names(con, current, 'followers')
                following = list_names(con, current, 'following')
                selected = self.category.get()
                if selected == 'Not following back':
                    self.entries = sorted(following - followers)
                elif selected == 'You do not follow back':
                    self.entries = sorted(followers - following)
                elif len(rows) == 1:
                    self.entries = []
                else:
                    previous = list_names(con, rows[1][0], 'followers')
                    self.entries = sorted((previous - followers) if selected.startswith('Lost') else (followers - previous))
        self.apply_filter()

    def apply_filter(self):
        needle = self.search.get().lower().strip()
        self.table.delete(*self.table.get_children())
        names = [name for name in self.entries if needle in name]
        for name in names:
            self.table.insert('', 'end', values=(name,))

    def open_selected(self, _event):
        chosen = self.table.selection()
        if chosen:
            username = self.table.item(chosen[0], 'values')[0]
            webbrowser.open(f'https://www.instagram.com/{username}/')


if __name__ == '__main__':
    Application().mainloop()
