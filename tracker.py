#!/usr/bin/env python3
"""Local Instagram JSON-export follower tracker (stdlib only)."""
import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE = Path(__file__).resolve().parent
FOLLOWERS_RE = re.compile(r'^followers(?:_\d+)?\.json$', re.I)
USERNAME_RE = re.compile(r'^[A-Za-z0-9._]{1,30}$')


def username_from(entry):
    fields = entry.get('string_list_data', [])
    candidates = [x.get('value', '') for x in fields if isinstance(x, dict)]
    candidates.append(entry.get('title', ''))
    for value in candidates:
        if isinstance(value, str) and USERNAME_RE.fullmatch(value.strip()):
            return value.strip().lower()
    for obj in fields:
        if not isinstance(obj, dict):
            continue
        href = obj.get('href', '')
        if isinstance(href, str):
            parsed = urlparse(href)
            if parsed.hostname in ('instagram.com', 'www.instagram.com'):
                parts = [unquote(p) for p in parsed.path.split('/') if p]
                if parts and parts[0] == '_u':
                    parts = parts[1:]
                if parts and USERNAME_RE.fullmatch(parts[0]):
                    return parts[0].lower()
    return None


def extract_records(raw, kind):
    data = json.loads(raw.decode('utf-8-sig'))
    if kind == 'following':
        if not isinstance(data, dict) or not isinstance(data.get('relationships_following'), list):
            raise ValueError('Unexpected following.json structure (expected relationships_following list)')
        items = data['relationships_following']
    else:
        if not isinstance(data, list):
            raise ValueError('Unexpected followers JSON structure (expected a list)')
        items = data
    result = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Unexpected entry in JSON export')
        name = username_from(item)
        if not name:
            raise ValueError('Could not read a username from an export entry; export format may have changed')
        result.add(name)
    return result


def load_export(path):
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise ValueError('Please supply an Instagram JSON export ZIP file')
    followers, following = set(), None
    follower_files = 0
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = Path(item.filename).name.lower()
            kind = 'followers' if FOLLOWERS_RE.fullmatch(name) else ('following' if name == 'following.json' else None)
            if kind is None:
                continue
            if item.file_size > 50_000_000:
                raise ValueError('A JSON export file is unexpectedly large')
            if kind == 'following' and following is not None:
                raise ValueError('Found multiple following.json files; use a ZIP for one Instagram account')
            payload = archive.read(item)
            names = extract_records(payload, kind)
            if kind == 'followers':
                followers.update(names)
                follower_files += 1
            else:
                following = names
    if follower_files == 0 or following is None:
        raise ValueError('Missing followers_N.json or following.json. Export Followers and following in JSON format, All time.')
    return followers, following


def connect(db):
    con = sqlite3.connect(db)
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS snapshots(
        id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL, filename TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE, followers_count INTEGER NOT NULL,
        following_count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS relationships(
        snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('followers','following')),
        username TEXT NOT NULL, PRIMARY KEY(snapshot_id,kind,username));
    ''')
    return con


def list_names(con, snapshot_id, kind):
    return {r[0] for r in con.execute('SELECT username FROM relationships WHERE snapshot_id=? AND kind=?', (snapshot_id, kind))}


def write_csv(path, names):
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['username', 'profile_url'])
        for username in sorted(names):
            writer.writerow([username, f'https://www.instagram.com/{username}/'])


def import_export(path, db, reports):
    path = Path(path)
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with connect(db) as con:
        if con.execute('SELECT 1 FROM snapshots WHERE sha256=?', (raw_hash,)).fetchone():
            print(f'Skipped already-imported ZIP: {path.name}')
            return False
    followers, following = load_export(path)
    reports.mkdir(parents=True, exist_ok=True)
    with connect(db) as con:
        prior = con.execute('SELECT id FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
        con.execute('INSERT INTO snapshots(imported_at,filename,sha256,followers_count,following_count) VALUES(?,?,?,?,?)',
                    (datetime.now(timezone.utc).isoformat(), path.name, raw_hash, len(followers), len(following)))
        snapshot_id = con.execute('SELECT last_insert_rowid()').fetchone()[0]
        con.executemany('INSERT INTO relationships VALUES(?,?,?)', [(snapshot_id, 'followers', u) for u in sorted(followers)] + [(snapshot_id, 'following', u) for u in sorted(following)])
        previous_followers = list_names(con, prior[0], 'followers') if prior else None
    output = reports / f'snapshot_{snapshot_id:04d}'
    output.mkdir(parents=True, exist_ok=True)
    not_following_back = following - followers
    write_csv(output / 'not_following_back.csv', not_following_back)
    write_csv(output / 'you_dont_follow_back.csv', followers - following)
    if previous_followers is not None:
        write_csv(output / 'lost_followers_since_previous_export.csv', previous_followers - followers)
        write_csv(output / 'new_followers_since_previous_export.csv', followers - previous_followers)
    summary = {'snapshot_id': snapshot_id, 'source': path.name, 'followers': len(followers), 'following': len(following),
               'not_following_back': len(not_following_back),
               'lost_followers_since_previous_export': len(previous_followers - followers) if previous_followers is not None else None,
               'warning': 'Lost follower differences can include deleted accounts or username changes; exports capture snapshots, not exact unfollow events.'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'Reports saved to: {output}')
    return True


def run_pending(inbox, db, reports):
    inbox.mkdir(parents=True, exist_ok=True)
    for path in sorted(inbox.glob('*.zip'), key=lambda p: (p.stat().st_mtime, p.name)):
        try:
            import_export(path, db, reports)
        except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile, sqlite3.Error) as error:
            print(f'Could not import {path.name}: {error}', file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description='Track Instagram followers from official JSON ZIP exports (no login required).')
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--import-zip', type=Path, metavar='ZIP', help='Import one export ZIP')
    modes.add_argument('--scan', action='store_true', help='Import all new ZIPs in inbox once')
    modes.add_argument('--watch', action='store_true', help='Poll inbox for new ZIPs')
    p.add_argument('--inbox', type=Path, default=BASE / 'inbox')
    p.add_argument('--db', type=Path, default=BASE / 'tracker.sqlite3')
    p.add_argument('--reports', type=Path, default=BASE / 'reports')
    p.add_argument('--interval', type=int, default=30, help='Polling interval in seconds (default 30)')
    a = p.parse_args()
    try:
        if a.import_zip:
            import_export(a.import_zip, a.db, a.reports)
        elif a.scan:
            run_pending(a.inbox, a.db, a.reports)
        else:
            if a.interval < 5:
                p.error('--interval must be at least 5 seconds')
            print(f'Watching {a.inbox} every {a.interval}s. Ctrl+C to stop.', flush=True)
            while True:
                run_pending(a.inbox, a.db, a.reports)
                time.sleep(a.interval)
    except KeyboardInterrupt:
        print('\nStopped.')
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile, sqlite3.Error) as error:
        p.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
