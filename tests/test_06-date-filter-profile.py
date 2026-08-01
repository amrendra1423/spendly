"""
Tests for the Step 6 date-range filter on GET /profile.

Spec: .claude/specs/06-date-filter-profile.md

These tests treat the spec as the source of truth for behaviour:
    - `date_from` / `date_to` are optional ISO (`YYYY-MM-DD`) query params on
      the existing `GET /profile` route (no new routes).
    - Absent or malformed params -> fall back to an unfiltered ("All Time")
      view rather than erroring.
    - A reversed range (`date_from > date_to`) falls back to unfiltered *and*
      flashes "Start date must be before end date."
    - A one-sided range (only one of the two params valid) is treated as
      fully unfiltered (resolved ambiguity given to this test suite).
    - All three profile sections (summary stats, recent transactions,
      category breakdown) must reflect the same active filter.
    - With no date args, `get_summary_stats`, `get_recent_transactions`, and
      `get_category_breakdown` in `database/queries.py` must behave exactly
      as they did before this feature (Step 5 behaviour).
"""

from calendar import monthrange
from datetime import date, timedelta

import pytest

from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# --------------------------------------------------------------------- #
# Test-local helpers (NOT copied from app.py — independent computation  #
# of "N calendar months before a date", used only to build fixture data #
# and expected query params for the preset windows described in the     #
# spec's Definition of Done).                                           #
# --------------------------------------------------------------------- #

def _iso(d):
    return d.strftime("%Y-%m-%d")


def _months_before(d, months):
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _login(client, make_user, name="Filter User", email="filter@example.com"):
    user_id = make_user(name=name, email=email)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name
    return user_id


def _assert_total_and_count(body, total, count):
    assert "₹" in body, "Amounts must always display the rupee symbol"
    assert f"{total:.2f}" in body, f"Expected total {total:.2f} in body"
    assert f">{count}<" in body, f"Expected transaction_count {count} in body"


# --------------------------------------------------------------------- #
# Shared fixture: a user with five expenses spread across "today",      #
# "earlier this month", "last month", "~4 months ago" and "~8 months    #
# ago" relative windows, with generous margins around the 3-month and   #
# 6-month preset boundaries so the assertions are robust regardless of  #
# exactly how those boundaries are computed.                            #
# --------------------------------------------------------------------- #

class _DatedExpenses:
    def __init__(self, client, user_id, dates):
        self.client = client
        self.user_id = user_id
        self.dates = dates


@pytest.fixture
def dated_expenses(client, make_user, make_expense):
    user_id = _login(client, make_user)

    today = date.today()
    this_month_start = today.replace(day=1)
    last_3_start = _months_before(today, 3)
    last_6_start = _months_before(today, 6)

    dates = {
        "today": today,
        "this_month_start": this_month_start,
        "prev_month_last_day": this_month_start - timedelta(days=1),
        "four_ish_months_ago": last_3_start - timedelta(days=10),
        "eight_ish_months_ago": last_6_start - timedelta(days=20),
        "last_3_start": last_3_start,
        "last_6_start": last_6_start,
    }

    make_expense(user_id, 10.00, "Food", _iso(dates["today"]), "TodayExpense")
    make_expense(user_id, 20.00, "Transport", _iso(dates["this_month_start"]), "ThisMonthStart")
    make_expense(user_id, 30.00, "Bills", _iso(dates["prev_month_last_day"]), "PrevMonthLastDay")
    make_expense(user_id, 40.00, "Health", _iso(dates["four_ish_months_ago"]), "FourMonthsAgo")
    make_expense(user_id, 50.00, "Entertainment", _iso(dates["eight_ish_months_ago"]), "EightMonthsAgo")

    return _DatedExpenses(client, user_id, dates)


# --------------------------------------------------------------------- #
# Happy paths                                                           #
# --------------------------------------------------------------------- #

class TestProfileDateFilterHappyPath:
    def test_no_query_params_is_unfiltered_matches_pre_existing_behaviour(self, dated_expenses):
        response = dated_expenses.client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        # All 5 expenses (10+20+30+40+50) must be included with no filter.
        _assert_total_and_count(body, 150.00, 5)
        for description in (
            "TodayExpense", "ThisMonthStart", "PrevMonthLastDay",
            "FourMonthsAgo", "EightMonthsAgo",
        ):
            assert description in body, f"{description} missing from unfiltered view"

    def test_this_month_preset_filters_to_current_calendar_month(self, dated_expenses):
        d = dated_expenses.dates
        response = dated_expenses.client.get(
            f"/profile?date_from={_iso(d['this_month_start'])}&date_to={_iso(d['today'])}"
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 30.00, 2)  # Today (10) + ThisMonthStart (20)
        assert "TodayExpense" in body
        assert "ThisMonthStart" in body
        assert "PrevMonthLastDay" not in body
        assert "FourMonthsAgo" not in body
        assert "EightMonthsAgo" not in body

    def test_last_3_months_preset_filters_to_three_month_window(self, dated_expenses):
        d = dated_expenses.dates
        response = dated_expenses.client.get(
            f"/profile?date_from={_iso(d['last_3_start'])}&date_to={_iso(d['today'])}"
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 60.00, 3)  # Today + ThisMonthStart + PrevMonthLastDay
        assert "PrevMonthLastDay" in body
        assert "FourMonthsAgo" not in body
        assert "EightMonthsAgo" not in body

    def test_last_6_months_preset_filters_to_six_month_window(self, dated_expenses):
        d = dated_expenses.dates
        response = dated_expenses.client.get(
            f"/profile?date_from={_iso(d['last_6_start'])}&date_to={_iso(d['today'])}"
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 100.00, 4)  # everything except EightMonthsAgo
        assert "FourMonthsAgo" in body
        assert "EightMonthsAgo" not in body

    def test_all_time_preset_passes_no_params_and_shows_everything(self, dated_expenses):
        # Per spec: "The 'All Time' preset must pass no query params
        # (clean /profile URL)".
        response = dated_expenses.client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 150.00, 5)

    def test_valid_custom_range_filters_all_three_sections_consistently(self, dated_expenses):
        d = dated_expenses.dates
        response = dated_expenses.client.get(
            f"/profile?date_from={_iso(d['four_ish_months_ago'])}&date_to={_iso(d['prev_month_last_day'])}"
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        # Only FourMonthsAgo (Health, 40) and PrevMonthLastDay (Bills, 30).
        _assert_total_and_count(body, 70.00, 2)
        # Recent transactions section.
        assert "FourMonthsAgo" in body
        assert "PrevMonthLastDay" in body
        assert "TodayExpense" not in body
        assert "ThisMonthStart" not in body
        assert "EightMonthsAgo" not in body
        # Category breakdown section reflects only the two matching categories.
        assert "Health" in body
        assert "Bills" in body
        assert "Transport" not in body
        assert "Entertainment" not in body


# --------------------------------------------------------------------- #
# Edge cases                                                            #
# --------------------------------------------------------------------- #

class TestProfileDateFilterEdgeCases:
    def test_range_with_zero_matching_expenses_shows_empty_zero_state(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 15.00, "Food", "2020-01-01", "OldExpense")

        far_future_from = _iso(date.today() + timedelta(days=1000))
        far_future_to = _iso(date.today() + timedelta(days=1010))
        response = client.get(f"/profile?date_from={far_future_from}&date_to={far_future_to}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "0.00" in body
        assert ">0<" in body
        assert "—" in body  # top_category placeholder when there is no data
        assert "OldExpense" not in body
        assert "Food" not in body

    def test_single_day_range_where_date_from_equals_date_to(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        target = date.today() - timedelta(days=15)
        before = target - timedelta(days=1)
        after = target + timedelta(days=1)

        make_expense(user_id, 5.00, "Food", _iso(before), "BeforeTarget")
        make_expense(user_id, 7.50, "Bills", _iso(target), "OnTarget")
        make_expense(user_id, 9.00, "Transport", _iso(after), "AfterTarget")

        response = client.get(f"/profile?date_from={_iso(target)}&date_to={_iso(target)}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 7.50, 1)
        assert "OnTarget" in body
        assert "BeforeTarget" not in body
        assert "AfterTarget" not in body


# --------------------------------------------------------------------- #
# Validation errors                                                     #
# --------------------------------------------------------------------- #

class TestProfileDateFilterValidationErrors:
    def test_malformed_date_from_falls_back_to_unfiltered_without_crashing(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 12.00, "Food", "2020-01-01", "OldOne")
        make_expense(user_id, 18.00, "Bills", _iso(date.today()), "NewOne")

        baseline = client.get("/profile")
        baseline_body = baseline.get_data(as_text=True)

        response = client.get(f"/profile?date_from=not-a-date&date_to={_iso(date.today())}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 30.00, 2)
        assert "OldOne" in body
        assert "NewOne" in body
        # Falls back to exactly the unfiltered rendering of the amounts/counts.
        assert "30.00" in baseline_body
        assert ">2<" in baseline_body

    def test_reversed_range_flashes_error_and_falls_back_to_unfiltered(
        self, client, make_user, make_expense
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 12.00, "Food", "2020-01-01", "OldOne")
        make_expense(user_id, 18.00, "Bills", _iso(date.today()), "NewOne")

        later = _iso(date.today())
        earlier = "2020-01-01"
        # date_from (later) is after date_to (earlier) -> reversed range.
        response = client.get(f"/profile?date_from={later}&date_to={earlier}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Start date must be before end date." in body
        # Falls back to fully unfiltered totals.
        _assert_total_and_count(body, 30.00, 2)
        assert "OldOne" in body
        assert "NewOne" in body

    @pytest.mark.parametrize(
        "query_string",
        [
            "date_from={valid}",  # only date_from provided
            "date_to={valid}",    # only date_to provided
        ],
    )
    def test_one_sided_range_treated_as_fully_unfiltered(
        self, client, make_user, make_expense, query_string
    ):
        user_id = _login(client, make_user)
        make_expense(user_id, 12.00, "Food", "2020-01-01", "OldOne")
        make_expense(user_id, 18.00, "Bills", _iso(date.today()), "NewOne")

        qs = query_string.format(valid=_iso(date.today()))
        response = client.get(f"/profile?{qs}")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        _assert_total_and_count(body, 30.00, 2)
        assert "OldOne" in body
        assert "NewOne" in body


# --------------------------------------------------------------------- #
# Auth guard                                                            #
# --------------------------------------------------------------------- #

class TestProfileDateFilterAuthGuard:
    def test_unauthenticated_request_redirects_to_login_regardless_of_query_params(self, client):
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_unauthenticated_request_redirects_to_login_with_malformed_params(self, client):
        response = client.get("/profile?date_from=not-a-date&date_to=also-not-a-date")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# DB-level unit tests: database/queries.py date-range params            #
# --------------------------------------------------------------------- #

class TestGetSummaryStatsDateRange:
    def test_filtered_range_only_counts_matching_expenses(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-01-01")
        make_expense(user_id, 25.50, "Bills", "2026-02-01")
        make_expense(user_id, 5.00, "Food", "2026-03-01")

        stats = get_summary_stats(user_id, date_from="2026-01-01", date_to="2026-02-28")

        assert stats["total_spent"] == 35.50
        assert stats["transaction_count"] == 2
        assert stats["top_category"] == "Bills"

    def test_filtered_range_with_no_matches_returns_zero_state(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-01-01")

        stats = get_summary_stats(user_id, date_from="2030-01-01", date_to="2030-12-31")

        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    def test_no_date_args_matches_pre_step6_unfiltered_behaviour(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-07-01")
        make_expense(user_id, 25.50, "Bills", "2026-07-02")
        make_expense(user_id, 5.00, "Food", "2026-07-03")

        stats = get_summary_stats(user_id)

        assert stats["total_spent"] == 40.50
        assert stats["transaction_count"] == 3
        assert stats["top_category"] == "Bills"


class TestGetRecentTransactionsDateRange:
    def test_filtered_range_excludes_out_of_range_transactions(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-01-01", "TooEarly")
        make_expense(user_id, 20.00, "Bills", "2026-02-10", "InRangeOld")
        make_expense(user_id, 15.00, "Transport", "2026-02-20", "InRangeNew")
        make_expense(user_id, 30.00, "Shopping", "2026-04-01", "TooLate")

        txs = get_recent_transactions(user_id, date_from="2026-02-01", date_to="2026-02-28")

        assert [tx["description"] for tx in txs] == ["InRangeNew", "InRangeOld"]

    def test_filtered_range_respects_limit(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-02-01", "First")
        make_expense(user_id, 20.00, "Bills", "2026-02-02", "Second")
        make_expense(user_id, 15.00, "Transport", "2026-02-03", "Third")

        txs = get_recent_transactions(
            user_id, limit=1, date_from="2026-02-01", date_to="2026-02-28"
        )

        assert len(txs) == 1
        assert txs[0]["description"] == "Third"

    def test_no_date_args_matches_pre_step6_unfiltered_behaviour(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-07-01", "Oldest")
        make_expense(user_id, 20.00, "Bills", "2026-07-03", "Newest")
        make_expense(user_id, 15.00, "Transport", "2026-07-02", "Middle")

        txs = get_recent_transactions(user_id)

        assert [tx["description"] for tx in txs] == ["Newest", "Middle", "Oldest"]


class TestGetCategoryBreakdownDateRange:
    def test_filtered_range_only_includes_matching_categories(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-01-01")
        make_expense(user_id, 20.00, "Bills", "2026-02-10")
        make_expense(user_id, 30.00, "Transport", "2026-02-20")

        breakdown = get_category_breakdown(user_id, date_from="2026-02-01", date_to="2026-02-28")

        names = {item["name"] for item in breakdown}
        assert names == {"Bills", "Transport"}
        assert sum(item["pct"] for item in breakdown) == 100
        assert all(isinstance(item["pct"], int) for item in breakdown)
        amounts = [item["amount"] for item in breakdown]
        assert amounts == sorted(amounts, reverse=True)

    def test_filtered_range_with_no_matches_returns_empty_list(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.00, "Food", "2026-01-01")

        breakdown = get_category_breakdown(user_id, date_from="2030-01-01", date_to="2030-12-31")

        assert breakdown == []

    def test_no_date_args_matches_pre_step6_unfiltered_behaviour(self, make_user, make_expense):
        user_id = make_user()
        make_expense(user_id, 10.01, "Bills", "2026-07-01")
        make_expense(user_id, 10.00, "Food", "2026-07-02")
        make_expense(user_id, 10.00, "Transport", "2026-07-03")

        breakdown = get_category_breakdown(user_id)

        assert breakdown[0]["name"] == "Bills"
        assert sum(item["pct"] for item in breakdown) == 100
        assert all(isinstance(item["pct"], int) for item in breakdown)
