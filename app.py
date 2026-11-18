# ===== Core (the minimum for a solid project) =====
# TODO: Accounts: REGISTER, LOG IN, log out, delete account.
# TODO: Transactions: add income or expenses, edit, delete, list them.
# TODO: Filtering: by month, date range, category, or income vs. expense.
# TODO: Categories: list the defaults (food, rent, transport, salary, allowance…).
# TODO: Budgets: set a monthly limit per category, edit, delete.

# ===== Insights (what makes it "fintech") =====
# TODO: Monthly summary: total income, total expenses, and what's left.
# TODO: Spending by category: where the money went this month, as totals and percentages.
# TODO: Budget status: for each budget, how much is spent, how much remains, and whether you're over.
# TODO: Month vs. month: "you spent 20% more on food than last month."
# TODO: Daily allowance: "you have €140 left and 10 days to go, so about €14/day."

# ===== Standout extras (pick one or two) =====
# TODO: Recurring transactions: rent, phone, subscriptions added automatically each month.
# TODO: Savings goals: "€300 for a trip by June," with progress tracking.
# TODO: Alerts: flag when a category hits 80% of its budget.
# TODO: CSV export: download your transactions for a spreadsheet.
# TODO: Student-specific touches: default categories like tuition (propinas), transport pass, cantina, books.

import sqlite3
from flask import Flask, session, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-me"

def get_db():
    conn = sqlite3.connect("budget.db")
    conn.row_factory = sqlite3.Row
    return conn

def register(username, email, password):
    username = username.strip()
    email = email.strip().lower()
    if not username or "@" not in email:
        raise ValueError("A username and a valid email are required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),)
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def login(username, email, password):
    username = username.strip()
    email = email.strip().lower()
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, email, password_hash FROM users "
            "WHERE username = ? AND email = ?",
            (username, email),
        ).fetchone()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None
    finally:
        conn.close()
    if user is None or not check_password_hash(user["password_hash"], password):
        return None
    return {"id": user["id"], "username": user["username"], "email": user["email"]}

@app.post("/login")
def login_route():
    data = request.get_json(silent=True) or {}
    user = login(
        data.get("username", ""),
        data.get("email", ""),
        data.get("password", ""),
    )
    if user is None:
        return jsonify(error="Invalid credentials"), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(user)

@app.post("/logout")
def logout_route():
    session.clear()
    return jsonify(message="Logged out")
