# ===== Core (the minimum for a solid project) =====
# DONE: Accounts
# DONE: Transactions
# DONE: Filtering
# DONE: Categories
# DONE: Budgets

# ===== Insights (what makes it "fintech") =====
# DONE: Monthly summary
# DONE: Spending by category
# DONE: Budget status
# DONE: Month vs. month
# DONE: Daily allowance

# ===== Standout extras (pick one or two) =====
# TODO: Recurring transactions: rent, phone, subscriptions added automatically each month.
# TODO: Savings goals: "€300 for a trip by June," with progress tracking.
# TODO: Alerts: flag when a category hits 80% of its budget.
# TODO: CSV export: download your transactions for a spreadsheet.
# TODO: Student-specific touches: default categories like tuition (propinas), transport pass, cantina, books.

import os
import secrets
import sqlite3
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, session, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from budget import monthly_summary, spending_by_category, budget_status, daily_allowance, compare_months

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BUDGET_DB", os.path.join(BASE_DIR, "budget.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

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
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()
        if not exists:
            with open(SCHEMA_PATH) as f:
                conn.executescript(f.read())
        with conn:
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
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            return False
        with conn:
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

@app.get("/categories")
@login_required
def list_categories():
    category_type = request.args.get("type")
    if category_type is not None and category_type not in ("income", "expense"):
        return jsonify(error="type must be income or expense."), 400
    query = "SELECT id, name, type FROM categories"
    params = ()
    if category_type:
        query += " WHERE type = ?"
        params = (category_type,)
    conn = get_db()
    try:
        rows = conn.execute(query + " ORDER BY type DESC, name", params).fetchall()
    finally:
        conn.close()
    return jsonify([dict(row) for row in rows])

TRANSACTION_SELECT = """
    SELECT t.id, t.amount, t.transaction_date, t.description,
           t.category_id, c.name AS category, c.type
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
"""

def parse_amount(value):
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
    try:
        year, month = (int(part) for part in value.split("-"))
        start = date(year, month, 1)
    except ValueError:
        raise ValueError("month must look like 2026-11.")
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()

def transaction_filters(args):
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

BUDGET_SELECT = """
    SELECT b.id, b.category_id, c.name AS category, b.amount, b.start_date, b.end_date
    FROM budgets b
    JOIN categories c ON c.id = b.category_id
"""

class BudgetConflict(Exception):
    pass

def budget_to_dict(row):
    return {
        "id": row["id"],
        "category_id": row["category_id"],
        "category": row["category"],
        "amount": row["amount"] / 100,
        "start_date": row["start_date"],
        "end_date": row["end_date"],
    }

def get_budget(conn, user_id, budget_id):
    return conn.execute(
        BUDGET_SELECT + " WHERE b.id = ? AND b.user_id = ?",
        (budget_id, user_id),
    ).fetchone()

def validate_budget(conn, user_id, data, current=None):
    fields = {}
    if "amount" in data or current is None:
        fields["amount"] = parse_amount(data.get("amount"))
    if "category_id" in data or current is None:
        category_id = data.get("category_id")
        if not isinstance(category_id, int) or isinstance(category_id, bool):
            raise ValueError("category_id must be an integer.")
        category = conn.execute(
            "SELECT type FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if category is None:
            raise ValueError("Unknown category_id.")
        if category["type"] != "expense":
            raise ValueError("Budgets can only be set on expense categories.")
        fields["category_id"] = category_id
    if "month" in data:
        if "start_date" in data or "end_date" in data:
            raise ValueError("Use either month or start_date/end_date, not both.")
        if not isinstance(data["month"], str):
            raise ValueError("month must look like 2026-11.")
        start, next_month = parse_month(data["month"])
        fields["start_date"] = start
        fields["end_date"] = (date.fromisoformat(next_month) - timedelta(days=1)).isoformat()
    else:
        for key in ("start_date", "end_date"):
            if key in data:
                fields[key] = parse_date(data[key])
            elif current is None:
                raise ValueError("Send month, or both start_date and end_date.")
    merged = {**(dict(current) if current else {}), **fields}
    if merged["end_date"] <= merged["start_date"]:
        raise ValueError("end_date must be after start_date.")
    overlap = conn.execute(
        "SELECT 1 FROM budgets WHERE user_id = ? AND category_id = ? AND id != ? "
        "AND start_date <= ? AND end_date >= ?",
        (user_id, merged["category_id"], current["id"] if current else 0,
         merged["end_date"], merged["start_date"]),
    ).fetchone()
    if overlap:
        raise BudgetConflict("You already have a budget for this category in that period.")
    return fields

@app.post("/budgets")
@login_required
def add_budget():
    data = get_json_object()
    if data is None:
        return jsonify(error="Expected a JSON object."), 400
    user_id = session["user_id"]
    conn = get_db()
    try:
        try:
            fields = validate_budget(conn, user_id, data)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except BudgetConflict as e:
            return jsonify(error=str(e)), 409
        with conn:
            cursor = conn.execute(
                "INSERT INTO budgets (user_id, category_id, amount, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, fields["category_id"], fields["amount"],
                 fields["start_date"], fields["end_date"]),
            )
        row = get_budget(conn, user_id, cursor.lastrowid)
        return jsonify(budget_to_dict(row)), 201
    finally:
        conn.close()

@app.get("/budgets")
@login_required
def list_budgets():
    conditions, params = ["b.user_id = ?"], [session["user_id"]]
    if "month" in request.args:
        try:
            start, next_month = parse_month(request.args["month"])
        except ValueError as e:
            return jsonify(error=str(e)), 400
        conditions.append("b.start_date < ? AND b.end_date >= ?")
        params += [next_month, start]
    conn = get_db()
    try:
        rows = conn.execute(
            BUDGET_SELECT + " WHERE " + " AND ".join(conditions)
            + " ORDER BY b.start_date DESC, c.name",
            params,
        ).fetchall()
    finally:
        conn.close()
    return jsonify([budget_to_dict(row) for row in rows])

@app.get("/budgets/<int:budget_id>")
@login_required
def show_budget(budget_id):
    conn = get_db()
    try:
        row = get_budget(conn, session["user_id"], budget_id)
    finally:
        conn.close()
    if row is None:
        return jsonify(error="Budget not found."), 404
    return jsonify(budget_to_dict(row))

@app.patch("/budgets/<int:budget_id>")
@login_required
def edit_budget(budget_id):
    data = get_json_object()
    if data is None:
        return jsonify(error="Expected a JSON object."), 400
    user_id = session["user_id"]
    conn = get_db()
    try:
        current = get_budget(conn, user_id, budget_id)
        if current is None:
            return jsonify(error="Budget not found."), 404
        try:
            fields = validate_budget(conn, user_id, data, current)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except BudgetConflict as e:
            return jsonify(error=str(e)), 409
        if not fields:
            return jsonify(error="Nothing to update. Send amount, category_id, month, start_date or end_date."), 400
        set_clause = ", ".join(f"{column} = ?" for column in fields)
        with conn:
            conn.execute(
                f"UPDATE budgets SET {set_clause} WHERE id = ? AND user_id = ?",
                (*fields.values(), budget_id, user_id),
            )
        row = get_budget(conn, user_id, budget_id)
        return jsonify(budget_to_dict(row))
    finally:
        conn.close()

@app.delete("/budgets/<int:budget_id>")
@login_required
def delete_budget(budget_id):
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM budgets WHERE id = ? AND user_id = ?",
                (budget_id, session["user_id"]),
            )
    finally:
        conn.close()
    if cursor.rowcount == 0:
        return jsonify(error="Budget not found."), 404
    return jsonify(message="Budget deleted")

def requested_month():
    return parse_month(request.args.get("month", date.today().strftime("%Y-%m")))

@app.get("/summary")
@login_required
def summary_route():
    try:
        start, end = requested_month()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    conn = get_db()
    try:
        summary = monthly_summary(conn, session["user_id"], start, end)
    finally:
        conn.close()
    return jsonify(
        month=start[:7],
        income=summary["income"] / 100,
        expenses=summary["expenses"] / 100,
        left=summary["left"] / 100,
        transactions=summary["transactions"],
    )

@app.get("/spending")
@login_required
def spending_route():
    try:
        start, end = requested_month()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    conn = get_db()
    try:
        spending = spending_by_category(conn, session["user_id"], start, end)
    finally:
        conn.close()
    for category in spending["categories"]:
        category["total"] /= 100
    return jsonify(month=start[:7], total=spending["total"] / 100, categories=spending["categories"])

@app.get("/budgets/status")
@login_required
def budget_status_route():
    try:
        start, end = requested_month()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    conn = get_db()
    try:
        budgets = budget_status(conn, session["user_id"], start, end)
    finally:
        conn.close()
    for budget in budgets:
        for key in ("amount", "spent", "remaining"):
            budget[key] /= 100
    return jsonify(month=start[:7], budgets=budgets)

@app.get("/allowance")
@login_required
def allowance_route():
    try:
        start, end = requested_month()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    conn = get_db()
    try:
        allowance = daily_allowance(conn, session["user_id"], start, end, date.today())
    finally:
        conn.close()
    return jsonify(
        month=start[:7],
        left=allowance["left"] / 100,
        days_left=allowance["days_left"],
        per_day=allowance["per_day"] / 100,
    )

@app.get("/compare")
@login_required
def compare_route():
    try:
        start, end = requested_month()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    previous_start = (date.fromisoformat(start) - timedelta(days=1)).replace(day=1).isoformat()
    conn = get_db()
    try:
        comparison = compare_months(conn, session["user_id"], previous_start, start, end)
    finally:
        conn.close()
    for item in [comparison["income"], comparison["expenses"], *comparison["categories"]]:
        item["current"] /= 100
        item["previous"] /= 100
    return jsonify(month=start[:7], previous_month=previous_start[:7], **comparison)
