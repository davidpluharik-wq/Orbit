# Release checklist

1. Update the version in `orbit/__init__.py` and `pyproject.toml` together, then update `CHANGELOG.md`.
2. Run `python -m unittest discover -s tests -v`, `ruff check .`, and `python -m build`.
3. Install the wheel into a fresh environment. Check `orbit --version`, `orbit --demo`, the packaged icon, and the native menus.
4. Test a copy of an existing database, a JSON backup round trip, and an interrupted focus session. Never use the only copy of personal data for release checks.
5. Review screenshots and regenerate them using `python scripts/screenshots.py` if necessary.
6. Confirm the distribution contains no database, credentials, exported backups, local configuration, or machine-specific launcher.
7. Tag the tested commit and create a GitHub release with the changelog and built distributions. Do not claim cross-platform verification unless it has actually been performed.
