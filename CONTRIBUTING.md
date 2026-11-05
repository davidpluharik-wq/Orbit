# Contributing

Thanks for helping improve Orbit. Start with an issue describing the problem, a concrete example, and the behavior you would like.

## Local setup

Use Python 3.10+ in a virtual environment, then install with `python -m pip install -e '.[dev]'`. Launch with `python app.py --demo` to work with disposable sample data. Do not use someone’s real workspace for tests or screenshots.

## Before opening a pull request

- Run `python -m unittest discover -s tests -v` and `ruff check .`.
- Build the distribution with `python -m build` after packaging changes.
- Check affected native views in both appearances and at 960px and 1360px window widths.
- Add regression tests for data loss, validation, persistence, and interaction bugs. Avoid tests that only repeat implementation details.
- Keep changes focused and explain the user-visible problem, resulting behavior, and validation.
- Do not include personal databases, timer state, backups, logs, credentials, or machine-specific desktop launchers.

## Design boundaries

The desktop interface belongs in `orbit/desktop.py`. Persistence and validation belong in `orbit/storage.py`; focus-session logic belongs in `orbit/focus.py`. Prefer small standard-library helpers over additional runtime dependencies. User text is plain text, including when it looks like HTML.

A restore must leave all existing records unchanged if any part fails. A focus completion must commit its session and timer reset in one transaction. Preserve compatibility with existing SQLite workspaces and the four-table JSON export format.

Contributions are distributed under the project’s GPL-3.0-only license.
