# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spendly is a Flask expense-tracker web app being built incrementally as a step-by-step learning project. Routes and modules exist as placeholders with comments describing what should be implemented at each step (e.g. `app.py` has comments like `Logout — coming in Step 3`, `Add expense — coming in Step 7`; `database/db.py` has comments describing Step 1 — Database Setup). When asked to implement a feature, check for these comments first — they indicate the intended scope and order of work, and later steps often depend on earlier ones (auth before expense CRUD, DB setup before auth).

## Commands

Run these from the repo root with the venv active.

```
# Activate virtualenv (Windows)
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the dev server (http://localhost:5001)
python app.py

# Run tests
pytest

# Run a single test file / test
pytest path/to/test_file.py
pytest path/to/test_file.py::test_name
```

There is no lint/format tooling configured in this repo.

## Architecture

- `app.py` — single Flask application module; all routes are currently defined directly on `app` (no blueprints). `debug=True`, runs on port 5001.
- `database/db.py` — intended to hold `get_db()` (SQLite connection with `row_factory` and foreign keys enabled), `init_db()` (creates tables with `CREATE TABLE IF NOT EXISTS`), and `seed_db()` (sample dev data). Not yet implemented — currently just comments describing the required contract.
- `templates/` — Jinja2 templates, all extending `templates/base.html`, which defines the nav/footer chrome and the `title`, `head`, `content`, and `scripts` blocks. Existing pages: `landing.html`, `login.html`, `register.html`, `terms.html`, `privacy.html`.
- `static/css/style.css` and `static/js/main.js` — single global stylesheet/script shared by all pages (no per-page or component-scoped assets).
- Auth forms (`login.html`, `register.html`) POST to `/login` and `/register` respectively and render an `error` template variable on failure; `register.html` collects `name`, `email`, `password`.
- Placeholder routes (`/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`) currently return plain strings and are meant to be implemented in later steps.
