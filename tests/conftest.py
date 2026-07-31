import os
import tempfile

import pytest

import database.db as db

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.remove(_path)
db.DB_PATH = _path

import app as app_module  # noqa: E402  (must import after DB_PATH is patched)


@pytest.fixture
def app():
    app_module.app.config.update(TESTING=True)
    yield app_module.app


@pytest.fixture(autouse=True)
def _clean_db():
    db.init_db()
    conn = db.get_db()
    conn.execute("DELETE FROM expenses")
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def make_user():
    def _make_user(name="Test User", email="test@example.com", password="password123"):
        from werkzeug.security import generate_password_hash

        conn = db.get_db()
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id

    return _make_user


@pytest.fixture
def make_expense():
    def _make_expense(user_id, amount, category, date, description=""):
        conn = db.get_db()
        conn.execute(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, category, date, description),
        )
        conn.commit()
        conn.close()

    return _make_expense
