from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, get_user_by_email

app = Flask(__name__)
# TODO: move to an environment variable before production
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


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
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "January 2026",
    }
    stats = {
        "total_spent": "₹24,850",
        "transaction_count": 34,
        "top_category": "Food",
    }
    transactions = [
        {"date": "Jul 27, 2026", "description": "Grocery shopping", "category": "Food", "amount": "₹1,240.00"},
        {"date": "Jul 25, 2026", "description": "Uber ride", "category": "Transport", "amount": "₹380.00"},
        {"date": "Jul 22, 2026", "description": "Electricity bill", "category": "Bills", "amount": "₹2,150.00"},
        {"date": "Jul 19, 2026", "description": "Pharmacy", "category": "Health", "amount": "₹560.00"},
        {"date": "Jul 16, 2026", "description": "Movie night", "category": "Entertainment", "amount": "₹740.00"},
        {"date": "Jul 12, 2026", "description": "New shoes", "category": "Shopping", "amount": "₹3,200.00"},
    ]
    categories = [
        {"name": "Food", "amount": "₹8,420", "percent": 78},
        {"name": "Transport", "amount": "₹4,100", "percent": 55},
        {"name": "Bills", "amount": "₹6,230", "percent": 68},
        {"name": "Health", "amount": "₹1,890", "percent": 30},
        {"name": "Entertainment", "amount": "₹2,540", "percent": 38},
        {"name": "Shopping", "amount": "₹3,900", "percent": 42},
        {"name": "Other", "amount": "₹1,120", "percent": 18},
    ]

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
