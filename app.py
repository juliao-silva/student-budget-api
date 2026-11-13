# ===== Core (the minimum for a solid project) =====
# TODO: Accounts: register, log in, log out, delete account.
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

from flask import Flask


def register(user, email, password):
    