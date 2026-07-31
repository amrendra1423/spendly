from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, get_user_by_email
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
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

    # --- BEGIN_STATS_BLOCK ---
    # SUBAGENT 2 (Summary stats): call get_summary_stats(user_id) and build
    # `stats` with total_spent formatted via _currency().
    stats = {
        "total_spent": _currency(0),
        "transaction_count": 0,
        "top_category": "—",
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
        for tx in get_recent_transactions(user_id)
    ]
    # --- END_TRANSACTIONS_BLOCK ---

    # --- BEGIN_CATEGORIES_BLOCK ---
    # SUBAGENT 3 (Category breakdown): call get_category_breakdown(user_id)
    # and build `categories`, renaming `pct` -> `percent` and formatting
    # `amount` via _currency().
    categories = []
    # --- END_CATEGORIES_BLOCK ---

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
