"""
Tests for Step 7: Add Expense (GET/POST /expenses/add).

Spec: .claude/specs/07-add-expense.md

These tests are written strictly from the spec's contract, not from reading
app.py's current implementation:
    - GET/POST /expenses/add require a logged-in session (session["user_id"]);
      unauthenticated requests to either method redirect to /login.
    - GET renders a form with amount, category (7 fixed options), date, and
      description fields, defaulting the date to today.
    - POST validates amount (> 0, numeric), category (one of the 7 fixed
      values), and date (valid YYYY-MM-DD); on any failure it re-renders the
      form (200) with an error message and the previously submitted values,
      and does NOT write a row to the DB.
    - description is optional; blank/whitespace-only is stored as NULL.
    - On success, a row is inserted for session["user_id"] (never a
      client-supplied user_id) and the response redirects to /profile.
    - The newly added expense must be reflected on the profile page's
      transaction list and category breakdown.
    - profile.html exposes an "Add Expense" link to /expenses/add, and the
      navbar shows an "Add Expense" link only when logged in.

The exact wording of validation error messages is an implementation detail
not pinned down by the spec, so error assertions here check for a generic,
case-insensitive "error" marker in the response body rather than a specific
string.
"""

from datetime import date

from database.db import get_db
from database.queries import insert_expense


CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def _login(client, make_user, name="Expense User", email="expense@example.com"):
    user_id = make_user(name=name, email=email)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name
    return user_id


def _expense_count(user_id=None):
    conn = get_db()
    if user_id is None:
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    conn.close()
    return count


def _all_rows_for(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def _assert_rerenders_with_error(response):
    body = response.get_data(as_text=True)
    assert response.status_code == 200, "Validation failure must re-render the form (200), not redirect"
    assert "<form" in body, "Form must still be present after a validation error"
    assert "error" in body.lower(), "Expected some error message to be displayed"
    return body


class TestInsertExpenseUnit:
    """Unit tests for database.queries.insert_expense, per the spec's table."""

    def test_valid_row_is_persisted_and_queryable(self, make_user):
        user_id = make_user()

        insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_none_description_is_stored_as_null(self, make_user):
        user_id = make_user()

        insert_expense(user_id, 10.0, "Other", "2026-03-20", None)

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None


class TestAddExpenseAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post(
            "/expenses/add",
            data={
                "amount": "10",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Should not be saved",
            },
        )

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_does_not_insert_a_row(self, client):
        client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "2026-03-20"},
        )

        assert _expense_count() == 0, "Unauthenticated POST must never write to the DB"


class TestAddExpenseGetAuthenticated:
    def test_returns_200_with_a_post_form(self, client, make_user):
        _login(client, make_user)

        response = client.get("/expenses/add")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "<form" in body
        assert 'method="POST"' in body or 'method="post"' in body

    def test_form_contains_amount_category_date_description_fields(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.get("/expenses/add")
        body = response.get_data(as_text=True)

        for field in ("amount", "category", "date", "description"):
            assert f'name="{field}"' in body, f"Expected a {field!r} field in the form"

    def test_category_select_contains_exactly_the_seven_fixed_options(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.get("/expenses/add")
        body = response.get_data(as_text=True)

        assert "<select" in body, "Category must be rendered as a <select>"
        for category in CATEGORIES:
            assert category in body, f"Missing category option: {category}"

    def test_date_field_defaults_to_todays_date(self, client, make_user):
        _login(client, make_user)

        response = client.get("/expenses/add")
        body = response.get_data(as_text=True)

        today_iso = date.today().strftime("%Y-%m-%d")
        assert today_iso in body, "Date field should default to today's date"


class TestAddExpensePostValidSubmission:
    def test_valid_submission_redirects_to_profile(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "42.50",
                "category": "Health",
                "date": "2026-03-20",
                "description": "Doctor visit",
            },
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_valid_submission_inserts_a_row_for_the_logged_in_user(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        client.post(
            "/expenses/add",
            data={
                "amount": "42.50",
                "category": "Health",
                "date": "2026-03-20",
                "description": "Doctor visit",
            },
        )

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == 42.50
        assert row["category"] == "Health"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Doctor visit"

    def test_new_expense_appears_on_profile_page_after_redirect(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "42.50",
                "category": "Health",
                "date": "2026-03-20",
                "description": "Doctor visit",
            },
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Doctor visit" in body, "New expense must appear in the transaction list"
        assert "Health" in body, "New expense's category must appear in the category breakdown"
        assert "₹" in body, "Amounts must always display the rupee symbol"

    def test_insert_ignores_client_supplied_user_id(self, client, make_user):
        """Only the session's logged-in user_id may ever be used, never a
        client-supplied value, even if the client tries to smuggle one in."""
        victim_id = make_user(name="Victim", email="victim@example.com")
        attacker_id = _login(
            client, make_user, name="Attacker", email="attacker@example.com"
        )

        client.post(
            "/expenses/add",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "2026-03-20",
                "description": "Sneaky",
                "user_id": str(victim_id),
            },
        )

        attacker_rows = _all_rows_for(attacker_id)
        victim_rows = _all_rows_for(victim_id)

        assert len(attacker_rows) == 1, "Expense must be recorded for the logged-in user"
        assert attacker_rows[0]["user_id"] == attacker_id
        assert len(victim_rows) == 0, "Client-supplied user_id must never be trusted"


class TestAddExpensePostOptionalDescription:
    def test_no_description_field_saves_expense_without_error(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "12.5", "category": "Other", "date": "2026-03-20"},
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        assert not rows[0]["description"]

    def test_blank_description_is_stored_as_null(self, client, make_user):
        user_id = _login(client, make_user)

        client.post(
            "/expenses/add",
            data={
                "amount": "12.5",
                "category": "Other",
                "date": "2026-03-20",
                "description": "",
            },
        )

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_whitespace_only_description_is_stripped_and_stored_as_null(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        client.post(
            "/expenses/add",
            data={
                "amount": "12.5",
                "category": "Other",
                "date": "2026-03-20",
                "description": "   ",
            },
        )

        rows = _all_rows_for(user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None


class TestAddExpensePostValidationErrors:
    def test_missing_amount_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_zero_amount_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_negative_amount_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "-5", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_non_numeric_amount_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "abc", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_invalid_category_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "NotACategory", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_missing_category_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_invalid_date_string_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "not-a-date"},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_missing_date_rerenders_with_error_and_does_not_insert(
        self, client, make_user
    ):
        user_id = _login(client, make_user)

        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": ""},
        )

        _assert_rerenders_with_error(response)
        assert _expense_count(user_id) == 0

    def test_validation_error_retains_previously_submitted_values(
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
        body = _assert_rerenders_with_error(response)

        assert "Taxi ride" in body, "Previously entered description must be retained"
        assert "2026-03-20" in body, "Previously entered date must be retained"
        assert "Transport" in body, "Previously entered category must be retained/selected"


class TestAddExpenseNavigation:
    """Definition-of-done items about surfacing /expenses/add in the UI."""

    def test_profile_page_links_to_add_expense_when_logged_in(
        self, client, make_user
    ):
        _login(client, make_user)

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "/expenses/add" in body, "Profile page must link to the add-expense form"

    def test_navbar_shows_add_expense_link_when_logged_in(self, client, make_user):
        _login(client, make_user)

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert "/expenses/add" in body

    def test_navbar_hides_add_expense_link_when_logged_out(self, client):
        response = client.get("/")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "/expenses/add" not in body, "Add Expense link must not be shown to logged-out visitors"
