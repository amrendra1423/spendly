from calendar import monthrange
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, get_user_by_email, CATEGORIES
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
)

app = Flask(__name__)
# TODO: move to an environment variable before production
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Formatting helpers                                                  #
# ------------------------------------------------------------------ #

def _currency(amount):
    return f"₹{amount:,.2f}"


def _display_date(iso_date):
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%b %d, %Y")


def _initials(name):
    words = name.split()
    return "".join(word[0] for word in words[:2]).upper()


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _subtract_months(d, months):
    total_months = d.month - 1 - months
    year = d.year + total_months // 12
    month = total_months % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _build_presets(today):
    return [
        {
            "key": "this_month",
            "label": "This Month",
            "date_from": today.replace(day=1).strftime("%Y-%m-%d"),
            "date_to": today.strftime("%Y-%m-%d"),
        },
        {
            "key": "last_3_months",
            "label": "Last 3 Months",
            "date_from": _subtract_months(today, 3).strftime("%Y-%m-%d"),
            "date_to": today.strftime("%Y-%m-%d"),
        },
        {
            "key": "last_6_months",
            "label": "Last 6 Months",
            "date_from": _subtract_months(today, 6).strftime("%Y-%m-%d"),
            "date_to": today.strftime("%Y-%m-%d"),
        },
        {
            "key": "all_time",
            "label": "All Time",
            "date_from": None,
            "date_to": None,
        },
    ]


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template("register.html", error="All fields are required.")

    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match.")

    if get_user_by_email(email):
        return render_template(
            "register.html", error="An account with that email already exists."
        )

    password_hash = generate_password_hash(password)

    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, password_hash),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email) if email and password else None

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.")
        return render_template("login.html")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user_row = get_user_by_id(user_id)
    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": _initials(user_row["name"]),
        "member_since": user_row["member_since"],
    }

    raw_from = request.args.get("date_from", "")
    raw_to = request.args.get("date_to", "")
    parsed_from = _parse_date(raw_from)
    parsed_to = _parse_date(raw_to)

    date_from = date_to = None
    if parsed_from and parsed_to:
        if parsed_from > parsed_to:
            flash("Start date must be before end date.")
        else:
            date_from = parsed_from.strftime("%Y-%m-%d")
            date_to = parsed_to.strftime("%Y-%m-%d")

    presets = _build_presets(datetime.now().date())
    active_preset = "all_time"
    if date_from and date_to:
        active_preset = next(
            (
                p["key"]
                for p in presets
                if p["key"] != "all_time"
                and p["date_from"] == date_from
                and p["date_to"] == date_to
            ),
            "custom",
        )

    # --- BEGIN_STATS_BLOCK ---
    summary = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    stats = {
        "total_spent": _currency(summary["total_spent"]),
        "transaction_count": summary["transaction_count"],
        "top_category": summary["top_category"],
    }
    # --- END_STATS_BLOCK ---

    # --- BEGIN_TRANSACTIONS_BLOCK ---
    transactions = [
        {
            "date": _display_date(tx["date"]),
            "description": tx["description"],
            "category": tx["category"],
            "amount": _currency(tx["amount"]),
        }
        for tx in get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    ]
    # --- END_TRANSACTIONS_BLOCK ---

    # --- BEGIN_CATEGORIES_BLOCK ---
    categories = [
        {
            "name": cat["name"],
            "amount": _currency(cat["amount"]),
            "percent": cat["pct"],
        }
        for cat in get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    ]
    # --- END_CATEGORIES_BLOCK ---

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        filters={"raw_from": raw_from, "raw_to": raw_to},
        presets=presets,
        active_preset=active_preset,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            today=datetime.now().date().strftime("%Y-%m-%d"),
        )

    raw_amount = request.form.get("amount", "")
    category = request.form.get("category", "")
    raw_date = request.form.get("date", "")
    description = request.form.get("description", "").strip()

    form_values = {
        "amount": raw_amount,
        "category": category,
        "date": raw_date,
        "description": description,
    }

    try:
        amount = float(raw_amount)
    except ValueError:
        amount = None

    error = None
    if amount is None or amount <= 0:
        error = "Enter a valid amount greater than 0."
    elif category not in CATEGORIES:
        error = "Select a valid category."
    elif _parse_date(raw_date) is None:
        error = "Enter a valid date."

    if error:
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            today=raw_date or datetime.now().date().strftime("%Y-%m-%d"),
            error=error,
            values=form_values,
        )

    insert_expense(
        session["user_id"], amount, category, raw_date, description or None
    )
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
