"""
Tests for Step 7: GET/POST /expenses/add.

Spec: .claude/specs/07-add-expense.md
"""

from database.db import get_db
from database.queries import insert_expense


def _login(client, make_user, name="Expense User", email="expense@example.com"):
    user_id = make_user(name=name, email=email)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name
    return user_id


class TestInsertExpense:
    def test_inserts_row_with_all_fields(self, make_user):
        user_id = make_user()
        insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_none_description_stored_as_null(self, make_user):
        user_id = make_user()
        insert_expense(user_id, 10.0, "Other", "2026-03-20", None)

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row["description"] is None


class TestAddExpenseAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "2026-03-20"},
        )

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


class TestAddExpenseGet:
    def test_authenticated_get_shows_form_with_all_categories(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.get("/expenses/add")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "<form" in body
        for category in (
            "Food",
            "Transport",
            "Bills",
            "Health",
            "Entertainment",
            "Shopping",
            "Other",
        ):
            assert category in body


class TestAddExpensePostHappyPath:
    def test_valid_submission_redirects_and_inserts_row(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["description"] == "Lunch"

    def test_blank_description_is_optional_and_saves_as_empty(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "12.5", "category": "Other", "date": "2026-03-20"},
        )

        assert response.status_code == 302

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert not row["description"]


class TestAddExpensePostValidationErrors:
    def test_missing_amount_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-03-20"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count == 0

    def test_zero_amount_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

    def test_negative_amount_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "-5", "category": "Food", "date": "2026-03-20"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

    def test_non_numeric_amount_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "abc", "category": "Food", "date": "2026-03-20"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

    def test_invalid_category_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "NotACategory", "date": "2026-03-20"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count == 0

    def test_invalid_date_rerenders_with_error(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "not-a-date"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "auth-error" in body

        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count == 0

    def test_validation_error_retains_previously_entered_values(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Transport",
                "date": "2026-03-20",
                "description": "Taxi ride",
            },
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Taxi ride" in body
        assert "2026-03-20" in body
