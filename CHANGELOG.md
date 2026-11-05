# Changelog

## 1.0.0

First packaged desktop release.

### Added

- Native Qt overview, task board, notebook, and focus studio.
- Light and dark appearance with remembered preferences and window geometry.
- Project, priority, due-date, and text filters; date/title/priority/newest sorting.
- Task-move undo, calendar date picker, native menus, and keyboard shortcuts.
- Unsaved-change protection for editors and ellipsis/tooltip support for long titles.
- Compact task-board layout for smaller windows.
- Disposable demo mode, screenshot generator, and portable Linux launcher generator.
- Package metadata, console entry point, CI checks, contributor documentation, and GPLv3 license.

### Fixed

- A crash after recording a focus session can no longer record the same session again on reopening.
- Corrupt or malformed backups cannot partially replace a workspace.
- Exports use atomic file replacement and cannot overwrite the live database through the UI.
- Legacy timer state is migrated once; restoring a backup clears active focus state.

### Compatibility

Existing project-folder databases and four-table JSON backups remain supported. The original browser version remains in the source tree as a legacy interface.
