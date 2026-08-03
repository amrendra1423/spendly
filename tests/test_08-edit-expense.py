"""
Tests for Step 8: Edit Expense (GET/POST /expenses/<id>/edit).

Spec: .claude/specs/08-edit-expense.md

These tests are written strictly from the spec's contract, not from reading
app.py's current implementation:
    - GET/POST /expenses/<id>/edit require a logged-in session
      (session["user_id"]); unauthenticated requests to either method
      redirect to /login.
    - Ownership is enforced two ways: `get_expense_by_id(expense_id, user_id)`
      only returns a row that belongs to the given user (None otherwise),
      and `update_expense(expense_id, user_id, ...)` scopes its UPDATE to
      `id = ? AND user_id = ?` so it is a no-op for a non-owned row.
    - The route itself must 404 (not error, not silently redirect) when the
      expense does not exist or belongs to another user, for both GET and
      POST.
    - GET renders a form pre-populated with the expense's current amount,
      category (correct <option> pre-selected), date, and description.
    - POST validates amount (> 0, numeric), category (one of the 7 fixed
      values), and date (valid YYYY-MM-DD); on any failure it re-renders the
      form (200) with an error message and the submitted (not original)
      values, and does NOT change the row in the DB.
    - description is optional; blank/whitespace-only is stored as NULL.
    - On success, `update_expense` is called and the response redirects to
      /profile; the updated values must then be visible on the profile page.
    - profile.html's transaction rows must link to the correct
      `/expenses/<id>/edit` URL.

The exact wording of validation error messages is an implementation detail
not pinned down by the spec, so error assertions here check for a generic,
case-insensitive "error" marker in the response body rather than a specific
string.
"""

import re

from database.db import get_db
from database.queries import get_expense_by_id, update_expense


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


def _get_expense_row(expense_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row


def _latest_expense_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    assert row is not None, "Expected an expense row to exist for this user"
    return row["id"]


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


def _assert_rerenders_with_error(response):
    body = response.get_data(as_text=True)
    assert response.status_code == 200, "Validation failure must re-render the form (200), not redirect"
    assert "<form" in body, "Form must still be present after a validation error"
    assert "error" in body.lower(), "Expected some error message to be displayed"
    return body


def _assert_category_selected(body, category):
    pattern = re.compile(
        rf'<option[^>]*value="{re.escape(category)}"[^>]*selected'
        rf'|<option[^>]*selected[^>]*value="{re.escape(category)}"'
    )
    assert pattern.search(body), f"Expected {category!r} to be the pre-selected option"


class TestGetExpenseByIdUnit:
    """Unit tests for database.queries.get_expense_by_id, per the spec's table."""

    def test_valid_expense_id_and_correct_user_id_returns_matching_row(
        self, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        result = get_expense_by_id(expense_id, user_id)

        assert result is not None
        assert result["id"] == expense_id
        assert result["user_id"] == user_id
        assert result["amount"] == 25.0
        assert result["category"] == "Food"
        assert result["date"] == "2026-03-01"
        assert result["description"] == "Lunch"

    def test_valid_expense_id_wrong_user_id_returns_none(
        self, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        other_id = make_user(name="Other", email="other@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        result = get_expense_by_id(expense_id, other_id)

        assert result is None, "Must not return another user's expense"

    def test_non_existent_expense_id_returns_none(self, make_user):
        user_id = make_user()

        result = get_expense_by_id(999999, user_id)

        assert result is None


class TestUpdateExpenseUnit:
    """Unit tests for database.queries.update_expense, per the spec's table."""

    def test_valid_expense_id_correct_user_id_updates_amount(
        self, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        update_expense(expense_id, user_id, 99.0, "Food", "2026-03-01", "Lunch")

        row = _get_expense_row(expense_id)
        assert row["amount"] == 99.0

    def test_wrong_user_id_leaves_row_unchanged_and_raises_no_error(
        self, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        attacker_id = make_user(name="Attacker", email="attacker@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        # Must not raise, even though it affects 0 rows.
        update_expense(expense_id, attacker_id, 99.0, "Shopping", "2026-05-05", "Hacked")

        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-01"
        assert row["description"] == "Lunch"


class TestEditExpenseAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/edit")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_redirects_to_login(self, client, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50",
                "category": "Shopping",
                "date": "2026-04-01",
                "description": "Should not be saved",
            },
        )

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_does_not_modify_the_row(
        self, client, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "50", "category": "Shopping", "date": "2026-04-01"},
        )

        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0
        assert row["category"] == "Food"


class TestEditExpenseGetOwnershipAndNotFound:
    def test_get_other_users_expense_returns_404(self, client, make_user, make_expense):
        owner_id = make_user(name="Owner", email="owner@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        _login(client, make_user, name="Attacker", email="attacker@example.com")

        response = client.get(f"/expenses/{expense_id}/edit")

        assert response.status_code == 404

    def test_get_non_existent_id_returns_404(self, client, make_user):
        _login(client, make_user)

        response = client.get("/expenses/999999/edit")

        assert response.status_code == 404


class TestEditExpenseGetAuthenticated:
    def test_returns_200_with_a_post_form(self, client, make_user, make_expense):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/edit")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "<form" in body
        assert 'method="POST"' in body or 'method="post"' in body

    def test_form_contains_amount_category_date_description_fields(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/edit")
        body = response.get_data(as_text=True)

        for field in ("amount", "category", "date", "description"):
            assert f'name="{field}"' in body, f"Expected a {field!r} field in the form"

    def test_form_is_pre_filled_with_the_expenses_current_values(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 42.5, "Transport", "2026-03-15", "Taxi ride")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/edit")
        body = response.get_data(as_text=True)

        assert "42.5" in body, "Amount must be pre-filled with the current value"
        assert "2026-03-15" in body, "Date must be pre-filled with the current value"
        assert "Taxi ride" in body, "Description must be pre-filled with the current value"

    def test_category_select_has_the_correct_option_pre_selected(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 42.5, "Transport", "2026-03-15", "Taxi ride")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/edit")
        body = response.get_data(as_text=True)

        assert "<select" in body, "Category must be rendered as a <select>"
        for category in CATEGORIES:
            assert category in body, f"Missing category option: {category}"
        _assert_category_selected(body, "Transport")


class TestEditExpensePostValidSubmission:
    def test_valid_submission_redirects_to_profile(self, client, make_user, make_expense):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "2026-05-05",
                "description": "New shoes",
            },
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_valid_submission_updates_the_row_in_the_database(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "2026-05-05",
                "description": "New shoes",
            },
        )

        row = _get_expense_row(expense_id)
        assert row["user_id"] == user_id
        assert row["amount"] == 99.99
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-05-05"
        assert row["description"] == "New shoes"
        assert _expense_count(user_id) == 1, "Editing must not create a new row"

    def test_updated_values_appear_on_profile_page_after_redirect(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "2026-05-05",
                "description": "New shoes",
            },
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "New shoes" in body, "Updated description must appear in the transaction list"
        assert "Shopping" in body, "Updated category must appear on the profile page"
        assert "₹" in body, "Amounts must always display the rupee symbol"


class TestEditExpensePostOwnershipAndNotFound:
    def test_post_other_users_expense_returns_404(self, client, make_user, make_expense):
        owner_id = make_user(name="Owner", email="owner@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        _login(client, make_user, name="Attacker", email="attacker@example.com")

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "1.00",
                "category": "Other",
                "date": "2026-01-01",
                "description": "Hacked",
            },
        )

        assert response.status_code == 404

    def test_post_other_users_expense_does_not_modify_the_row(
        self, client, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        _login(client, make_user, name="Attacker", email="attacker@example.com")

        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "1.00",
                "category": "Other",
                "date": "2026-01-01",
                "description": "Hacked",
            },
        )

        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-01"
        assert row["description"] == "Lunch"

    def test_post_non_existent_id_returns_404(self, client, make_user):
        _login(client, make_user)

        response = client.post(
            "/expenses/999999/edit",
            data={"amount": "10", "category": "Food", "date": "2026-03-20"},
        )

        assert response.status_code == 404


class TestEditExpensePostOptionalDescription:
    def test_no_description_field_saves_without_error(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "12.5", "category": "Other", "date": "2026-03-20"},
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        row = _get_expense_row(expense_id)
        assert not row["description"]

    def test_blank_description_is_stored_as_null(self, client, make_user, make_expense):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "12.5",
                "category": "Other",
                "date": "2026-03-20",
                "description": "",
            },
        )

        row = _get_expense_row(expense_id)
        assert row["description"] is None

    def test_whitespace_only_description_is_stripped_and_stored_as_null(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "12.5",
                "category": "Other",
                "date": "2026-03-20",
                "description": "   ",
            },
        )

        row = _get_expense_row(expense_id)
        assert row["description"] is None


class TestEditExpensePostValidationErrors:
    def test_missing_amount_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0, "DB must be unchanged after a validation error"

    def test_zero_amount_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0

    def test_negative_amount_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "-5", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0

    def test_non_numeric_amount_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "abc", "category": "Food", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["amount"] == 25.0

    def test_invalid_category_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "10", "category": "NotACategory", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["category"] == "Food"

    def test_missing_category_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "10", "category": "", "date": "2026-03-20"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["category"] == "Food"

    def test_invalid_date_string_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "10", "category": "Food", "date": "not-a-date"},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["date"] == "2026-03-01"

    def test_missing_date_rerenders_with_error_and_does_not_update(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "10", "category": "Food", "date": ""},
        )

        _assert_rerenders_with_error(response)
        row = _get_expense_row(expense_id)
        assert row["date"] == "2026-03-01"

    def test_validation_error_retains_submitted_values_not_original_values(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "abc",
                "category": "Transport",
                "date": "2026-04-15",
                "description": "New taxi ride",
            },
        )
        body = _assert_rerenders_with_error(response)

        assert "New taxi ride" in body, "Newly submitted description must be retained"
        assert "2026-04-15" in body, "Newly submitted date must be retained"
        assert "Transport" in body, "Newly submitted category must be retained/selected"


class TestEditExpenseNavigation:
    """Definition-of-done items about the profile page's per-row Edit link."""

    def test_profile_transaction_row_links_to_the_correct_edit_url(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert f"/expenses/{expense_id}/edit" in body, (
            "Profile page must link each transaction row to its own edit URL"
        )

    def test_multiple_transactions_each_link_to_their_own_edit_url(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        first_id = _latest_expense_id(user_id)
        make_expense(user_id, 40.0, "Bills", "2026-03-02", "Water bill")
        second_id = _latest_expense_id(user_id)

        assert first_id != second_id

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert f"/expenses/{first_id}/edit" in body
        assert f"/expenses/{second_id}/edit" in body
