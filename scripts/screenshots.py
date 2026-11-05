#!/usr/bin/env python3
"""Render README screenshots using synthetic data in an isolated workspace."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['QT_QPA_PLATFORMTHEME'] = ''
os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'
os.environ['XDG_CURRENT_DESKTOP'] = ''
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication, QEvent
from orbit import desktop, storage
from orbit.demo import populate


def main():
    application = QApplication([])
    application.setStyle('Fusion')
    destination = ROOT / 'docs' / 'screenshots'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as directory:
        with patch.object(storage, 'DB', Path(directory) / 'demo.sqlite3'):
            storage.initialize()
            storage.set_preference('focus_migrated', True)
            populate()
            window = desktop.Orbit()
            window.resize(1360, 940)
            window.show()
            for view, filename in [('Overview', 'overview'), ('Task board', 'board'), ('Notebook', 'notebook'), ('Focus studio', 'focus')]:
                window.navigate(view)
                application.processEvents()
                application.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                window.grab().save(str(destination / (filename + '.png')))
            window.toggle_theme()
            window.navigate('Task board')
            application.processEvents()
            application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            application.processEvents()
            window.grab().save(str(destination / 'dark.png'))
            window.close()
    print(f'Screenshots saved to {destination}')


if __name__ == '__main__':
    main()
