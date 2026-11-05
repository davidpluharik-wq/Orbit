"""SQLite persistence, input validation, and atomic backup operations.

The default workspace stays beside app.py for compatibility with existing installs.
Set ORBIT_DATA_DIR to choose a different directory, including in packaged installs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

SOURCE_ROOT = Path(__file__).resolve().parents[1]
# Source checkouts remain portable. Installed packages use a writable user directory.
DEFAULT_ROOT = SOURCE_ROOT if (SOURCE_ROOT / 'app.py').is_file() else Path.home() / '.local' / 'share' / 'orbit'
ROOT = Path(os.environ.get('ORBIT_DATA_DIR', DEFAULT_ROOT)).expanduser().resolve()
DB = ROOT / 'orbit.sqlite3'
TABLES = ('projects', 'tasks', 'notes', 'sessions')
STATUSES = {'todo', 'doing', 'done'}
PRIORITIES = {'low', 'medium', 'high'}
FIELDS = {
    'projects': ('name', 'color'),
    'tasks': ('title', 'description', 'project_id', 'status', 'priority', 'due'),
    'notes': ('title', 'body'),
    'sessions': ('task_id', 'minutes'),
}
REQUIRED = {'projects': ('name',), 'tasks': ('title',), 'notes': ('title',), 'sessions': ('minutes',)}


@contextmanager
def connect():
    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL DEFAULT '#a6a1ff');
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'todo', priority TEXT NOT NULL DEFAULT 'medium',
            due TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
            minutes INTEGER NOT NULL, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS tasks_project_status ON tasks(project_id, status);
        CREATE INDEX IF NOT EXISTS sessions_created ON sessions(created);
        CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')


def now():
    return datetime.now(timezone.utc).isoformat()


def state(con):
    return {table: [dict(row) for row in con.execute(f'SELECT * FROM {table} ORDER BY id DESC')] for table in TABLES}


def clean(table, data, *, complete=False):
    """Validate a mutation or a complete imported record, without coercing bad types."""
    if table not in FIELDS or not isinstance(data, dict):
        raise ValueError('Invalid record type.')
    result = {key: data[key] for key in FIELDS[table] if key in data}
    if complete:
        for key in REQUIRED[table]:
            if key not in result:
                raise ValueError(f'{key} is required.')
    for key in ('title', 'name', 'description', 'body', 'color', 'due', 'status', 'priority'):
        if key in result and not isinstance(result[key], str):
            raise ValueError(f'{key} must be text.')
    for key in ('title', 'name'):
        if key in result:
            result[key] = result[key].strip()
            if not result[key] or len(result[key]) > 300:
                raise ValueError('Names and titles must contain 1–300 characters.')
    for key in ('description', 'body'):
        if len(result.get(key, '')) > 1_000_000:
            raise ValueError('Notes and descriptions must be under one million characters.')
    if 'color' in result and not re.fullmatch(r'#[0-9a-fA-F]{6}', result['color']):
        raise ValueError('Choose a valid project color.')
    if 'status' in result and result['status'] not in STATUSES:
        raise ValueError('Invalid task status.')
    if 'priority' in result and result['priority'] not in PRIORITIES:
        raise ValueError('Invalid priority.')
    if result.get('due'):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', result['due']):
            raise ValueError('Use YYYY-MM-DD for the due date.')
        try:
            datetime.strptime(result['due'], '%Y-%m-%d')
        except ValueError as exc:
            raise ValueError('Choose a valid calendar date.') from exc
    for key in ('project_id', 'task_id'):
        if key in result and result[key] is not None:
            if type(result[key]) is not int or result[key] < 1:
                raise ValueError('Invalid linked record.')
    if 'minutes' in result and (type(result['minutes']) is not int or not 1 <= result['minutes'] <= 240):
        raise ValueError('Session duration must be between 1 and 240 minutes.')
    return result


def get_preference(key, default=None, con=None):
    if con is None:
        with connect() as connection:
            return get_preference(key, default, connection)
    row = con.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row['value'])
    except (ValueError, TypeError):
        return default


def set_preference(key, value, con=None):
    if con is None:
        with connect() as connection:
            set_preference(key, value, connection)
        return
    con.execute('INSERT INTO preferences(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key, json.dumps(value, allow_nan=False)))


def restore_backup(con, data):
    """Restore four public tables atomically; the caller owns the transaction.

    Every record is validated before deletion. Preferences stay local, but the
    focus timer is cleared so it cannot refer to the replaced task identifiers.
    """
    if not isinstance(data, dict) or set(data) != set(TABLES) or any(not isinstance(data[t], list) for t in TABLES):
        raise ValueError('Select a valid Orbit JSON backup.')
    validated = {}
    for table in TABLES:
        validated[table] = []
        ids = set()
        for row in data[table]:
            if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] < 1 or row['id'] in ids:
                raise ValueError('Backup IDs must be unique positive integers.')
            ids.add(row['id'])
            values = clean(table, row, complete=True)
            values['id'] = row['id']
            timestamp = {'tasks': 'created', 'notes': 'updated', 'sessions': 'created'}.get(table)
            if timestamp:
                value = row.get(timestamp)
                if not isinstance(value, str):
                    raise ValueError(f'{timestamp} timestamp is required.')
                try:
                    parsed = datetime.fromisoformat(value)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    values[timestamp] = parsed.isoformat()
                except ValueError as exc:
                    raise ValueError('Invalid backup timestamp.') from exc
            validated[table].append(values)
    for table in reversed(TABLES):
        con.execute(f'DELETE FROM {table}')
    for table, records in validated.items():
        for values in records:
            con.execute(f'INSERT INTO {table} ({",".join(values)}) VALUES ({",".join("?" for _ in values)})', list(values.values()))
    con.execute("DELETE FROM preferences WHERE key='focus'")


def atomic_json(path, data):
    """Write a backup without truncating the previous file if writing fails."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(data, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Repository:
    """Small, validated boundary between desktop actions and SQL."""
    def snapshot(self):
        with connect() as con:
            return state(con)

    def save(self, table, values, ident=None):
        values = clean(table, values, complete=ident is None)
        if ident is None and table in ('tasks', 'sessions'):
            values['created'] = now()
        if table == 'notes':
            values['updated'] = now()
        with connect() as con:
            if ident is not None:
                if not con.execute(f'SELECT id FROM {table} WHERE id=?', (ident,)).fetchone():
                    raise ValueError('This item no longer exists.')
                if values:
                    con.execute(f'UPDATE {table} SET {",".join(k+"=?" for k in values)} WHERE id=?', [*values.values(), ident])
                return ident
            cursor = con.execute(f'INSERT INTO {table} ({",".join(values)}) VALUES ({",".join("?" for _ in values)})', list(values.values()))
            return cursor.lastrowid

    def delete(self, table, ident):
        if table not in TABLES:
            raise ValueError('Invalid record type.')
        with connect() as con:
            con.execute(f'DELETE FROM {table} WHERE id=?', (ident,))

    def restore(self, data):
        with connect() as con:
            restore_backup(con, data)
