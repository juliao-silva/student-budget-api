# ===== Core (the minimum for a solid project) =====
# TODO: Accounts: REGISTER, LOG IN, LOG OUT, delete account.
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

import os
import secrets
import sqlite3
from functools import wraps
from flask import Flask, session, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Set SECRET_KEY in the environment for stable sessions. Without it, a random key is
# used and everyone is logged out whenever the server restarts.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BUDGET_DB", os.path.join(BASE_DIR, "budget.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # needed for ON DELETE CASCADE
    return conn

def init_db():
    """Create the tables from schema.sql if the database is empty."""
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()
        if not exists:
            with open(SCHEMA_PATH) as f:
                conn.executescript(f.read())
    finally:
        conn.close()

init_db()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Login required"), 401
        return view(*args, **kwargs)
    return wrapped

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

def delete_account(user_id, password):
    """Delete the user after re-checking the password.

    Returns True if deleted, False if the user doesn't exist or the password is wrong.
    Related rows (transactions, budgets...) should be removed by ON DELETE CASCADE.
    """
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            return False
        with conn:  # single transaction
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        conn.close()

@app.post("/register")
def register_route():
    data = request.get_json(silent=True) or {}
    try:
        user_id = register(
            data.get("username", ""),
            data.get("email", ""),
            data.get("password", ""),
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if user_id is None:
        return jsonify(error="Username or email already in use"), 409
    return jsonify(id=user_id), 201

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

@app.delete("/account")
@login_required
def delete_account_route():
    data = request.get_json(silent=True) or {}
    if not delete_account(session["user_id"], data.get("password", "")):
        return jsonify(error="Wrong password"), 403
    session.clear()
    return jsonify(message="Account deleted")
