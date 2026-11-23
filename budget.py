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
