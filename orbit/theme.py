"""Consistent light and dark palettes for native Qt controls."""
from pathlib import Path
from PyQt6.QtGui import QColor, QPalette

LIGHT_STYLE = '''
QWidget {font-family: "DejaVu Sans"; font-size: 12px; color: #303247;}
QMainWindow, QWidget#workspace {background: #f7f8fb;}
QFrame#sidebar {background: #ffffff; border-right: 1px solid #e6e7ef;}
QLabel {background: transparent;}
QWidget#project-list {background: #ffffff;}
QMenuBar, QMenu {background: #ffffff; color: #303247;}
QMenuBar::item:selected, QMenu::item:selected {background: #eeebfa;}
QToolTip {border: 1px solid #e6e7ef; padding: 6px;}
QLabel#brand {font-size: 30px; font-weight: 800; color: #6550bc;}
QLabel#eyebrow {font-size: 10px; font-weight: 700; color: #8c80b6; letter-spacing: 2px;}
QLabel#title {font-size: 29px; font-weight: 700; color: #292b40;}
QLabel#muted {color: #8c8fa2; font-size: 11px;}
QLabel#section {font-size: 15px; font-weight: 700;}
QLabel#value {font-size: 30px; font-weight: 700;}
QLabel#clock {font-size: 82px; font-weight: 300; color: #6f59c4;}
QPushButton {padding: 10px 15px; background: #ffffff; border: 1px solid #e5e5ef; border-radius: 8px; text-align: left;}
QPushButton:hover {background: #f0ecfb; border-color: #c6b9ea;}
QPushButton:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus {border: 1px solid #9d85e3;}
QPushButton#nav {border: none; padding: 13px 16px; color: #78798f;}
QPushButton#nav:checked {background: #eeebfa; color: #7055c4; font-weight: 700;}
QPushButton#primary {background: #7660cf; color: white; border: none; font-weight: 700; padding: 12px 19px;}
QPushButton#primary:hover {background: #6249b9;}
QPushButton#danger {color: #bb6574;}
QFrame#panel, QFrame#card {background: #ffffff; border: 1px solid #e6e7ef; border-radius: 12px;}
QFrame#hero {background: #eeebfb; border: 1px solid #e1daf5; border-radius: 12px;}
QFrame#column {background: #eef0f5; border-radius: 12px;}
QLineEdit, QTextEdit, QComboBox, QSpinBox {background: #ffffff; border: 1px solid #e2e3ed; border-radius: 7px; padding: 9px; selection-background-color: #b8a7e6;}
QComboBox::drop-down {border: none; width: 18px;}
QComboBox QAbstractItemView {background: #ffffff; selection-background-color: #ede6fc; selection-color: #4e397c;}
QScrollArea {border: none; background: transparent;}
QScrollBar:vertical {background: transparent; width: 7px;}
QScrollBar::handle:vertical {background: #d5d2e2; border-radius: 3px; min-height: 30px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height: 0;}
QProgressBar {background: #f0edf8; border: none; border-radius: 3px; height: 6px; max-height: 6px;}
QProgressBar::chunk {background: #9a83d9; border-radius: 3px;}
QDialog {background: #f7f8fb;}
QStatusBar {background: #f7f8fb; color: #85869a; font-size: 11px;}
'''

DARK_COLORS = {
    '#f7f8fb': '#171b28', '#ffffff': '#222839', '#e6e7ef': '#343c51',
    '#303247': '#e7eafa', '#6550bc': '#b7a0ff', '#8c80b6': '#b7a7df',
    '#292b40': '#eff0ff', '#8c8fa2': '#a8afc4', '#f0ecfb': '#323149',
    '#e5e5ef': '#3c4359', '#c6b9ea': '#8d77be', '#78798f': '#b3bad0',
    '#eeebfa': '#37324f', '#7055c4': '#c4acff', '#eeebfb': '#302d49',
    '#e1daf5': '#484062', '#eef0f5': '#1d2232', '#e2e3ed': '#3d455c',
    '#ede6fc': '#504169', '#4e397c': '#f2eaff', '#f0edf8': '#36374c',
    '#85869a': '#a7adc3', '#6f59c4': '#c0aaff', '#bb6574': '#ed9caa',
}


def stylesheet(theme='light'):
    style = LIGHT_STYLE
    if theme == 'dark':
        import re
        style = re.sub(r'#[0-9a-fA-F]{6}', lambda match: DARK_COLORS.get(match[0], match[0]), style)
    arrow = (Path(__file__).resolve().parent / 'resources' / 'chevron.svg').as_posix()
    return style + '\nQComboBox::down-arrow {image: url("' + arrow + '"); width:10px; height:10px;}'


def apply_theme(application, theme):
    dark = theme == 'dark'
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: '#171b28' if dark else '#f7f8fb',
        QPalette.ColorRole.WindowText: '#e7eafa' if dark else '#303247',
        QPalette.ColorRole.Base: '#222839' if dark else '#ffffff',
        QPalette.ColorRole.AlternateBase: '#1d2232' if dark else '#f0edf8',
        QPalette.ColorRole.Text: '#e7eafa' if dark else '#303247',
        QPalette.ColorRole.Button: '#222839' if dark else '#ffffff',
        QPalette.ColorRole.ButtonText: '#e7eafa' if dark else '#303247',
        QPalette.ColorRole.Highlight: '#7660cf',
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.ToolTipBase: '#222839' if dark else '#ffffff',
        QPalette.ColorRole.ToolTipText: '#e7eafa' if dark else '#303247',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(stylesheet(theme))
