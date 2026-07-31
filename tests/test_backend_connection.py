from datetime import datetime

import database.db as db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# --------------------------------------------------------------------- #
# get_user_by_id                                                        #
# --------------------------------------------------------------------- #

def test_get_user_by_id_valid(make_user):
    user_id = make_user(name="Ada Lovelace", email="ada@example.com")

    result = get_user_by_id(user_id)

    assert result["name"] == "Ada Lovelace"
    assert result["email"] == "ada@example.com"
    assert result["member_since"] == datetime.now().strftime("%B %Y")


def test_get_user_by_id_missing():
    assert get_user_by_id(999) is None


# --------------------------------------------------------------------- #
# get_summary_stats                                                     #
# --------------------------------------------------------------------- #

def test_get_summary_stats_with_expenses(make_user, make_expense):
    user_id = make_user()
    make_expense(user_id, 10.00, "Food", "2026-07-01")
    make_expense(user_id, 25.50, "Bills", "2026-07-02")
    make_expense(user_id, 5.00, "Food", "2026-07-03")

    stats = get_summary_stats(user_id)

    assert stats["total_spent"] == 40.50
    assert stats["transaction_count"] == 3
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(make_user):
    user_id = make_user()

    stats = get_summary_stats(user_id)

    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# --------------------------------------------------------------------- #
# get_recent_transactions                                               #
# --------------------------------------------------------------------- #

def test_get_recent_transactions_with_expenses(make_user, make_expense):
    user_id = make_user()
    make_expense(user_id, 10.00, "Food", "2026-07-01", "Oldest")
    make_expense(user_id, 20.00, "Bills", "2026-07-03", "Newest")
    make_expense(user_id, 15.00, "Transport", "2026-07-02", "Middle")

    txs = get_recent_transactions(user_id)

    assert [tx["description"] for tx in txs] == ["Newest", "Middle", "Oldest"]
    assert txs[0]["date"] == "2026-07-03"
    assert txs[0]["category"] == "Bills"
    assert txs[0]["amount"] == 20.00


def test_get_recent_transactions_no_expenses(make_user):
    user_id = make_user()
    assert get_recent_transactions(user_id) == []


# --------------------------------------------------------------------- #
# get_category_breakdown                                                #
# --------------------------------------------------------------------- #

def test_get_category_breakdown_with_expenses(make_user, make_expense):
    user_id = make_user()
    make_expense(user_id, 10.01, "Bills", "2026-07-01")
    make_expense(user_id, 10.00, "Food", "2026-07-02")
    make_expense(user_id, 10.00, "Transport", "2026-07-03")

    breakdown = get_category_breakdown(user_id)

    assert breakdown[0]["name"] == "Bills"
    assert sum(item["pct"] for item in breakdown) == 100
    assert all(isinstance(item["pct"], int) for item in breakdown)
    amounts = [item["amount"] for item in breakdown]
    assert amounts == sorted(amounts, reverse=True)


def test_get_category_breakdown_no_expenses(make_user):
    user_id = make_user()
    assert get_category_breakdown(user_id) == []


# --------------------------------------------------------------------- #
# GET /profile route                                                    #
# --------------------------------------------------------------------- #

def test_profile_unauthenticated_redirects_to_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated_as_seed_user(client):
    # seed_db() is the app's real demo-data loader; the spec's Definition of
    # done states total_spent should be 346.24, but seed_db()'s 8 hardcoded
    # rows actually sum to 269.74 — asserting the real figure here.
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")

    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]
        sess["user_name"] = demo_user["name"]

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "269.74" in body
    assert ">8<" in body  # transaction_count stat tile
    assert "Bills" in body
    assert body.index("Restaurant") < body.index("Groceries")  # newest-first
    for category in db.CATEGORIES:
        assert category in body


def test_profile_new_user_zero_state(client, make_user):
    user_id = make_user(name="Fresh User", email="fresh@example.com")

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Fresh User"

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "0.00" in body
    assert ">0<" in body
    assert "—" in body
