# Spendly

Spendly is a Flask expense tracker. Register, log in, and log, edit, and delete
personal expenses, with a profile dashboard summarizing spending by date range
and category.

**Live demo:** https://expense-tracker-production-a004.up.railway.app
(login with `demo@spendly.com` / `demo123`)

## Features

- Account registration and login/logout with hashed passwords
- Profile dashboard: total spent, transaction count, top category, and a
  recent-transactions table, filterable by date range (with quick presets:
  This Month, Last 3 Months, Last 6 Months, All Time)
- Spending breakdown by category
- Add, edit, and delete expenses, each scoped to the logged-in user
- Analytics page (placeholder — coming soon)

## Tech stack

- **Backend:** Flask (Python), raw `sqlite3` — no ORM
- **Frontend:** Jinja2 templates, a single global stylesheet/script (no
  build step, no JS framework)
- **Auth:** `werkzeug.security` password hashing, Flask session cookies
- **Tests:** pytest + pytest-flask
- **Deployment:** gunicorn behind Railway

## Project structure

```
app.py                  Flask app — all routes live here (no blueprints)
database/
  db.py                 DB connection, schema, and seed data
  queries.py            All SQL query functions
templates/               Jinja2 templates, all extending base.html
static/
  css/style.css          Single global stylesheet (CSS variables, no hardcoded hex)
  js/main.js              Single global script
tests/                    pytest suite, one file per feature step
.claude/specs/            Spec docs for each incremental build step
```

## Getting started

```bash
# Create and activate a virtualenv (Windows)
python -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the dev server
python app.py
```

The app runs at http://localhost:5001 and seeds a demo user
(`demo@spendly.com` / `demo123`) with sample expenses on first run.

By default the dev server runs with debug mode off. To enable Flask's
debug/reloader locally, set `FLASK_DEBUG=1` before running:

```bash
# Windows PowerShell
$env:FLASK_DEBUG = "1"; python app.py
```

## Running tests

```bash
pytest                                    # full suite
pytest tests/test_09-delete-expense.py    # a single file
pytest tests/test_09-delete-expense.py::TestDeleteExpenseUnit  # a single test class
```

## Deployment

The app is deployed to [Railway](https://railway.com) via the Railway CLI
(`railway up`), running under gunicorn (see `Procfile`). Configuration is
read from environment variables:

| Variable   | Purpose                                             |
| ---------- | ---------------------------------------------------- |
| `PORT`     | Set automatically by Railway                        |
| `SECRET_KEY` | Flask session signing key — set to a random value in production |
| `FLASK_DEBUG` | Set to `1` to enable debug mode (never set in production) |

Note: the app uses a local SQLite file (`expense_tracker.db`), which is not
persisted across Railway redeploys — data resets to the seeded demo data on
each deploy unless a persistent volume is attached.

## Project conventions

This app is being built incrementally, one feature at a time, following the
specs in `.claude/specs/`. See `CLAUDE.md` for the full set of development
conventions (no ORMs, parameterized queries only, CSS variables only, etc.).
