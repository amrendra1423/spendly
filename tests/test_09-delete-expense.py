"""
Tests for Step 9: Delete Expense (POST /expenses/<id>/delete).

Spec: .claude/specs/09-delete-expense.md

These tests are written strictly from the spec's contract, not from reading
app.py's current implementation:
    - POST /expenses/<id>/delete requires a logged-in session
      (session["user_id"]); unauthenticated requests redirect to /login (302)
      and must not delete anything.
    - Ownership is enforced by reusing `get_expense_by_id(expense_id, user_id)`
      (from Step 8) to check the expense exists and belongs to the current
      user before deleting — if it returns None, the route must abort 404.
    - `delete_expense(expense_id, user_id)` (new in this step) issues a
      parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?`, so
      it is a silent no-op (no exception, 0 rows affected) when the id
      doesn't exist or belongs to another user.
    - The route only accepts POST — a bare GET to the same URL must return
      405 (Method Not Allowed).
    - On success: the row is removed from the database, the response
      redirects (302) to /profile (not a rendered template), only the
      targeted row is removed (other rows/users' rows are untouched), and
      the deleted expense no longer appears on the profile page afterwards.
    - profile.html's transaction rows must each include a Delete action
      (a POST form) pointing at that row's own `/expenses/<id>/delete` URL,
      alongside the existing Edit action.
"""

from database.db import get_db
from database.queries import delete_expense, get_expense_by_id


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


class TestDeleteExpenseUnit:
    """Unit tests for database.queries.delete_expense, per the spec's table."""

    def test_valid_expense_id_correct_user_id_removes_row_from_db(
        self, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        delete_expense(expense_id, user_id)

        assert _get_expense_row(expense_id) is None, "Row must be removed"

    def test_valid_expense_id_wrong_user_id_leaves_row_and_raises_no_error(
        self, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        attacker_id = make_user(name="Attacker", email="attacker@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        # Must not raise, even though it affects 0 rows.
        delete_expense(expense_id, attacker_id)

        row = _get_expense_row(expense_id)
        assert row is not None, "Row must remain when deleted by a non-owner"
        assert row["amount"] == 25.0
        assert row["category"] == "Food"

    def test_non_existent_expense_id_raises_no_error_and_db_unchanged(
        self, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")

        # Must not raise, even for an id that doesn't exist at all.
        delete_expense(999999, user_id)

        assert _expense_count() == 1, "DB must be unchanged"


class TestDeleteExpenseAuthGuard:
    def test_post_unauthenticated_redirects_to_login(
        self, client, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(f"/expenses/{expense_id}/delete")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_unauthenticated_does_not_delete_the_row(
        self, client, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(f"/expenses/{expense_id}/delete")

        assert _get_expense_row(expense_id) is not None, (
            "Expense must survive an unauthenticated delete attempt"
        )


class TestDeleteExpenseOwnershipAndNotFound:
    def test_post_other_users_expense_returns_404(
        self, client, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        _login(client, make_user, name="Attacker", email="attacker@example.com")

        response = client.post(f"/expenses/{expense_id}/delete")

        assert response.status_code == 404

    def test_post_other_users_expense_does_not_delete_the_row(
        self, client, make_user, make_expense
    ):
        owner_id = make_user(name="Owner", email="owner@example.com")
        make_expense(owner_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(owner_id)

        _login(client, make_user, name="Attacker", email="attacker@example.com")

        client.post(f"/expenses/{expense_id}/delete")

        row = _get_expense_row(expense_id)
        assert row is not None, "Another user's expense must not be deletable"
        assert row["amount"] == 25.0
        assert row["category"] == "Food"

    def test_post_non_existent_id_returns_404(self, client, make_user):
        _login(client, make_user)

        response = client.post("/expenses/999999/delete")

        assert response.status_code == 404


class TestDeleteExpenseHappyPath:
    def test_valid_delete_redirects_to_profile(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(f"/expenses/{expense_id}/delete")

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_valid_delete_removes_the_row_from_the_database(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.post(f"/expenses/{expense_id}/delete")

        assert _get_expense_row(expense_id) is None
        assert _expense_count(user_id) == 0

    def test_only_the_targeted_expense_is_removed(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        first_id = _latest_expense_id(user_id)
        make_expense(user_id, 40.0, "Bills", "2026-03-02", "Water bill")
        second_id = _latest_expense_id(user_id)

        response = client.post(f"/expenses/{first_id}/delete")

        assert response.status_code == 302
        assert _get_expense_row(first_id) is None, "Targeted row must be gone"
        row = _get_expense_row(second_id)
        assert row is not None, "Untargeted row must survive"
        assert row["category"] == "Bills"
        assert row["description"] == "Water bill"
        assert _expense_count(user_id) == 1

    def test_deleting_one_users_expense_does_not_touch_another_users_expenses(
        self, client, make_user, make_expense
    ):
        other_id = make_user(name="Other", email="other@example.com")
        make_expense(other_id, 15.0, "Health", "2026-03-01", "Other's expense")
        other_expense_id = _latest_expense_id(other_id)

        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        own_expense_id = _latest_expense_id(user_id)

        client.post(f"/expenses/{own_expense_id}/delete")

        assert _get_expense_row(own_expense_id) is None
        assert _get_expense_row(other_expense_id) is not None
        assert _expense_count(other_id) == 1

    def test_deleted_expense_no_longer_appears_on_profile_after_redirect(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Deleted Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(
            f"/expenses/{expense_id}/delete", follow_redirects=True
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Deleted Lunch" not in body, (
            "Deleted expense must not appear in the transaction list"
        )

    def test_delete_does_not_render_a_template_directly(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.post(f"/expenses/{expense_id}/delete")

        # A successful delete must redirect, not render a 200 page directly.
        assert response.status_code == 302


class TestDeleteExpenseMethodNotAllowed:
    def test_get_returns_405_for_own_expense(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/delete")

        assert response.status_code == 405

    def test_get_returns_405_when_unauthenticated(
        self, client, make_user, make_expense
    ):
        user_id = make_user()
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get(f"/expenses/{expense_id}/delete")

        assert response.status_code == 405

    def test_get_does_not_delete_the_row(self, client, make_user, make_expense):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        client.get(f"/expenses/{expense_id}/delete")

        assert _get_expense_row(expense_id) is not None, (
            "A GET request must never delete the expense"
        )


class TestDeleteExpenseNavigation:
    """Definition-of-done items about the profile page's per-row Delete action."""

    def test_profile_transaction_row_has_a_delete_form_for_the_correct_url(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert f"/expenses/{expense_id}/delete" in body, (
            "Profile page must include a Delete action pointing at the "
            "expense's own delete URL"
        )
        assert 'method="POST"' in body or 'method="post"' in body

    def test_profile_transaction_row_shows_both_edit_and_delete_actions(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 25.0, "Food", "2026-03-01", "Lunch")
        expense_id = _latest_expense_id(user_id)

        response = client.get("/profile")
        body = response.get_data(as_text=True)

        assert f"/expenses/{expense_id}/edit" in body, "Edit action must still be present"
        assert f"/expenses/{expense_id}/delete" in body, "Delete action must be present"

    def test_multiple_transactions_each_have_their_own_delete_url(
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

        assert f"/expenses/{first_id}/delete" in body
        assert f"/expenses/{second_id}/delete" in body
