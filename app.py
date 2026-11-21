# ===== Core (the minimum for a solid project) =====
# DONE: Accounts
# DONE: Transactions
# DONE: Filtering
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
from datetime import date
from decimal import Decimal, InvalidOperation
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

# A transaction is income or an expense depending on its category's type.
DEFAULT_CATEGORIES = [
    ("salary", "income"),
    ("allowance", "income"),
    ("scholarship", "income"),
    ("food", "expense"),
    ("rent", "expense"),
    ("transport", "expense"),
    ("tuition", "expense"),
    ("books", "expense"),
    ("bills", "expense"),
    ("health", "expense"),
    ("entertainment", "expense"),
    ("other", "expense"),
]

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
        with conn:  # add any missing default categories (safe to run every start)
            conn.executemany(
                "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?)",
                DEFAULT_CATEGORIES,
            )
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

TRANSACTION_SELECT = """
    SELECT t.id, t.amount, t.transaction_date, t.description,
           t.category_id, c.name AS category, c.type
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
"""

def parse_amount(value):
    """Convert euros (number or string) to integer cents."""
    if value is None or isinstance(value, bool):
        raise ValueError("amount is required.")
    try:
        euros = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("amount must be a number.")
    if not euros.is_finite() or euros <= 0:
        raise ValueError("amount must be greater than 0.")
    if euros.as_tuple().exponent < -2:
        raise ValueError("amount can have at most 2 decimal places.")
    return int(euros * 100)

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string like 2026-11-18.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("date must look like 2026-11-18.")

def validate_transaction(conn, data, partial):
    """Return the columns to save. With partial=True, only the fields sent are checked."""
    fields = {}
    if "amount" in data or not partial:
        fields["amount"] = parse_amount(data.get("amount"))
    if "category_id" in data or not partial:
        category_id = data.get("category_id")
        if not isinstance(category_id, int) or isinstance(category_id, bool):
            raise ValueError("category_id must be an integer.")
        if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
            raise ValueError("Unknown category_id.")
        fields["category_id"] = category_id
    if "date" in data:
        fields["transaction_date"] = parse_date(data["date"])
    elif not partial:
        fields["transaction_date"] = date.today().isoformat()
    if "description" in data:
        description = data["description"]
        if description is not None and not isinstance(description, str):
            raise ValueError("description must be text.")
        fields["description"] = (description.strip() or None) if description else None
    return fields

def transaction_to_dict(row):
    return {
        "id": row["id"],
        "amount": row["amount"] / 100,
        "type": row["type"],
        "category_id": row["category_id"],
        "category": row["category"],
        "date": row["transaction_date"],
        "description": row["description"],
    }

def get_transaction(conn, user_id, transaction_id):
    return conn.execute(
        TRANSACTION_SELECT + " WHERE t.id = ? AND t.user_id = ?",
        (transaction_id, user_id),
    ).fetchone()

def get_json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None

@app.post("/transactions")
@login_required
def add_transaction():
    data = get_json_object()
    if data is None:
        return jsonify(error="Expected a JSON object."), 400
    user_id = session["user_id"]
    conn = get_db()
    try:
        try:
            fields = validate_transaction(conn, data, partial=False)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        with conn:
            cursor = conn.execute(
                "INSERT INTO transactions (user_id, category_id, amount, transaction_date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, fields["category_id"], fields["amount"],
                 fields["transaction_date"], fields.get("description")),
            )
        row = get_transaction(conn, user_id, cursor.lastrowid)
        return jsonify(transaction_to_dict(row)), 201
    finally:
        conn.close()

def parse_month(value):
    """Turn "2026-11" into the first day of that month and of the next one."""
    try:
        year, month = (int(part) for part in value.split("-"))
        start = date(year, month, 1)
    except ValueError:
        raise ValueError("month must look like 2026-11.")
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()

def transaction_filters(args):
    """Build extra WHERE conditions from the query string.

    Supported: ?month=YYYY-MM, ?from=YYYY-MM-DD, ?to=YYYY-MM-DD (both inclusive),
    ?category_id=N and ?type=income|expense. They can be combined.
    """
    conditions, params = [], []
    if "month" in args:
        if "from" in args or "to" in args:
            raise ValueError("Use either month or from/to, not both.")
        start, end = parse_month(args["month"])
        conditions.append("t.transaction_date >= ? AND t.transaction_date < ?")
        params += [start, end]
    if "from" in args:
        conditions.append("t.transaction_date >= ?")
        params.append(parse_date(args["from"]))
    if "to" in args:
        conditions.append("t.transaction_date <= ?")
        params.append(parse_date(args["to"]))
    if "from" in args and "to" in args and params[-2] > params[-1]:
        raise ValueError("from must be on or before to.")
    if "category_id" in args:
        try:
            category_id = int(args["category_id"])
        except ValueError:
            raise ValueError("category_id must be an integer.")
        conditions.append("t.category_id = ?")
        params.append(category_id)
    if "type" in args:
        if args["type"] not in ("income", "expense"):
            raise ValueError("type must be income or expense.")
        conditions.append("c.type = ?")
        params.append(args["type"])
    return conditions, params

@app.get("/transactions")
@login_required
def list_transactions():
    try:
        conditions, params = transaction_filters(request.args)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    where = " AND ".join(["t.user_id = ?"] + conditions)
    conn = get_db()
    try:
        rows = conn.execute(
            TRANSACTION_SELECT + f" WHERE {where} ORDER BY t.transaction_date DESC, t.id DESC",
            (session["user_id"], *params),
        ).fetchall()
    finally:
        conn.close()
    return jsonify([transaction_to_dict(row) for row in rows])

@app.get("/transactions/<int:transaction_id>")
@login_required
def show_transaction(transaction_id):
    conn = get_db()
    try:
        row = get_transaction(conn, session["user_id"], transaction_id)
    finally:
        conn.close()
    if row is None:
        return jsonify(error="Transaction not found."), 404
    return jsonify(transaction_to_dict(row))

@app.patch("/transactions/<int:transaction_id>")
@login_required
def edit_transaction(transaction_id):
    data = get_json_object()
    if data is None:
        return jsonify(error="Expected a JSON object."), 400
    user_id = session["user_id"]
    conn = get_db()
    try:
        if get_transaction(conn, user_id, transaction_id) is None:
            return jsonify(error="Transaction not found."), 404
        try:
            fields = validate_transaction(conn, data, partial=True)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        if not fields:
            return jsonify(error="Nothing to update. Send amount, category_id, date or description."), 400
        set_clause = ", ".join(f"{column} = ?" for column in fields)
        with conn:
            conn.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = ? AND user_id = ?",
                (*fields.values(), transaction_id, user_id),
            )
        row = get_transaction(conn, user_id, transaction_id)
        return jsonify(transaction_to_dict(row))
    finally:
        conn.close()

@app.delete("/transactions/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM transactions WHERE id = ? AND user_id = ?",
                (transaction_id, session["user_id"]),
            )
    finally:
        conn.close()
    if cursor.rowcount == 0:
        return jsonify(error="Transaction not found."), 404
    return jsonify(message="Transaction deleted")
