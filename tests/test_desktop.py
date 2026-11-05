"""Native UI workflows with an isolated database; no display required."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'
os.environ['XDG_CURRENT_DESKTOP'] = ''
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from orbit import desktop
from orbit.theme import LIGHT_STYLE


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle('Fusion')
        cls.application.setStyleSheet(LIGHT_STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=desktop.ROOT)
        self.db_patch = patch.object(desktop.store, 'DB', Path(self.temp.name) / 'test.sqlite3')
        self.timer_patch = patch.object(desktop, 'TIMER_FILE', Path(self.temp.name) / 'timer.json')
        self.db_patch.start()
        self.timer_patch.start()
        desktop.store.initialize()
        self.window = desktop.Orbit()
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        self.db_patch.stop()
        self.timer_patch.stop()
        self.temp.cleanup()

    def test_editors_board_and_notes(self):
        editor = desktop.Editor(self.window, 'projects')
        editor.title.setText('New project')
        editor.save()
        pid = self.window.data['projects'][0]['id']
        self.window.project = pid
        editor = desktop.Editor(self.window, 'tasks')
        editor.title.setText('Native task')
        editor.body.setPlainText('A real desktop workflow')
        editor.due.setText('2026-12-01')
        editor.save()
        task = self.window.data['tasks'][0]
        self.assertEqual(task['project_id'], pid)
        self.window.move_task(task['id'], 'doing')
        self.assertEqual(self.window.data['tasks'][0]['status'], 'doing')
        note = desktop.Editor(self.window, 'notes')
        note.title.setText('Ideas')
        note.body.setPlainText('Line one\nLine two')
        note.save()
        self.assertEqual(self.window.data['notes'][0]['body'], 'Line one\nLine two')
        for view in ('Overview', 'Task board', 'Notebook', 'Focus studio'):
            self.window.navigate(view)
            self.application.processEvents()
            self.assertFalse(self.window.grab().isNull())
        self.window.search.setText('nonexistent')
        self.assertEqual(self.window.tasks(), [])

    def test_invalid_editor_does_not_save(self):
        editor = desktop.Editor(self.window, 'tasks')
        editor.title.setText('Bad date')
        editor.due.setText('tomorrow')
        editor.save()
        self.assertTrue(editor.error.text())
        self.assertEqual(self.window.repo.snapshot()['tasks'], [])

    def test_timer_pause_persistence_and_completion(self):
        self.window.navigate('Focus studio')
        self.window.set_duration(1)
        self.window.toggle_timer()
        self.assertIsNotNone(self.window.timer.deadline)
        self.window.toggle_timer()
        self.assertIsNone(self.window.timer.deadline)
        self.assertGreater(self.window.timer.remaining, 0)
        self.window.timer.remaining = 42
        self.window.save_timer()
        self.window.timer.remaining = 0
        self.window.load_timer()
        self.assertEqual(self.window.timer.remaining, 42)
        self.window.timer.deadline = time.time() - 1
        self.window.save_timer()
        self.window.tick()
        self.assertIsNone(self.window.timer.deadline)
        self.assertEqual(len(self.window.repo.snapshot()['sessions']), 1)
        self.window.tick()
        self.assertEqual(len(self.window.repo.snapshot()['sessions']), 1)
        self.assertEqual(self.window.repo.snapshot()['sessions'][0]['minutes'], 1)

    def test_native_restore_rollback(self):
        self.window.repo.save('notes', {'title': 'Keep this', 'body': 'Original'})
        backup = self.window.repo.snapshot()
        invalid = dict(backup, tasks=[{'id': 1, 'title': 'Invalid', 'project_id': 999, 'created': desktop.store.now()}])
        with self.assertRaises(desktop.sqlite3.IntegrityError):
            self.window.repo.restore(invalid)
        self.assertEqual(self.window.repo.snapshot(), backup)
        self.window.repo.restore(backup)
        self.assertEqual(self.window.repo.snapshot(), backup)

    def test_move_undo_and_stale_undo(self):
        ident = self.window.repo.save('tasks', {'title': 'Move me'})
        self.window.refresh()
        self.window.move_task(ident, 'doing')
        self.assertTrue(self.window.undo_action.isEnabled())
        self.window.undo_move()
        self.assertEqual(self.window.data['tasks'][0]['status'], 'todo')
        self.window.move_task(ident, 'doing')
        self.window.repo.save('tasks', {'status': 'done'}, ident)
        self.window.undo_move()
        self.assertEqual(self.window.repo.snapshot()['tasks'][0]['status'], 'done')

    def test_filters_sorting_and_reset(self):
        from datetime import datetime, timedelta
        today = datetime.now().date()
        self.window.repo.save('tasks', {'title': 'Zulu', 'due': (today-timedelta(days=1)).isoformat(), 'priority': 'high'})
        self.window.repo.save('tasks', {'title': 'Alpha', 'due': today.isoformat(), 'priority': 'low'})
        self.window.refresh()
        self.window.date_filter = 'overdue'
        self.assertEqual([t['title'] for t in self.window.tasks()], ['Zulu'])
        self.window.date_filter = 'today'
        self.assertEqual([t['title'] for t in self.window.tasks()], ['Alpha'])
        self.window.clear_filters()
        self.window.sort_order = 'title'
        self.assertEqual([t['title'] for t in self.window.tasks()], ['Alpha', 'Zulu'])

    def test_dark_theme_and_compact_board(self):
        self.window.toggle_theme()
        self.assertEqual(desktop.store.get_preference('theme'), 'dark')
        self.assertTrue(self.window.dark_action.isChecked())
        self.window.repo.save('tasks', {'title': 'A very long task title '*10})
        self.window.refresh()
        self.window.navigate('Task board')
        self.window.resize(960, 700)
        self.application.processEvents()
        self.application.processEvents()
        self.assertTrue(self.window.compact)
        self.assertFalse(self.window.grab().isNull())
        self.window.toggle_theme()
        self.assertEqual(self.window.theme, 'light')

    def test_editor_discard_confirmation(self):
        from PyQt6.QtWidgets import QMessageBox
        editor = desktop.Editor(self.window, 'notes')
        editor.show()
        editor.title.setText('Unsaved idea')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
            editor.reject()
        self.assertTrue(editor.isVisible())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Discard):
            editor.reject()
        self.assertFalse(editor.isVisible())
        self.assertEqual(self.window.repo.snapshot()['notes'], [])


if __name__ == '__main__':
    unittest.main()
