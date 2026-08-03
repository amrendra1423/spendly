from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created_at.strftime("%B %Y"),
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()

    params = [user_id]
    date_clause = ""
    if date_from is not None and date_to is not None:
        date_clause = " AND date BETWEEN ? AND ?"
        params.extend([date_from, date_to])

    totals = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
        "FROM expenses WHERE user_id = ?" + date_clause,
        params,
    ).fetchone()

    top = conn.execute(
        """
        SELECT category
        FROM expenses
        WHERE user_id = ?""" + date_clause + """
        GROUP BY category
        ORDER BY SUM(amount) DESC
        LIMIT 1
        """,
        params,
    ).fetchone()

    conn.close()

    return {
        "total_spent": totals["total"],
        "transaction_count": totals["count"],
        "top_category": top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()

    params = [user_id]
    date_clause = ""
    if date_from is not None and date_to is not None:
        date_clause = " AND date BETWEEN ? AND ?"
        params.extend([date_from, date_to])
    params.append(limit)

    rows = conn.execute(
        """
        SELECT id, date, description, category, amount
        FROM expenses
        WHERE user_id = ?""" + date_clause + """
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def update_expense(expense_id, user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        """
        UPDATE expenses
        SET amount = ?, category = ?, date = ?, description = ?
        WHERE id = ? AND user_id = ?
        """,
        (amount, category, date, description, expense_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()


def insert_expense(user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()

    params = [user_id]
    date_clause = ""
    if date_from is not None and date_to is not None:
        date_clause = " AND date BETWEEN ? AND ?"
        params.extend([date_from, date_to])

    rows = conn.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?""" + date_clause + """
        GROUP BY category
        ORDER BY total DESC
        """,
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)

    breakdown = []
    for row in rows:
        exact_pct = (row["total"] / grand_total) * 100
        breakdown.append(
            {"name": row["category"], "amount": row["total"], "pct": int(exact_pct)}
        )

    remainder = 100 - sum(item["pct"] for item in breakdown)
    if breakdown:
        breakdown[0]["pct"] += remainder

    return breakdown
