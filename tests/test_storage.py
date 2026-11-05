"""Validation and durability guarantees at the persistence boundary."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from orbit import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=storage.SOURCE_ROOT)
        self.patch = patch.object(storage, 'DB', Path(self.temp.name) / 'test.sqlite3')
        self.patch.start()
        storage.initialize()
        self.repo = storage.Repository()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_migrations_are_repeatable_and_preserve_records(self):
        ident = self.repo.save('notes', {'title': 'Keep me', 'body': 'Original text'})
        storage.initialize()
        self.assertEqual(self.repo.snapshot()['notes'][0]['id'], ident)
        storage.set_preference('theme', 'dark')
        self.assertEqual(storage.get_preference('theme'), 'dark')

    def test_validation_rejects_invalid_types_and_dates(self):
        for values in [{'title': None}, {'title': 'x', 'status': []}, {'title': 'x', 'priority': {}},
                       {'title': 'x', 'project_id': True}, {'title': 'x', 'due': '2026-02-30'},
                       {'title': 'x', 'due': '2026-2-3'}, {'title': ' '}, {'title': 'x'*301}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.repo.save('tasks', values)
        with self.assertRaises(ValueError):
            self.repo.save('projects', {'name': 'X', 'color': 'red; background: black'})
        self.assertEqual(self.repo.snapshot()['tasks'], [])

    def test_missing_and_unknown_records_fail_cleanly(self):
        with self.assertRaises(ValueError):
            self.repo.save('notes', {'body': 'Missing title'})
        with self.assertRaises(ValueError):
            self.repo.save('tasks', {'title': 'X'}, 900)
        with self.assertRaises(ValueError):
            self.repo.delete('preferences', 1)

    def test_bad_backups_leave_workspace_and_timer_intact(self):
        self.repo.save('notes', {'title': 'Important', 'body': '<b>Plain text</b>'})
        backup = self.repo.snapshot()
        storage.set_preference('focus', {'sentinel': True})
        bad = []
        for body in [None, [], {}, {'notes': []}]:
            bad.append(body)
        for row in [
            {'id': 1, 'title': 'Missing timestamp'},
            {'id': -1, 'title': 'Bad ID', 'updated': storage.now()},
            {'id': 1, 'title': None, 'updated': storage.now()},
            {'id': 1, 'title': 'Bad timestamp', 'updated': 'yesterday'},
        ]:
            value = copy.deepcopy(backup)
            value['notes'] = [row]
            bad.append(value)
        value = copy.deepcopy(backup)
        value['notes'] *= 2
        bad.append(value)
        for value in bad:
            with self.subTest(value=value), self.assertRaises((ValueError, sqlite3.Error)):
                self.repo.restore(value)
            self.assertEqual(self.repo.snapshot(), backup)
            self.assertEqual(storage.get_preference('focus'), {'sentinel': True})

    def test_successful_restore_clears_focus_not_appearance(self):
        storage.set_preference('focus', {'task': 123})
        storage.set_preference('theme', 'dark')
        self.repo.restore(self.repo.snapshot())
        self.assertIsNone(storage.get_preference('focus'))
        self.assertEqual(storage.get_preference('theme'), 'dark')

    def test_foreign_key_failure_rolls_back_every_table(self):
        self.repo.save('notes', {'title': 'Keep'})
        original = self.repo.snapshot()
        broken = dict(original, tasks=[{'id': 1, 'title': 'Wrong link', 'project_id': 999, 'created': storage.now()}])
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.restore(broken)
        self.assertEqual(self.repo.snapshot(), original)

    def test_atomic_export_preserves_previous_file_on_failure(self):
        path = Path(self.temp.name) / 'backup.json'
        storage.atomic_json(path, {'first': 'café'})
        self.assertEqual(json.loads(path.read_text()), {'first': 'café'})
        with patch('orbit.storage.os.replace', side_effect=OSError('Disk unavailable')):
            with self.assertRaises(OSError):
                storage.atomic_json(path, {'second': True})
        self.assertEqual(json.loads(path.read_text()), {'first': 'café'})
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))
