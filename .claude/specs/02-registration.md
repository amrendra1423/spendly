# Spec: Registration

## Overview

This feature implements user registration for Spendly. It replaces the placeholder `/register` route (currently a simple `GET` that renders `register.html` with no form handling) with a working `POST` handler that validates input and creates a new row in the `users` table with a hashed password. This is the first step in the authentication flow and unblocks login, logout, and profile, which all depend on a real `users` table being populated through the app rather than only through `seed_db()`. Registration does not start a session itself — it redirects to `/login` so the user signs in explicitly; session creation is handled by the login step.

## Depends on

- Step 1 — Database Setup (`database/db.py` fully implemented — complete)

## Routes

- GET /register — render the registration form — public (already exists, unchanged)
- POST /register — validate input, create user, redirect to login — public

## Database changes

No database changes. The `users` table in `database/db.py` already has all required columns (`id`, `name`, `email`, `password_hash`, `created_at`). Registration will insert into this existing table using a parameterized `INSERT`.

## Templates

- Create: none
- Modify: `templates/register.html` — adds a `confirm_password` field alongside `password`; form posts `name`, `email`, `password`, `confirm_password` to `/register` and renders an `error` variable on failure.

## Files to change

- `app.py` — implement `POST` handling on the `/register` route: read form fields, validate, check for existing email, hash password, insert user, set session, redirect
- `database/db.py` — no changes expected, but add a small helper only if needed (e.g. `get_user_by_email`) if the query is reused elsewhere

## Files to create

- None

## New dependencies

No new dependencies. `werkzeug.security` (already used in `seed_db()`) provides `generate_password_hash`; Flask's built-in `session` provides login state.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend base.html
- Validate that `name`, `email`, `password`, and `confirm_password` are all non-empty before attempting an insert
- Validate that `password` and `confirm_password` match; on mismatch, re-render `register.html` with `error` set
- Check for an existing user with the same email before inserting; on conflict, re-render `register.html` with `error` set instead of raising an unhandled `IntegrityError`
- On success, redirect to `/login` — do not start a session; the user signs in explicitly afterward
- Do not implement `/login`, `/logout`, or `/profile` behavior in this step — those remain placeholders for later steps

## Definition of done

- [ ] Submitting the registration form with valid name/email/password creates a new row in `users` with a hashed (not plaintext) password
- [ ] Submitting with an email that already exists (e.g. `demo@spendly.com`) re-renders `register.html` with a visible error and does not create a duplicate row
- [ ] Submitting with a missing field (name, email, password, or confirm password) re-renders `register.html` with a visible error and does not insert a row
- [ ] Submitting with `password` and `confirm_password` that don't match re-renders `register.html` with a visible error and does not insert a row
- [ ] After successful registration, the user is redirected to `/login` (no session is created by registration itself)
- [ ] App starts and runs without errors (`python app.py`)
- [ ] No plaintext passwords appear anywhere in `expense_tracker.db` after registering
