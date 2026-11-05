"""Persistent focus sessions with atomic, exactly-once completion."""
import json
import math
from pathlib import Path
import time
from uuid import uuid4

from . import storage


class FocusTimer:
    def __init__(self, legacy_file: Path | None = None):
        self.duration = 25
        self.remaining = 1500
        self.deadline = None
        self.task = None
        self.token = None
        self.reload()
        if not storage.get_preference('focus_migrated', False):
            if storage.get_preference('focus') is None and legacy_file and legacy_file.exists():
                try:
                    value = json.loads(legacy_file.read_text(encoding='utf-8'))
                    self.apply(value)
                    self.save()
                except (OSError, ValueError, TypeError, KeyError):
                    pass
            storage.set_preference('focus_migrated', True)

    def apply(self, value):
        if not isinstance(value, dict):
            raise ValueError('Invalid timer state.')
        duration, remaining = value.get('duration'), value.get('remaining')
        deadline, task = value.get('deadline'), value.get('task')
        if type(duration) is not int or not 1 <= duration <= 240:
            raise ValueError('Invalid duration.')
        if type(remaining) is not int or not 0 <= remaining <= duration*60:
            raise ValueError('Invalid remaining time.')
        if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0):
            raise ValueError('Invalid deadline.')
        if task is not None and (type(task) is not int or task < 1):
            raise ValueError('Invalid focus task.')
        self.duration, self.remaining, self.deadline, self.task = duration, remaining, deadline, task
        self.token = value.get('token') or (uuid4().hex if deadline else None)

    def value(self):
        return {'duration': self.duration, 'remaining': self.remaining, 'deadline': self.deadline,
                'task': self.task, 'token': self.token}

    def reload(self):
        value = storage.get_preference('focus')
        if value is not None:
            try:
                self.apply(value)
            except ValueError:
                pass

    def save(self):
        storage.set_preference('focus', self.value())

    def seconds(self):
        return max(0, math.ceil(self.deadline-time.time())) if self.deadline else self.remaining

    def text(self):
        seconds = self.seconds()
        return f'{seconds//60:02d}:{seconds%60:02d}'

    def toggle(self):
        if self.deadline:
            self.remaining = self.seconds()
            self.deadline = None
        else:
            if self.remaining <= 0:
                self.remaining = self.duration*60
            self.deadline = time.time()+self.remaining
            self.token = uuid4().hex
        self.save()

    def reset(self):
        self.deadline = None
        self.remaining = self.duration*60
        self.token = None
        self.save()

    def set_duration(self, minutes):
        if type(minutes) is not int or not 1 <= minutes <= 240 or self.deadline:
            raise ValueError('Pause the timer before choosing 1–240 minutes.')
        self.duration, self.remaining = minutes, minutes*60
        self.save()

    def finish_if_due(self):
        """Commit both the session and reset together, even across crash/restart."""
        if not self.deadline or self.deadline > time.time():
            return False
        completed = False
        with storage.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = storage.get_preference('focus', con=con)
            if current and current.get('token') == self.token and current.get('deadline') and current['deadline'] <= time.time():
                ident = current.get('task')
                if ident is not None and not con.execute('SELECT id FROM tasks WHERE id=?', (ident,)).fetchone():
                    ident = None
                con.execute('INSERT INTO sessions(task_id,minutes,created) VALUES(?,?,?)', (ident, current['duration'], storage.now()))
                current.update(deadline=None, remaining=current['duration']*60, token=None)
                storage.set_preference('focus', current, con)
                completed = True
        # Reload only after the commit; a failed transaction preserves the active state.
        if current:
            self.apply(current)
        else:
            self.deadline, self.token = None, None
            self.remaining = self.duration*60
        return completed
