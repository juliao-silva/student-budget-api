# Student Budget API

#### Video Demo: <URL HERE>

#### Description:

Student Budget API is a backend-only REST API that helps students keep track of their money. Users can record income and expenses, set monthly budgets per category, and get simple insights such as how much is left this month, where the money went, and how much they can spend per day. There is no frontend: every endpoint receives and returns JSON.

It is my final project for CS50x, built with Python, Flask and SQLite.

## Features

- **Accounts:** register, log in, log out and delete your account. Passwords are hashed.
- **Transactions:** add, list, edit and delete income and expenses.
- **Filters:** list transactions by month, date range, category or type (income/expense).
- **Categories:** a shared list of defaults for students, such as food, rent, transport, tuition, books, salary, allowance and scholarship.
- **Budgets:** set a spending limit per category for a month or a custom date range.
- **Insights:**
  - monthly summary: income, expenses and what's left
  - spending by category, with percentages
  - budget status: spent, remaining and whether you're over
  - daily allowance: what's left divided by the days left in the month
  - month vs. month: how this month compares to the last one
  - alerts: budgets that are 80% or more used
- **CSV export:** download your transactions as a spreadsheet.

## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask run --port 5001
```

The database (`budget.db`) is created automatically from `schema.sql` the first time the app starts. On macOS, port 5000 is used by AirPlay, which is why the example uses 5001.

The API uses session cookies, so log in first with a tool that keeps cookies, such as Thunder Client or Postman.

## Endpoints

| Method | Route | What it does |
|---|---|---|
| POST | `/register` | Create an account |
| POST | `/login` | Log in |
| POST | `/logout` | Log out |
| DELETE | `/account` | Delete your account (needs your password) |
| GET | `/categories` | List categories (`?type=income` or `?type=expense`) |
| POST | `/transactions` | Add a transaction |
| GET | `/transactions` | List transactions (`?month=`, `?from=`, `?to=`, `?category_id=`, `?type=`) |
| GET | `/transactions/<id>` | Show one transaction |
| PATCH | `/transactions/<id>` | Edit a transaction |
| DELETE | `/transactions/<id>` | Delete a transaction |
| GET | `/transactions/export` | Download transactions as CSV (same filters as the list) |
| POST | `/budgets` | Add a budget |
| GET | `/budgets` | List budgets (`?month=`) |
| GET | `/budgets/<id>` | Show one budget |
| PATCH | `/budgets/<id>` | Edit a budget |
| DELETE | `/budgets/<id>` | Delete a budget |
| GET | `/budgets/status` | Spent and remaining for each budget |
| GET | `/summary` | Monthly income, expenses and what's left |
| GET | `/spending` | Spending by category |
| GET | `/allowance` | How much you can spend per day |
| GET | `/compare` | This month compared with the previous one |
| GET | `/alerts` | Budgets that are close to or over their limit (`?threshold=`) |

The insight routes use the current month by default, or the one given with `?month=YYYY-MM`.

Example request to add a transaction:

```json
POST /transactions
{"amount": 12.50, "category_id": 4, "date": "2026-11-18", "description": "Lunch"}
```

## Files

- **`app.py`**: the Flask app. It connects to the database, checks the input and defines every route.
- **`budget.py`**: the financial calculations used by the insight routes, such as the monthly summary, spending by category, budget status, daily allowance, month comparison and alerts.
- **`schema.sql`**: the database structure, with four tables: `users`, `categories`, `transactions` and `budgets`.
- **`requirements.txt`**: the Python packages needed to run the project.

## Design choices

- **Money is stored in cents.** Amounts are saved as whole numbers (€12.50 is stored as 1250) to avoid rounding errors with decimals. The API converts them to euros only in its responses.
- **Income or expense is decided by the category, not by the sign of the amount.** Amounts are always positive, and each category has a type. This keeps the data simple and avoids mistakes with negative numbers.
- **Categories are shared.** All users get the same default list. This keeps the project smaller, though custom categories per user would be a possible next step.
- **Every query is filtered by the logged-in user**, so users can only see and change their own data.
- **User input is always passed as query placeholders**, never put directly into SQL, to prevent SQL injection.
- **Input is validated before it reaches the database**, and errors come back as clear JSON messages instead of crashes.
- **Budgets can't overlap.** You can't have two budgets for the same category covering the same days, so the budget status is never ambiguous.
- **Backend only.** I chose to focus on the API and its logic rather than a user interface.

## Acknowledgements

#### AI use:
I used AI to help plan the project's execution, handle errors, and learn how to implement certain features. I wrote the code and made the design decisions myself.
