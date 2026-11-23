def monthly_summary(conn, user_id, start, end):
    row = conn.execute(
        "SELECT "
        "COALESCE(SUM(CASE WHEN c.type = 'income' THEN t.amount END), 0) AS income, "
        "COALESCE(SUM(CASE WHEN c.type = 'expense' THEN t.amount END), 0) AS expenses, "
        "COUNT(*) AS transactions "
        "FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.user_id = ? AND t.transaction_date >= ? AND t.transaction_date < ?",
        (user_id, start, end),
    ).fetchone()
    return {
        "income": row["income"],
        "expenses": row["expenses"],
        "left": row["income"] - row["expenses"],
        "transactions": row["transactions"],
    }

def spending_by_category(conn, user_id, start, end):
    rows = conn.execute(
        "SELECT c.id AS category_id, c.name AS category, SUM(t.amount) AS total "
        "FROM transactions t "
        "JOIN categories c ON c.id = t.category_id "
        "WHERE t.user_id = ? AND c.type = 'expense' "
        "AND t.transaction_date >= ? AND t.transaction_date < ? "
        "GROUP BY c.id "
        "ORDER BY total DESC, c.name",
        (user_id, start, end),
    ).fetchall()
    total = sum(row["total"] for row in rows)
    categories = [
        {
            "category_id": row["category_id"],
            "category": row["category"],
            "total": row["total"],
            "percent": round(row["total"] * 100 / total, 1),
        }
        for row in rows
    ]
    return {"total": total, "categories": categories}

def budget_status(conn, user_id, start, end):
    rows = conn.execute(
        "SELECT b.id, b.category_id, c.name AS category, b.amount, b.start_date, b.end_date, "
        "COALESCE((SELECT SUM(t.amount) FROM transactions t "
        "WHERE t.user_id = b.user_id AND t.category_id = b.category_id "
        "AND t.transaction_date BETWEEN b.start_date AND b.end_date), 0) AS spent "
        "FROM budgets b "
        "JOIN categories c ON c.id = b.category_id "
        "WHERE b.user_id = ? AND b.start_date < ? AND b.end_date >= ? "
        "ORDER BY b.start_date, c.name",
        (user_id, end, start),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "category_id": row["category_id"],
            "category": row["category"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "amount": row["amount"],
            "spent": row["spent"],
            "remaining": row["amount"] - row["spent"],
            "percent_used": round(row["spent"] * 100 / row["amount"], 1),
            "over": row["spent"] > row["amount"],
        }
        for row in rows
    ]
