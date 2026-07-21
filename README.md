# WE_OWE — Student Budget & Shared Expense Hub

> A full-stack web application that helps students plan a monthly budget, manage shared household expenses, split bills fairly, settle balances, scan receipts, coordinate shopping, and understand where their money goes.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00?logo=sqlalchemy&logoColor=white)
![Tests](https://img.shields.io/badge/tests-112%20collected-2ea44f)
![License](https://img.shields.io/badge/academic-project-7c6cff)

## Table of contents

- [Project overview](#project-overview)
- [The problem we solve](#the-problem-we-solve)
- [Team](#team)
- [Main features](#main-features)
- [Technology stack](#technology-stack)
- [How the application works](#how-the-application-works)
- [Run the project locally](#run-the-project-locally)
- [Optional setup](#optional-setup)
- [How to use WE_OWE](#how-to-use-we_owe)
- [Testing and developer tools](#testing-and-developer-tools)
- [Project structure](#project-structure)
- [Database and data safety](#database-and-data-safety)
- [Security](#security)
- [Production deployment](#production-deployment)
- [Project documentation](#project-documentation)

## Project overview

WE_OWE is designed for students and flatmates who need one simple place for both **personal budgeting** and **shared expense management**. A user can create a group, invite flatmates, record an expense, choose who paid, select how it should be divided, track debts, and record the final settlement. The same account also provides a personal monthly budget, recurring bills, savings planning, charts, spending insights, reminders, and multi-currency preferences.

The project began as a shared-expense tracker and grew into a complete student finance hub. It is especially useful for international students who manage fixed monthly costs such as rent, health insurance, broadcasting fees, mobile plans, groceries, and occasional money transfers home.

## The problem we solve

Students living together often use separate tools for budgeting, shopping lists, receipts, reminders, and splitting bills. This creates confusion about:

- who paid for an expense;
- how much each person owes;
- whether a payment has actually been settled;
- which receipt items belong to which friend;
- how much of the monthly budget has already been used; and
- which categories are responsible for overspending.

WE_OWE connects these workflows. Saved transactions are used as the source for balances, budget usage, reports, and recommendations, reducing duplicate entry and calculation mistakes.

## Team

| Team member | Role | Main contribution |
|---|---|---|
| **Gnanasree Shivaji** | Backend & API development | Flask application structure, server-side routes, business logic, APIs/services, authentication, budgeting, reminders, reports, and feature integration |
| **Kaniksha** | Frontend development | Responsive user interface, page layouts, forms, navigation, styling, visual feedback, and interactive JavaScript behavior |
| **Ananya** | Database & testing | Database design, model relationships, data validation, test scenarios, calculation verification, and quality assurance |
| **Kavin** | Scrum Master | Sprint planning, backlog coordination, Trello workflow, progress tracking, team communication, and delivery management |

## Main features

### Account and preferences

- Register, confirm an email address, log in, and log out.
- Strong password validation and secure password hashing.
- Forgot-password and time-limited password-reset flow.
- Choose a timezone and preferred currency: EUR, USD, INR, or GBP.
- Preserve the original currency on existing transactions instead of silently converting historical values.
- Choose immediate and scheduled email-reminder preferences.
- Export personal data as readable JSON or safely delete an account.

### Groups and shared expenses

- Create, edit, and delete expense-sharing groups.
- Invite members by email and manage member/admin roles.
- Add, edit, or delete shared expenses with notes, dates, categories, and receipt attachments.
- Record one or multiple payers for the same expense.
- Split expenses equally, by exact amount, percentage, or shares.
- Keep every group isolated so only its members can access its data.

### Receipts and item assignment

- Upload JPG, PNG, GIF, WebP, or PDF receipts up to 5 MB.
- Scan receipt images using Tesseract OCR.
- Convert detected products into an editable checklist with quantity, unit price, and total price.
- Correct common OCR inconsistencies by validating unit price against quantity and printed line total.
- Assign individual receipt products to different group members before saving the expense.

### Balances and settlements

- Calculate what every member paid, owes, should receive, or must pay.
- Simplify mutual debts into clear settlement suggestions.
- Record a payment, then let the recipient confirm or reject it.
- Cancel pending payments and preserve settlement history.
- Recommend who should pay the next shared expense based on previous contributions.

### Monthly budget planner

- Create, update, reset, or delete a budget for a particular month.
- Set monthly income and an optional savings goal.
- Set editable limits for Rent, Bills, Groceries, Eating out, Money sent home, and Other expenses.
- Add, describe, and delete personal spending entries.
- Manage recurring bills such as health insurance, radio tax, rent, and mobile recharge.
- Confirm when a recurring bill is actually paid, so unconfirmed values are not invented as spending.
- Display money left after spending and optional savings.
- Show threshold warnings and progress bars while keeping progress visually capped at 100%; the written figure can still report the real overspend.
- Display a category donut chart with percentages and hover details.

### Shopping, reminders, and reports

- Maintain a collaborative shopping list with assignee, quantity, category, note, and final price.
- Mark items as purchased and optionally convert real purchases into shared expenses.
- Repair stale shopping-to-expense links if a generated expense is later deleted.
- Create immediate or scheduled payment reminders with delivery tracking.
- Send reminders through SMTP or save them to a local development outbox.
- Generate monthly spending summaries from saved transactions only.
- Filter reports by personal activity, all activity, or an individual group.
- View category breakdowns, monthly trends, plan-versus-actual usage, and data-backed recommendations.
- Export report rows as CSV.

## Technology stack

### Backend

| Technology | How it is used |
|---|---|
| **Python** | Main programming language for business logic, calculations, validation, OCR parsing, background work, and tests |
| **Flask** | Web framework, routing, request handling, application factory, blueprints, CLI commands, and server-side page rendering |
| **Flask-SQLAlchemy / SQLAlchemy** | Object-relational mapping, model relationships, queries, transactions, and support for SQLite or PostgreSQL |
| **Flask-Login** | Authentication sessions, protected routes, current-user handling, and login redirects |
| **Flask-WTF / WTForms** | Server-side forms, validation, CSRF protection, select fields, dates, decimals, and file uploads |
| **itsdangerous** | Signed, expiring email-confirmation and password-reset tokens through Flask's secret key |
| **Python `smtplib`** | Real SMTP email delivery for confirmations, invitations, resets, and payment reminders |
| **Gunicorn** | Production WSGI server |

### Frontend

| Technology | How it is used |
|---|---|
| **HTML5 + Jinja2** | Reusable server-rendered templates, macros, forms, cards, tables, and conditional UI states |
| **CSS3** | Responsive dark interface, mobile layouts, cards, progress indicators, alerts, and dashboard styling |
| **Vanilla JavaScript** | Dynamic payer totals, split previews, receipt checklist interaction, responsive charts, and shopping/group interactions |
| **SVG / CSS charts** | Donut charts, contribution visualizations, budget progress, and monthly spending trends without a large frontend framework |

### Data, OCR, quality, and delivery

| Technology | How it is used |
|---|---|
| **SQLite** | Zero-configuration local development database stored outside Git in `instance/we_owe.db` |
| **PostgreSQL + psycopg2** | Production-ready database option selected through `DATABASE_URL` |
| **Pillow** | Receipt image loading, grayscale conversion, contrast enhancement, and resizing |
| **Tesseract + pytesseract** | OCR engine and Python integration for extracting supermarket receipt text |
| **pytest** | Automated coverage for authentication, groups, expenses, splits, balances, budgets, OCR, shopping, reminders, reports, settlements, and error handling |
| **Git, GitHub, and Trello** | Version control, collaboration, pull-request workflow, product backlog, sprint planning, and checklist tracking |

## How the application works

```text
Browser
  │
  ├── HTML/CSS/JavaScript interface
  │
  ▼
Flask blueprints
  ├── Authentication and settings
  ├── Groups, expenses, shopping, and settlements
  ├── Budgets, reminders, and reports
  │
  ▼
Service layer
  ├── Balance and settlement calculations
  ├── Receipt OCR and validation
  ├── Email delivery and reminder worker
  ├── Reporting, insights, and next-payer logic
  │
  ▼
SQLAlchemy models
  └── SQLite locally / PostgreSQL in production
```

The application uses a Flask **application factory** and separates major domains into blueprints. Calculations are centralized in service modules, while templates focus on presentation. Reports read saved transaction rows rather than generating artificial historical data.

## Run the project locally

### Prerequisites

- Python 3.10 or newer
- Git
- `pip`
- Tesseract OCR only if receipt scanning is required

### 1. Clone the repository

```bash
git clone https://github.com/GnanasreeShivaji/we_owe_budgethub.git
cd we_owe_budgethub
```

### 2. Create and activate a virtual environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create local environment configuration

macOS or Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace the development secret with a long random value. Never commit the real `.env` file.

Generate a secret with Python:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Minimal local configuration:

```dotenv
SECRET_KEY=paste-your-generated-secret-here
MAIL_SUPPRESS_SEND=1
SESSION_COOKIE_SECURE=0
```

The default SQLite database is created automatically on the first launch.

### 5. Start the application

```bash
python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

## Optional setup

### Receipt OCR

The Python package `pytesseract` is included in `requirements.txt`, but the operating-system Tesseract engine must also be installed.

macOS with Homebrew:

```bash
brew install tesseract tesseract-lang
```

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu
```

Verify the installation:

```bash
tesseract --version
```

Receipt scanning tries German and English recognition and automatically locates common Homebrew and system Tesseract paths.

### Real email delivery

With `MAIL_SUPPRESS_SEND=1`, email is not sent externally. Instead, messages are written to `instance/outbox/`, which is useful for local testing.

To send through an SMTP provider, configure the following in your private `.env`:

```dotenv
MAIL_SUPPRESS_SEND=0
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-account@example.com
SMTP_PASSWORD=your-app-password
MAIL_FROM=your-account@example.com
```

Use the SMTP values supplied by your email provider. For Gmail, use an **App Password** when two-step verification is enabled; do not place a normal account password in source code. The port must contain digits only—for example `587`, not `587ß` or `587:`.

Run scheduled reminder delivery manually:

```bash
flask --app run dispatch-reminders
```

Or keep the reminder worker running in a second terminal:

```bash
python -m app.reminders.worker
```

### PostgreSQL

Local development requires no database installation. To use PostgreSQL, set:

```dotenv
DATABASE_URL=postgresql://username:password@localhost:5432/we_owe
```

The application also normalizes the older `postgres://` URL prefix automatically.

## How to use WE_OWE

1. **Create an account.** Register, then open the confirmation link sent by email or written to `instance/outbox/` during local development.
2. **Choose preferences.** Open Settings to select a timezone, currency, and reminder preferences. A new currency applies to newly created records; it does not rewrite historical transaction values.
3. **Create a group.** Add a household, trip, or friend group and invite members by email.
4. **Add an expense.** Enter a title, amount, category, date, notes, payer or payers, and participants. Select equal, exact, percentage, or shares splitting.
5. **Use a receipt when helpful.** Upload a receipt, scan it into a checklist, correct any OCR result, and assign products to the people who consumed them.
6. **Check balances.** The group page calculates who owes whom from saved payments and splits.
7. **Settle a debt.** Record the transfer; the recipient can confirm or reject it, creating an auditable settlement history.
8. **Plan a monthly budget.** Add income, optional savings, category limits, recurring bills, and personal spending. Confirm recurring bills only after they are paid.
9. **Coordinate shopping.** Add group shopping items, assign buyers, mark purchases complete, and turn purchased items into an expense when required.
10. **Review reports.** Select a month and scope to view real saved spending, charts, budget usage, trends, recommendations, and downloadable CSV data.
11. **Send reminders.** Create immediate or scheduled reminders for an outstanding balance and review delivery status.

## Testing and developer tools

Run the complete automated suite:

```bash
PYTHONPATH=. pytest -q
```

The current suite contains **112 collected tests** across the project's core workflows.

Inspect the local database without printing password hashes:

```bash
python tools/inspect_database.py
python tools/inspect_database.py groups
```

Create a timestamped SQLite backup:

```bash
python tools/backup_database.py
```

Generate sprint burndown reports:

```bash
python tools/generate_burndown.py
```

## Project structure

```text
we_owe_budgethub/
├── app/
│   ├── auth/                    registration, login, confirmation, reset
│   ├── budgets/                 monthly budgets and recurring bills
│   ├── expenses/                expense CRUD, payers, splits, receipts
│   ├── groups/                  group and membership management
│   ├── reminders/               payment reminders and worker process
│   ├── reports/                 reports, charts, insights, CSV export
│   ├── settlement_records/      settlement lifecycle and history
│   ├── settings/                preferences, data export, deletion
│   ├── shopping/                collaborative shopping lists
│   ├── services/                calculations, email, OCR, preferences
│   ├── static/                  CSS and browser-side JavaScript
│   ├── templates/               Jinja2 user-interface templates
│   ├── config.py                development/test/production configuration
│   ├── models.py                SQLAlchemy data models
│   └── __init__.py              application factory and extensions
├── docs/                        schema and Trello-ready user stories
├── reports/burndown/            sprint burndown artifacts
├── tests/                       pytest test suite
├── tools/                       database and reporting utilities
├── .env.example                 safe environment-variable template
├── Procfile                     web and reminder-worker processes
├── requirements.txt             Python dependencies
├── run.py                       local development entry point
└── wsgi.py                      production WSGI entry point
```

## Database and data safety

The main models are `User`, `Group`, `Membership`, `Invitation`, `Expense`, `ExpensePayment`, `ExpenseSplit`, `ReceiptItem`, `MonthlyBudget`, `PersonalExpense`, `RecurringBill`, `ShoppingItem`, `PaymentReminder`, and `SettlementTransaction`.

For local development, the live database is:

```text
instance/we_owe.db
```

The database is deliberately **not stored in GitHub**. The following local or sensitive paths are ignored:

- `.env`
- `.venv/`
- `instance/` (database, uploaded receipts, mail outbox, and backups)
- Python and pytest cache files

This keeps credentials and users' financial data out of version control. Each developer or deployment receives a separate database, which the application creates automatically.

The readable database design is available in [`docs/database_schema.sql`](docs/database_schema.sql).

## Security

- Passwords are stored as salted hashes using Werkzeug, never as plaintext.
- Forms use CSRF protection.
- Login attempts are rate-limited in the authentication flow.
- Email confirmation and reset links use signed, expiring tokens.
- Group authorization checks prevent access by non-members.
- Admin-only actions are protected separately from normal member actions.
- Session cookies are `HttpOnly` and `SameSite=Lax`; secure cookies are enabled in production.
- Production responses include security headers for content type, framing, referrer policy, permissions, and HTTPS.
- Uploaded files are size-limited and stored outside the public source tree.
- Secrets, SMTP credentials, databases, receipts, and local email files are excluded from Git.

## Production deployment

The repository includes a `Procfile` with two processes:

```text
web: gunicorn --workers 2 --bind 0.0.0.0:$PORT wsgi:app
worker: python -m app.reminders.worker
```

A hosting platform should provide these environment variables:

- `SECRET_KEY`
- `DATABASE_URL`
- `SESSION_COOKIE_SECURE=1`
- `MAIL_SUPPRESS_SEND=0`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `MAIL_FROM`
- optionally `REMINDER_WORKER_INTERVAL`

Use PostgreSQL for a persistent production database and configure persistent storage or object storage for uploaded receipt files. Never deploy the development `.env` or SQLite database from a laptop.

## Project documentation

- [Database schema](docs/database_schema.sql)
- [Trello-ready user stories](docs/trello_user_stories.md)
- [Formatted user-stories document](docs/WE_OWE_New_Trello_User_Stories.docx)
- [Sprint burndown reports](reports/burndown/)

---

Developed by **Gnanasree Shivaji, Kaniksha, Ananya, and Kavin** as a college software-engineering project demonstrating agile delivery, full-stack development, database design, automated testing, and real-world personal-finance workflows.
