# Architecture

Orbit is a single-process Qt application. The desktop entry point creates a workspace lock, initializes SQLite, and opens the main window. It does not start an HTTP service or embed a browser.

## Persistence boundary

`storage.Repository` validates writes before executing parameterized SQL. Table names come from a fixed internal allowlist. Foreign keys detach tasks when a project is deleted and detach sessions when a task is deleted. Existing schemas are initialized idempotently; indexes and the internal preferences table are additive.

A source checkout stores its data beside `app.py`. Installed packages default to a writable user directory. `ORBIT_DATA_DIR` overrides the location. Tests patch the database path to temporary directories inside the project; they never modify the personal database.

## Focus state

`FocusTimer` stores duration, remaining seconds, deadline, linked task ID, and a unique run token in SQLite preferences. A deadline uses wall-clock time so minimizing, suspending, or closing the app does not pause a session. Changing the system clock can change the remaining time.

Completion acquires a SQLite write transaction, verifies the stored token and deadline, inserts the session, and resets focus state before committing. A second completion attempt sees the cleared state and inserts nothing. A failed write rolls back both operations, leaving the session eligible for a later retry. Desktop workspace locking prevents multiple active windows from editing the same focus state.

The legacy JSON focus file is imported once. A migration preference prevents it from being imported again after a restore. It is never deleted automatically.

## Backups

The public JSON format contains exactly four arrays: `projects`, `tasks`, `notes`, and `sessions`. IDs, required fields, dates, priorities, statuses, colors, links, and timestamps are validated. Missing optional fields use the schema defaults for backward compatibility.

Restore validates every record, then replaces all four public tables in one transaction. Foreign-key or insertion errors roll back every deletion. Focus state is cleared in the same transaction; theme and geometry preferences remain local. Export uses a temporary file in the destination directory, flushes it, and replaces the destination atomically.

## UI

Views are rendered from repository snapshots. Qt owns widget lifetimes; replaced widgets are deleted after event processing. Search is debounced. Long task, project, and note titles use accessible buttons with tooltips and ellipsis, so they cannot stretch the board. Small windows stack columns vertically. Light/dark styling includes the application palette so native popups match.

## Packaging

Only the `orbit` package and its SVG resource are installed by the Python build. Desktop integration and screenshot generation are source-checkout tools. The source tree retains the optional original web interface, which shares the storage layer but is not imported by the desktop package.
