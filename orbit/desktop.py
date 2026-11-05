"""Orbit's native Qt desktop interface. No HTTP server or browser is used."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer, QMimeData, QLockFile
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QDrag, QAction
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QComboBox, QDialog,
    QFormLayout, QTextEdit, QMessageBox, QFileDialog,
    QSpinBox, QProgressBar, QGridLayout, QSizePolicy, QCalendarWidget,
)
from . import storage as store
from .storage import Repository
from . import __version__
from .theme import apply_theme
from .focus import FocusTimer

ROOT = store.ROOT
ICON = Path(__file__).resolve().parent / 'resources' / 'orbit.svg'
TIMER_FILE = ROOT / 'focus-state.json'
STATUSES = {'todo': 'To do', 'doing': 'In progress', 'done': 'Completed'}


def label(text, style=None, wrap=False):
    widget = QLabel(str(text))
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if style:
        widget.setObjectName(style)
    return widget


def button(text, callback, style=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if style:
        widget.setObjectName(style)
    widget.setAccessibleName(text)
    widget.clicked.connect(lambda checked=False: callback())
    return widget


class TitleButton(QPushButton):
    """A keyboard-accessible title that cannot expand the board horizontally."""
    def __init__(self, text, callback):
        super().__init__(text.replace('&', '&&'))
        self.full_text = text
        self.setAccessibleName(text)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('border:none; text-align:left; padding:5px 3px; font-weight:600;')
        self.clicked.connect(lambda checked=False: callback())

    def resizeEvent(self, event):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, max(0, event.size().width()-14)).replace('&', '&&'))
        super().resizeEvent(event)


def panel(style='panel'):
    widget = QFrame()
    widget.setObjectName(style)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(14)
    return widget, layout


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class Editor(QDialog):
    def __init__(self, window, table, record=None, status='todo'):
        super().__init__(window)
        self.window, self.table, self.record = window, table, record or {}
        self.setWindowTitle(('Edit ' if record else 'New ') + {'tasks': 'task', 'notes': 'note', 'projects': 'project'}[table])
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(18)
        layout.addWidget(label(self.windowTitle(), 'section'))
        form = QFormLayout()
        form.setSpacing(13)
        self.title = QLineEdit(self.record.get('title', self.record.get('name', '')))
        self.title.setMaxLength(300)
        self.title.setPlaceholderText('Give it a name…')
        form.addRow('Name' if table == 'projects' else 'Title', self.title)
        if table in ('tasks', 'notes'):
            self.body = QTextEdit()
            self.body.setAcceptRichText(False)
            self.body.setPlainText(self.record.get('description' if table == 'tasks' else 'body', ''))
            self.body.setMinimumHeight(180 if table == 'tasks' else 300)
            form.addRow('Details' if table == 'tasks' else 'Your note', self.body)
        if table == 'tasks':
            self.project = QComboBox()
            self.project.addItem('Personal · no project', None)
            for project in window.data['projects']:
                self.project.addItem(project['name'], project['id'])
            self.project.setCurrentIndex(max(0, self.project.findData(self.record.get('project_id', window.project))))
            self.status = QComboBox()
            for key, value in STATUSES.items():
                self.status.addItem(value, key)
            self.status.setCurrentIndex(self.status.findData(self.record.get('status', status)))
            self.priority = QComboBox()
            for key in ('low', 'medium', 'high'):
                self.priority.addItem(key.capitalize(), key)
            self.priority.setCurrentIndex(self.priority.findData(self.record.get('priority', 'medium')))
            self.due = QLineEdit(self.record.get('due', ''))
            self.due.setPlaceholderText('YYYY-MM-DD · leave empty for no deadline')
            form.addRow('Project', self.project)
            form.addRow('Status', self.status)
            form.addRow('Priority', self.priority)
            due_row = QHBoxLayout()
            due_row.addWidget(self.due, 1)
            due_row.addWidget(button('▦', self.choose_date))
            form.addRow('Due date', due_row)
        if table == 'projects':
            self.color = QComboBox()
            for name, color in [('Lavender', '#a6a1ff'), ('Sage', '#75b9a5'), ('Peach', '#e6a08b'), ('Sky', '#7eafe2'), ('Rose', '#cc8fba')]:
                self.color.addItem(name, color)
            idx = self.color.findData(self.record.get('color', '#a6a1ff'))
            if idx < 0:
                self.color.addItem('Custom', self.record['color'])
                idx = self.color.count() - 1
            self.color.setCurrentIndex(idx)
            form.addRow('Color', self.color)
        layout.addLayout(form)
        self.error = label('', 'muted', True)
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        if record:
            actions.addWidget(button('Delete', self.remove, 'danger'))
        actions.addStretch()
        actions.addWidget(button('Cancel', self.reject))
        actions.addWidget(button('Save changes ↗', self.save, 'primary'))
        layout.addLayout(actions)
        self.title.setFocus()
        self.initial_values = self.values()
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self.save)

    def choose_date(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Choose a due date')
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget()
        layout.addWidget(calendar)
        actions = QHBoxLayout()
        actions.addWidget(button('No deadline', lambda: (self.due.clear(), dialog.accept())))
        actions.addStretch()
        actions.addWidget(button('Choose date', lambda: (self.due.setText(calendar.selectedDate().toString('yyyy-MM-dd')), dialog.accept()), 'primary'))
        layout.addLayout(actions)
        dialog.exec()

    def reject(self):
        if self.values() != self.initial_values:
            if QMessageBox.question(self, 'Discard changes?', 'You have unsaved changes. Discard them?',
                                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
                return
        super().reject()

    def values(self):
        values = {'name' if self.table == 'projects' else 'title': self.title.text()}
        if self.table == 'tasks':
            values.update(description=self.body.toPlainText(), project_id=self.project.currentData(),
                          status=self.status.currentData(), priority=self.priority.currentData(), due=self.due.text().strip())
        elif self.table == 'notes':
            values['body'] = self.body.toPlainText()
        else:
            values['color'] = self.color.currentData()
        return values

    def save(self):
        try:
            self.window.repo.save(self.table, self.values(), self.record.get('id'))
        except (ValueError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            return
        self.window.refresh()
        self.accept()

    def remove(self):
        text = 'Delete this project? Its tasks will move to Personal.' if self.table == 'projects' else 'Permanently delete this item?'
        if QMessageBox.question(self, 'Delete item', text) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.window.repo.delete(self.table, self.record['id'])
            self.window.undo_stack.clear()
            if self.table == 'projects' and self.window.project == self.record['id']:
                self.window.project = None
            self.window.refresh()
            self.accept()
        except sqlite3.Error as exc:
            self.error.setText(str(exc))


class TaskCard(QFrame):
    def __init__(self, window, task):
        super().__init__()
        self.window, self.task, self.start = window, task, None
        self.setObjectName('card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        tag = label(task['priority'].upper(), 'eyebrow')
        tag.setStyleSheet('color: '+{'high': '#c07876', 'medium': '#b4975f', 'low': '#68a48d'}[task['priority']])
        layout.addWidget(tag)
        edit = TitleButton(task['title'], lambda: window.edit('tasks', task))
        edit.setStyleSheet('border:none; font-weight:600; text-align:left; padding:5px 0;')
        edit.setToolTip(task['title'])
        layout.addWidget(edit)
        if task['description']:
            layout.addWidget(label(task['description'][:130], 'muted', True))
        layout.addWidget(label(window.project_name(task['project_id']), 'muted', True))
        bottom = QHBoxLayout()
        due = label(task['due'] or 'No due date', 'muted')
        if task['due'] and task['due'] < datetime.now().date().isoformat() and task['status'] != 'done':
            due.setStyleSheet('color: #be6e78')
        bottom.addWidget(due)
        bottom.addStretch()
        status = QComboBox()
        for key, value in STATUSES.items():
            status.addItem(value, key)
        status.setCurrentIndex(status.findData(task['status']))
        status.setStyleSheet('font-size:10px; padding:5px;')
        status.currentIndexChanged.connect(lambda: window.move_task(task['id'], status.currentData()))
        bottom.addWidget(status)
        layout.addLayout(bottom)
        self.setToolTip('Drag the card background to another column, or use the status menu.')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self.start).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData('application/x-orbit-task', str(self.task['id']).encode())
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
                self.start = None
        super().mouseMoveEvent(event)


class TaskColumn(QFrame):
    def __init__(self, window, status):
        super().__init__()
        self.window, self.status = window, status
        self.setObjectName('column')
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-orbit-task'):
            event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            ident = int(bytes(event.mimeData().data('application/x-orbit-task')))
            self.window.move_task(ident, self.status)
            event.acceptProposedAction()
        except ValueError:
            pass


class Orbit(QMainWindow):
    def __init__(self):
        super().__init__()
        self.repo = Repository()
        self.data = self.repo.snapshot()
        self.view, self.project, self.priority, self.query = 'Overview', None, '', ''
        self.timer = FocusTimer(TIMER_FILE)
        self.theme = store.get_preference('theme', 'light')
        apply_theme(QApplication.instance(), self.theme)
        self.date_filter, self.sort_order = '', 'due'
        self.undo_stack = []
        self.setWindowTitle('Orbit — Your personal workspace')
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1280, 860)
        self.setMinimumSize(960, 650)
        self.compact = False
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(225)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 25)
        side.setSpacing(9)
        brand = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QIcon(str(ICON)).pixmap(36, 36))
        brand.addWidget(icon)
        brand.addWidget(label('orbit.', 'brand'))
        brand.addStretch()
        side.addLayout(brand)
        side.addSpacing(29)
        side.addWidget(label('PERSONAL WORKSPACE', 'eyebrow'))
        self.nav = {}
        for name, symbol in [('Overview', '◫'), ('Task board', '▦'), ('Notebook', '▤'), ('Focus studio', '◷')]:
            btn = button(f'{symbol}    {name}', lambda name=name: self.navigate(name), 'nav')
            btn.setCheckable(True)
            self.nav[name] = btn
            side.addWidget(btn)
        side.addSpacing(20)
        project_heading = QHBoxLayout()
        project_heading.addWidget(label('PROJECTS', 'eyebrow'))
        project_heading.addStretch()
        project_heading.addWidget(button('+', lambda: self.edit('projects')))
        side.addLayout(project_heading)
        self.project_layout = QVBoxLayout()
        project_scroll = QScrollArea()
        project_scroll.setWidgetResizable(True)
        project_widget = QWidget()
        project_widget.setObjectName("project-list")
        project_widget.setLayout(self.project_layout)
        project_scroll.setWidget(project_widget)
        side.addWidget(project_scroll, 1)
        side.addWidget(label('●  Local & private', 'muted'))
        side.addWidget(label('Your work stays on this computer.', 'muted', True))
        side.addSpacing(9)
        side.addWidget(button('↓  Export backup', self.export_backup))
        side.addWidget(button('↑  Restore backup', self.restore_backup))
        shell.addWidget(sidebar)
        workspace = QWidget()
        workspace.setObjectName('workspace')
        work = QVBoxLayout(workspace)
        work.setContentsMargins(32, 20, 32, 16)
        work.setSpacing(20)
        top = QHBoxLayout()
        self.breadcrumb = label('Workspace / Overview', 'muted')
        top.addWidget(self.breadcrumb)
        top.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search tasks & notes…  Ctrl+K')
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(280)
        self.search_delay = QTimer(self)
        self.search_delay.setSingleShot(True)
        self.search_delay.setInterval(140)
        self.search_delay.timeout.connect(self.render)
        self.search.textChanged.connect(self.search_changed)
        top.addWidget(self.search)
        work.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        work.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        footer.addWidget(label('Small steps. Meaningful progress.', 'muted'))
        footer.addStretch()
        footer.addWidget(label('ORBIT  /  DESKTOP EDITION', 'eyebrow'))
        work.addLayout(footer)
        shell.addWidget(workspace, 1)
        self.statusBar().showMessage('All changes are saved automatically.')
        QShortcut(QKeySequence('Ctrl+K'), self, activated=self.search.setFocus)
        QShortcut(QKeySequence('Ctrl+N'), self, activated=lambda: self.edit('notes' if self.view == 'Notebook' else 'tasks'))
        self.create_menus()
        geometry = store.get_preference('geometry')
        if isinstance(geometry, str):
            from PyQt6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.tick)
        self.ticker.start(250)
        self.render()

    def create_menus(self):
        def action(menu, title, callback, shortcut=None):
            item = QAction(title, self)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            item.triggered.connect(lambda checked=False: callback())
            menu.addAction(item)
            return item
        file_menu = self.menuBar().addMenu('&File')
        action(file_menu, 'New task…', lambda: self.edit('tasks'))
        action(file_menu, 'New note…', lambda: self.edit('notes'), 'Ctrl+Shift+N')
        action(file_menu, 'New project…', lambda: self.edit('projects'))
        file_menu.addSeparator()
        action(file_menu, 'Export backup…', self.export_backup, 'Ctrl+Shift+E')
        action(file_menu, 'Restore backup…', self.restore_backup)
        file_menu.addSeparator()
        action(file_menu, 'Quit', self.close, 'Ctrl+Q')
        edit_menu = self.menuBar().addMenu('&Edit')
        self.undo_action = action(edit_menu, 'Undo task move', self.undo_move, 'Ctrl+Z')
        self.undo_action.setEnabled(False)
        action(edit_menu, 'Clear all filters', self.clear_filters, 'Ctrl+Shift+F')
        view_menu = self.menuBar().addMenu('&View')
        for index, view in enumerate(self.nav, 1):
            action(view_menu, view, lambda view=view: self.navigate(view), f'Ctrl+{index}')
        view_menu.addSeparator()
        self.dark_action = action(view_menu, 'Dark appearance', self.toggle_theme, 'Ctrl+Shift+D')
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.theme == 'dark')
        help_menu = self.menuBar().addMenu('&Help')
        action(help_menu, 'Keyboard shortcuts', self.show_shortcuts, 'F1')
        action(help_menu, 'About Orbit', self.about)

    def show_shortcuts(self):
        QMessageBox.information(self, 'Keyboard shortcuts',
            'Ctrl+N     New task / note in Notebook\n'
            'Ctrl+Shift+N     New note\nCtrl+K     Search\n'
            'Ctrl+1…4     Switch workspace\nCtrl+Z     Undo task move\n'
            'Ctrl+Shift+F     Clear filters\nCtrl+Shift+D     Toggle dark appearance\n'
            'Ctrl+Shift+E     Export backup\nCtrl+Enter     Save editor\n'
            'Escape     Close editor (prompts for unsaved changes)\nCtrl+Q     Quit')

    def about(self):
        QMessageBox.about(self, 'About Orbit',
            f'<h2>Orbit {__version__}</h2><p>A little clarity for meaningful work.</p>'
            '<p>A native Python workspace for projects, notes, and focus.</p>'
            '<p>Your data stays on your computer. No accounts, tracking, or network access.</p>'
            '<p>Built with Python, Qt / PyQt6, and SQLite.<br>Licensed under GPL-3.0-only.</p>')

    def toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        store.set_preference('theme', self.theme)
        apply_theme(QApplication.instance(), self.theme)
        self.dark_action.setChecked(self.theme == 'dark')
        self.render()

    def clear_filters(self):
        self.project, self.priority, self.date_filter, self.query = None, '', '', ''
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.search_delay.stop()
        self.render()

    def undo_move(self):
        if not self.undo_stack:
            return
        ident, before, after = self.undo_stack.pop()
        current = next((t for t in self.repo.snapshot()['tasks'] if t['id'] == ident), None)
        if current and current['status'] == after:
            self.repo.save('tasks', {'status': before}, ident)
            self.refresh()
            self.statusBar().showMessage('Task move undone.', 5000)
        else:
            self.undo_action.setEnabled(bool(self.undo_stack))
            self.statusBar().showMessage('This task has changed. Its current state was kept.', 5000)

    def project_name(self, ident):
        return next((p['name'] for p in self.data['projects'] if p['id'] == ident), 'Personal')

    def navigate(self, view):
        self.view = view
        self.render()

    def search_changed(self, text):
        self.query = text.casefold().strip()
        if self.view == 'Focus studio' and self.query:
            self.view = 'Task board'
        self.search_delay.start()

    def select_project(self, ident):
        self.project = ident
        self.navigate('Task board')

    def refresh(self):
        self.data = self.repo.snapshot()
        self.render()

    def tasks(self):
        today = datetime.now().date().isoformat()
        week = (datetime.now().date()+timedelta(days=7)).isoformat()
        def matches(task):
            due = task['due']
            date_match = (not self.date_filter or
                          (self.date_filter == 'overdue' and due and due < today and task['status'] != 'done') or
                          (self.date_filter == 'today' and due == today) or
                          (self.date_filter == 'week' and due and today <= due <= week) or
                          (self.date_filter == 'none' and not due))
            return (date_match and (self.project is None or task['project_id'] == self.project)
                    and (not self.priority or task['priority'] == self.priority)
                    and (not self.query or self.query in (task['title']+' '+task['description']+' '+self.project_name(task['project_id'])).casefold()))
        result = [task for task in self.data['tasks'] if matches(task)]
        keys = {
            'due': lambda task: (task['due'] or '9999', {'high': 0, 'medium': 1, 'low': 2}[task['priority']], -task['id']),
            'priority': lambda task: ({'high': 0, 'medium': 1, 'low': 2}[task['priority']], task['due'] or '9999'),
            'title': lambda task: task['title'].casefold(),
            'newest': lambda task: -task['id'],
        }
        return sorted(result, key=keys[self.sort_order])

    def edit(self, table, record=None, status='todo'):
        Editor(self, table, record, status).exec()

    def move_task(self, ident, status):
        try:
            task = next((t for t in self.data['tasks'] if t['id'] == ident), None)
            if not task or task['status'] == status:
                return
            self.repo.save('tasks', {'status': status}, ident)
            self.undo_stack.append((ident, task['status'], status))
            self.undo_stack = self.undo_stack[-30:]
            self.refresh()
            self.statusBar().showMessage('Task moved. Ctrl+Z to undo.', 6000)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, 'Could not save task', str(exc))

    def render(self):
        self.undo_action.setEnabled(bool(self.undo_stack))
        for name, btn in self.nav.items():
            btn.setChecked(name == self.view)
        clear_layout(self.project_layout)
        all_projects = button('All projects', lambda: self.select_project(None), 'nav')
        all_projects.setCheckable(True)
        all_projects.setChecked(self.project is None)
        self.project_layout.addWidget(all_projects)
        for project in self.data['projects']:
            row = QHBoxLayout()
            dot = label('●')
            color = project['color']
            if len(color) != 7 or not color.startswith('#') or any(c not in '0123456789abcdefABCDEF' for c in color[1:]):
                color = '#a6a1ff'
            dot.setStyleSheet(f'color:{color};')
            row.addWidget(dot)
            pbtn = TitleButton(project['name'], lambda p=project: self.select_project(p['id']))
            pbtn.setObjectName('nav')
            pbtn.setToolTip(project['name'])
            pbtn.setCheckable(True)
            pbtn.setChecked(project['id'] == self.project)
            row.addWidget(pbtn, 1)
            edit = button('⋯', lambda p=project: self.edit('projects', p))
            edit.setToolTip('Edit project')
            edit.setFixedWidth(32)
            edit.setStyleSheet('padding:4px; border:none;')
            row.addWidget(edit)
            self.project_layout.addLayout(row)
        self.project_layout.addStretch()
        self.breadcrumb.setText('Workspace / '+self.view+(' / '+self.project_name(self.project) if self.project else ''))
        scroll_position = self.scroll.verticalScrollBar().value()
        body = QWidget()
        body.setObjectName('workspace')
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 15, 6, 10)
        self.body.setSpacing(24)
        previous = self.scroll.takeWidget()
        self.scroll.setWidget(body)
        if previous:
            previous.deleteLater()
        self.clock = None
        if self.view == 'Overview':
            self.overview()
        elif self.view == 'Task board':
            self.board()
        elif self.view == 'Notebook':
            self.notebook()
        else:
            self.focus()
        self.body.addStretch()
        if self.view == 'Task board':
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_position))

    def heading(self, eyebrow, title, subtitle, action=None):
        self.body.addWidget(label(eyebrow, 'eyebrow'))
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label(title, 'title', True))
        text.addWidget(label(subtitle, 'muted', True))
        row.addLayout(text, 1)
        if action:
            row.addWidget(button(action[0], action[1], 'primary'))
        self.body.addLayout(row)

    def empty(self, layout, text):
        note = label('✧  '+text, 'muted', True)
        note.setContentsMargins(6, 20, 6, 20)
        layout.addWidget(note)

    def task_row(self, layout, task):
        row = QHBoxLayout()
        check = button('✓' if task['status'] == 'done' else '○', lambda: self.move_task(task['id'], 'todo' if task['status'] == 'done' else 'done'))
        check.setFixedWidth(38)
        check.setToolTip('Reopen task' if task['status'] == 'done' else 'Complete task')
        row.addWidget(check)
        text = QVBoxLayout()
        edit = TitleButton(task['title'], lambda: self.edit('tasks', task))
        edit.setStyleSheet('border:none; text-align:left; padding:4px; font-weight:600;')
        text.addWidget(edit)
        text.addWidget(label(' '+self.project_name(task['project_id'])+(' · '+task['due'] if task['due'] else ''), 'muted'))
        row.addLayout(text, 1)
        row.addWidget(label(task['priority'].upper(), 'eyebrow'))
        layout.addLayout(row)

    def overview(self):
        self.heading(datetime.now().strftime('%A, %B %d').upper(), 'Make room for meaningful work.',
                     'A little clarity for everything you’re working toward.', ('+ New task', lambda: self.edit('tasks')))
        tasks = self.tasks()
        done = sum(t['status'] == 'done' for t in tasks)
        minutes = sum(s['minutes'] for s in self.data['sessions'] if datetime.fromisoformat(s['created']).astimezone().date() == datetime.now().date())
        stats = QHBoxLayout()
        for title, value, caption in [('Open tasks', len(tasks)-done, 'Your next steps, in one place'), ('Completed', done, 'Small wins add up'), ('Focus today', f'{minutes} min', 'Time for what matters'), ('Projects', len(self.data['projects']), 'Big ideas, organized')]:
            card, col = panel()
            col.addWidget(label(title, 'muted'))
            col.addWidget(label(value, 'value'))
            col.addWidget(label(caption, 'muted', True))
            stats.addWidget(card)
        self.body.addLayout(stats)
        if self.project is not None or self.priority or self.date_filter or self.query:
            self.body.addWidget(button('Filtered workspace · Clear filters', self.clear_filters))
        columns = QHBoxLayout()
        left, left_col = panel()
        left_col.addWidget(label('Your next steps', 'section'))
        pending = sorted((t for t in tasks if t['status'] != 'done'), key=lambda t: (t['due'] or '9999', {'high': 0, 'medium': 1, 'low': 2}[t['priority']]))
        for task in pending[:6]:
            self.task_row(left_col, task)
        if not pending:
            self.empty(left_col, 'A clear space for your next step. Create a task to get started.')
        left_col.addStretch()
        left_col.addWidget(button('View task board ↗', lambda: self.navigate('Task board')))
        columns.addWidget(left, 3)
        hero, hero_col = panel('hero')
        hero_col.addWidget(label('A MOMENT OF FOCUS', 'eyebrow'))
        hero_col.addWidget(label('One thing at a time.\nThat’s how things happen.', 'section', True))
        hero_col.addWidget(label('Give your next task a little undivided attention. The rest can wait.', 'muted', True))
        hero_col.addStretch()
        hero_col.addWidget(button('Enter focus studio ↗', lambda: self.navigate('Focus studio'), 'primary'))
        columns.addWidget(hero, 2)
        self.body.addLayout(columns)
        projects, col = panel()
        col.addWidget(label('Project pulse', 'section'))
        for project in self.data['projects']:
            ts = [t for t in self.data['tasks'] if t['project_id'] == project['id']]
            n = sum(t['status'] == 'done' for t in ts)
            row = QHBoxLayout()
            row.addWidget(button(project['name'], lambda p=project: self.select_project(p['id'])))
            row.addStretch()
            row.addWidget(label(f'{n} of {len(ts)} complete', 'muted'))
            col.addLayout(row)
            progress = QProgressBar()
            progress.setRange(0, max(1, len(ts)))
            progress.setValue(n)
            progress.setTextVisible(False)
            col.addWidget(progress)
        if not self.data['projects']:
            self.empty(col, 'Your next chapter starts here. Create a project using the + in the sidebar.')
        self.body.addWidget(projects)

    def board(self):
        self.heading('A LITTLE STRUCTURE, A LOT OF POSSIBILITY', self.project_name(self.project) if self.project else 'Your task board',
                     'Move work forward. Drag cards between columns or use the status menus.', ('+ New task', lambda: self.edit('tasks')))
        filters = QHBoxLayout()
        project_filter = QComboBox()
        project_filter.addItem('All projects', None)
        for p in self.data['projects']:
            project_filter.addItem(p['name'], p['id'])
        project_filter.setCurrentIndex(max(0, project_filter.findData(self.project)))
        project_filter.currentIndexChanged.connect(lambda: self.select_project(project_filter.currentData()))
        filters.addWidget(project_filter)
        priority_filter = QComboBox()
        priority_filter.addItem('All priorities', '')
        for priority in ('high', 'medium', 'low'):
            priority_filter.addItem(priority.capitalize(), priority)
        priority_filter.setCurrentIndex(priority_filter.findData(self.priority))
        priority_filter.currentIndexChanged.connect(lambda: self.filter_priority(priority_filter.currentData()))
        filters.addWidget(priority_filter)
        date_filter = QComboBox()
        for title, value in [('All dates', ''), ('Overdue', 'overdue'), ('Due today', 'today'), ('Next 7 days', 'week'), ('No deadline', 'none')]:
            date_filter.addItem(title, value)
        date_filter.setCurrentIndex(date_filter.findData(self.date_filter))
        date_filter.currentIndexChanged.connect(lambda: self.set_filter('date_filter', date_filter.currentData()))
        filters.addWidget(date_filter)
        sort = QComboBox()
        for title, value in [('Sort: due date', 'due'), ('Sort: priority', 'priority'), ('Sort: title', 'title'), ('Sort: newest', 'newest')]:
            sort.addItem(title, value)
        sort.setCurrentIndex(sort.findData(self.sort_order))
        sort.currentIndexChanged.connect(lambda: self.set_filter('sort_order', sort.currentData()))
        filters.addWidget(sort)
        clear = button('Reset', self.clear_filters)
        clear.setToolTip('Clear project, priority, date, and search filters')
        filters.addWidget(clear)
        filters.addStretch()
        filters.addWidget(label(f'{len(self.tasks())} tasks', 'muted'))
        self.body.addLayout(filters)
        board = QVBoxLayout() if self.compact else QHBoxLayout()
        board.setSpacing(16)
        for status, title in STATUSES.items():
            column = TaskColumn(self, status)
            col = QVBoxLayout(column)
            col.setContentsMargins(13, 15, 13, 15)
            col.setSpacing(13)
            tasks = [t for t in self.tasks() if t['status'] == status]
            head = QHBoxLayout()
            head.addWidget(label(f'{title}  ·  {len(tasks)}', 'section'))
            head.addStretch()
            head.addWidget(button('+', lambda s=status: self.edit('tasks', status=s)))
            col.addLayout(head)
            for task in tasks:
                col.addWidget(TaskCard(self, task))
            if not tasks:
                self.empty(col, 'Room for your next step.')
            col.addStretch()
            board.addWidget(column, 1)
        self.body.addLayout(board)

    def set_filter(self, name, value):
        setattr(self, name, value)
        self.render()

    def filter_priority(self, value):
        self.priority = value
        self.render()

    def notebook(self):
        self.heading('THOUGHTS, PLANS & POSSIBILITIES', 'Your notebook', 'A home for the things you don’t want to forget.',
                     ('+ New note', lambda: self.edit('notes')))
        notes = [n for n in self.data['notes'] if not self.query or self.query in (n['title']+' '+n['body']).casefold()]
        grid = QGridLayout()
        grid.setSpacing(18)
        for index, note in enumerate(notes):
            card, col = panel()
            col.addWidget(label('▤  NOTE', 'eyebrow'))
            col.addWidget(TitleButton(note['title'], lambda n=note: self.edit('notes', n)))
            col.addWidget(label(note['body'][:300] or 'A blank page, full of possibility.', 'muted', True))
            col.addStretch()
            col.addWidget(label('Updated '+datetime.fromisoformat(note['updated']).astimezone().strftime('%b %d, %Y'), 'muted'))
            columns = 1 if self.compact else 2
            grid.addWidget(card, index//columns, index%columns)
        self.body.addLayout(grid)
        if not notes:
            self.empty(self.body, 'Start with a thought. Create a note using the button above.')

    def focus(self):
        self.heading('LESS DISTRACTION, MORE INTENTION', 'Focus studio', 'A quiet space to do your best work.')
        card, col = panel()
        card.setMinimumHeight(380)
        eyebrow = label('YOUR TIME, WELL SPENT', 'eyebrow')
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(eyebrow)
        self.clock = label(self.clock_text(), 'clock')
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.clock)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(button('Pause session' if self.timer.deadline else 'Start focusing ↗', self.toggle_timer, 'primary'))
        controls.addWidget(button('Reset', self.reset_timer))
        controls.addStretch()
        col.addLayout(controls)
        settings = QHBoxLayout()
        settings.addStretch()
        settings.addWidget(label('Minutes', 'muted'))
        duration = QSpinBox()
        duration.setRange(1, 240)
        duration.setValue(self.timer.duration)
        duration.setEnabled(not self.timer.deadline)
        duration.valueChanged.connect(self.set_duration)
        settings.addWidget(duration)
        task = QComboBox()
        task.setMaximumWidth(350)
        task.addItem('Free focus · no task', None)
        for t in self.data['tasks']:
            if t['status'] != 'done' or t['id'] == self.timer.task:
                task.addItem(t['title'], t['id'])
        task.setCurrentIndex(max(0, task.findData(self.timer.task)))
        task.setEnabled(not self.timer.deadline)
        task.currentIndexChanged.connect(lambda: self.set_focus_task(task.currentData()))
        settings.addWidget(task)
        settings.addStretch()
        col.addLayout(settings)
        info = label('Completed sessions are saved automatically. The timer works while the app is minimized.', 'muted', True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(info)
        self.body.addWidget(card)
        history, col = panel()
        col.addWidget(label('Recent sessions', 'section'))
        for session in self.data['sessions'][:12]:
            row = QHBoxLayout()
            title = next((t['title'] for t in self.data['tasks'] if t['id'] == session['task_id']), 'Free focus')
            row.addWidget(label(title, wrap=True), 1)
            row.addWidget(label(datetime.fromisoformat(session['created']).astimezone().strftime('%b %d · %H:%M'), 'muted'))
            row.addWidget(label(f"{session['minutes']} min", 'eyebrow'))
            row.addWidget(button('×', lambda s=session: self.delete_session(s['id']), 'danger'))
            col.addLayout(row)
        if not self.data['sessions']:
            self.empty(col, 'Your completed sessions will appear here.')
        self.body.addWidget(history)

    def delete_session(self, ident):
        if QMessageBox.question(self, 'Delete session', 'Delete this focus session?') == QMessageBox.StandardButton.Yes:
            try:
                self.repo.delete('sessions', ident)
                self.refresh()
            except sqlite3.Error as exc:
                QMessageBox.warning(self, 'Could not delete session', str(exc))

    def clock_text(self):
        return self.timer.text()

    def load_timer(self):
        self.timer.reload()

    def save_timer(self):
        self.timer.save()

    def set_duration(self, minutes):
        self.timer.set_duration(minutes)
        if self.clock:
            self.clock.setText(self.clock_text())

    def set_focus_task(self, ident):
        self.timer.task = ident
        self.timer.save()

    def toggle_timer(self):
        self.timer.toggle()
        self.render()

    def reset_timer(self):
        self.timer.reset()
        self.render()

    def tick(self):
        if self.clock:
            self.clock.setText(self.clock_text())
        try:
            if not self.timer.finish_if_due():
                return
        except sqlite3.Error as exc:
            # Avoid repeatedly opening modal dialogs while the database is locked.
            self.statusBar().showMessage('Session is waiting to save: '+str(exc), 10000)
            return
        self.refresh()
        QApplication.beep()
        QApplication.alert(self, 5000)
        self.statusBar().showMessage('Session complete. Take a breath — you earned it.', 20000)

    def export_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export Orbit backup', str(ROOT / ('orbit-backup-'+datetime.now().strftime('%Y-%m-%d')+'.json')), 'JSON backups (*.json)')
        if not path:
            return
        try:
            if Path(path).resolve() == store.DB.resolve():
                raise ValueError('Choose a JSON file, not the live workspace database.')
            store.atomic_json(path, self.repo.snapshot())
            self.statusBar().showMessage('Backup saved.', 6000)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Restore Orbit backup', str(ROOT), 'JSON backups (*.json)')
        if not path:
            return
        if QMessageBox.question(self, 'Replace workspace?', 'Restoring replaces all current data. Export a backup first if you want to keep it. Continue?') != QMessageBox.StandardButton.Yes:
            return
        try:
            if Path(path).stat().st_size > 5_000_000:
                raise ValueError('Backup exceeds the 5 MB limit.')
            self.repo.restore(json.loads(Path(path).read_text(encoding='utf-8')))
            self.project = None
            self.undo_stack.clear()
            self.timer.task = None
            self.timer.reset()
            self.refresh()
            self.statusBar().showMessage('Backup restored.', 6000)
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            QMessageBox.warning(self, 'Restore failed', str(exc))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = event.size().width() < 1180
        if hasattr(self, 'scroll') and compact != self.compact:
            self.compact = compact
            QTimer.singleShot(0, self.render)

    def closeEvent(self, event):
        try:
            self.save_timer()
            store.set_preference('geometry', bytes(self.saveGeometry().toBase64()).decode())
        except (OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, 'Could not save workspace', str(exc))
            event.ignore()
            return
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Orbit — a private, native desktop workspace.')
    parser.add_argument('--version', action='version', version=f'Orbit {__version__}')
    parser.add_argument('--demo', action='store_true', help='Open a temporary sample workspace; your own data is untouched.')
    args = parser.parse_args(argv)
    application = QApplication([sys.argv[0]])
    application.setApplicationName('Orbit')
    application.setDesktopFileName('orbit')
    application.setWindowIcon(QIcon(str(ICON)))
    application.setStyle('Fusion')
    temporary = None
    if args.demo:
        store.ROOT.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='.demo-', dir=store.ROOT)
        store.DB = Path(temporary.name) / 'orbit.sqlite3'
    try:
        store.DB.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(store.DB.parent / 'orbit.lock'))
        if not lock.tryLock(100):
            QMessageBox.information(None, 'Orbit is already running', 'Orbit is already open. Switch to its window to continue.')
            return 0
        store.initialize()
        if args.demo:
            from .demo import populate
            # Skip migration of the personal timer into a demo workspace.
            store.set_preference('focus_migrated', True)
            populate()
        window = Orbit()
        if args.demo:
            window.setWindowTitle('Orbit — Demo workspace')
            window.statusBar().showMessage('DEMO · This temporary workspace is removed when you close the app.')
        window.show()
        result = application.exec()
        lock.unlock()
        return result
    except (OSError, sqlite3.Error) as exc:
        QMessageBox.critical(None, 'Orbit could not start', f'Could not open the workspace at {store.DB}.\n\n{exc}')
        return 1
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == '__main__':
    sys.exit(main())
