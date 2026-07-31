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


def get_summary_stats(user_id):
    # SUBAGENT 2 (Summary stats): implement this function.
    # Contract: return {"total_spent": <float>, "transaction_count": <int>, "top_category": <str>}
    # total_spent = SUM(amount) across the user's expenses (0 if none)
    # transaction_count = COUNT(*) across the user's expenses (0 if none)
    # top_category = category with the highest SUM(amount) ("—" if none)
    raise NotImplementedError


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT date, description, category, amount
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id):
    # SUBAGENT 3 (Category breakdown): implement this function.
    # Contract: return a list of dicts, each with name, amount, pct (int)
    # Ordered by amount desc. pct values must sum to exactly 100 (floor each,
    # then give the remainder to the largest category). [] if none.
    raise NotImplementedError
