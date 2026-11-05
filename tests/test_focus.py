"""Focus session recovery, validation, and exactly-once completion."""
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from orbit import storage
from orbit.focus import FocusTimer


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=storage.SOURCE_ROOT)
        self.patch = patch.object(storage, 'DB', Path(self.temp.name) / 'test.sqlite3')
        self.patch.start()
        storage.initialize()
        self.timer = FocusTimer()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def overdue(self, task=None):
        self.timer.task = task
        self.timer.toggle()
        self.timer.deadline = time.time()-1
        self.timer.save()

    def test_reopen_completes_only_once(self):
        self.overdue()
        reopened = FocusTimer()
        self.assertTrue(reopened.finish_if_due())
        self.assertFalse(self.timer.finish_if_due())
        self.assertFalse(FocusTimer().finish_if_due())
        self.assertEqual(len(storage.Repository().snapshot()['sessions']), 1)

    def test_failed_commit_keeps_active_timer_and_no_session(self):
        self.overdue()
        with storage.connect() as con:
            con.execute("CREATE TRIGGER fail_session BEFORE INSERT ON sessions BEGIN SELECT RAISE(ABORT, 'Simulated failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.timer.finish_if_due()
        self.assertIsNotNone(self.timer.deadline)
        self.assertIsNotNone(storage.get_preference('focus')['deadline'])
        self.assertEqual(storage.Repository().snapshot()['sessions'], [])
        with storage.connect() as con:
            con.execute('DROP TRIGGER fail_session')
        self.assertTrue(self.timer.finish_if_due())
        self.assertEqual(len(storage.Repository().snapshot()['sessions']), 1)

    def test_deleted_linked_task_becomes_free_focus(self):
        repo = storage.Repository()
        ident = repo.save('tasks', {'title': 'Temporary task'})
        self.overdue(ident)
        repo.delete('tasks', ident)
        self.timer.finish_if_due()
        self.assertIsNone(repo.snapshot()['sessions'][0]['task_id'])

    def test_pause_resume_reset_and_duration(self):
        self.timer.set_duration(1)
        self.assertEqual(self.timer.text(), '01:00')
        self.timer.toggle()
        with self.assertRaises(ValueError):
            self.timer.set_duration(5)
        self.timer.toggle()
        self.assertIsNone(self.timer.deadline)
        self.assertGreater(self.timer.remaining, 0)
        self.timer.set_duration(5)
        self.timer.reset()
        self.assertEqual(self.timer.remaining, 300)
        self.assertEqual(storage.get_preference('focus')['remaining'], 300)

    def test_corrupt_timer_state_is_ignored(self):
        for deadline in [float('inf'), float('nan'), True, 'tomorrow', -1]:
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                self.timer.apply({'duration': 25, 'remaining': 1500, 'deadline': deadline})
        storage.set_preference('focus', {'duration': 'invalid'})
        reopened = FocusTimer()
        self.assertEqual(reopened.duration, 25)
        self.assertIsNone(reopened.deadline)

    def test_legacy_json_migration_happens_only_once(self):
        with storage.connect() as con:
            con.execute('DELETE FROM preferences')
        path = Path(self.temp.name) / 'focus-state.json'
        path.write_text(json.dumps({'duration': 45, 'remaining': 900, 'deadline': None, 'task': None}))
        migrated = FocusTimer(path)
        self.assertEqual(migrated.duration, 45)
        self.assertEqual(migrated.remaining, 900)
        storage.Repository().restore(storage.Repository().snapshot())
        reopened = FocusTimer(path)
        self.assertEqual(reopened.duration, 25)

    def test_restore_cannot_complete_old_timer(self):
        self.overdue()
        repo = storage.Repository()
        repo.restore(repo.snapshot())
        self.assertFalse(self.timer.finish_if_due())
        self.assertEqual(repo.snapshot()['sessions'], [])
