# WE_OWE — Student Budget Hub

Implementation includes **US-01 (User Registration & Login)**,
**US-02 (Group Creation & Management)**, **US-03 (Expense CRUD + receipts)**,
**US-04 (equal, exact, percentage and shares expense splitting)**, and
**US-08 (collaborative shared shopping lists)**, and **US-09 (scheduled,
tracked payment reminders)**, and **US-10 (spending reports, charts, verified
totals, CSV/PDF export)**, plus **US-11 (data-backed spending insights and
recommended actions)**, **US-12 (fair next-payer recommendations)**, and
**US-15 (calculation auditing and safe transfer error handling)**. US-05 automatically derives each group member's
balance from payments and saved splits.

Stack (per the planning report): **Python / Flask** backend, **SQL** via
SQLAlchemy (SQLite in dev, PostgreSQL-ready), **HTML + CSS + JavaScript**
frontend rendered with Jinja2.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then set SECRET_KEY to a random string
python run.py                      # http://127.0.0.1:5000
```

To deliver payment reminders whose scheduled time has arrived, run this from
cron or a deployment scheduler (the reminder center also has a manual button):

```bash
flask --app run dispatch-reminders
```

For continuous automatic delivery, run a separate worker process:

```bash
python -m app.reminders.worker
```

Production starts the two processes declared in `Procfile`: the Gunicorn web
process and the reminder worker. Configure `SECRET_KEY`, `DATABASE_URL`, SMTP,
and HTTPS in the deployment platform; never commit `.env`.

Create a safe SQLite backup with:

```bash
python tools/backup_database.py
```

The Trello-ready Sprint 5 stories are in `docs/trello_user_stories.md`.

The database (`instance/we_owe.db`) is created automatically on first run.
With no SMTP configured, all emails (confirmation, password reset, invites)
are written to `instance/outbox/` as `.txt` files — open them to click the
confirmation/reset links locally.

## Run the tests

```bash
PYTHONPATH=. pytest -q               # 18 tests
```

## Inspect the database

Show the table structure, relationships, and stored rows without displaying
password hashes:

```bash
python tools/inspect_database.py
python tools/inspect_database.py groups   # inspect one table only
```

The readable SQL design is in `docs/database_schema.sql`. The live SQLite
database is stored at `instance/we_owe.db`.

## Project layout

```
app/
  __init__.py        app factory + extensions (SQLAlchemy, Login, CSRF)
  config.py          config; DATABASE_URL switches SQLite -> Postgres
  models.py          User, Group, Membership, Invitation
  auth/              US-01: forms.py (validation) + routes.py
  groups/            US-02: forms.py + routes.py
  services/email.py  email sending (outbox fallback) + signed tokens
  templates/         Jinja2 pages
  static/            style.css + groups.js
tests/               pytest suite (test_auth.py, test_groups.py)
run.py               dev entrypoint
```

## How the code maps to the Trello checklists

**US-01 — User Registration & Login**

| Checklist item | Where |
|---|---|
| Create registration form | `auth/forms.py` `RegisterForm`, `templates/auth/register.html` |
| Validate required fields | WTForms `DataRequired`/`Email`/`EqualTo` |
| Set up password rules | `auth/forms.py` `strong_password` (8+, upper, lower, digit, special) |
| Send confirmation email | `auth/routes.py` `_send_confirmation` + `/auth/confirm/<token>` |
| Create login form | `LoginForm`, `templates/auth/login.html` |
| Authenticate user credentials | `auth/routes.py` `login` + `User.check_password` (hashed) |
| Handle invalid login attempts | single generic error, no account enumeration |
| Verify password reset flow | `/auth/forgot` + `/auth/reset/<token>` |

**US-02 — Group Creation & Management**

| Checklist item | Where |
|---|---|
| Create group | `groups/routes.py` `create_group` (creator becomes admin) |
| Edit group details | `edit_group` |
| Add group members | `invite_member` (registered → instant; else pending invite) |
| Remove group members | `remove_member` (owner protected) |
| Assign group roles | `change_role` (admin ↔ member) |
| View group members | `view_group`, `templates/groups/group_detail.html` |
| Delete group | `delete_group` (cascades memberships + invitations) |

## Acceptance criteria coverage

- **US-01:** email-format + password-strength validation; duplicate emails
  rejected; successful login redirects to the dashboard. Passwords are stored
  as salted hashes (`werkzeug.security`), never plaintext.
- **US-02:** group names unique per owner; members invited by email; group
  logs are isolated — every group route is guarded so a user can only reach a
  group they hold a `Membership` for (see `test_group_isolation_*`).

## Security notes (relevant to the Auth module)

- Passwords are hashed with `werkzeug.security` (scrypt). Login distinguishes
  an unregistered email from an incorrect password to guide new users to sign up.
- CSRF protection on every form (Flask-WTF).
- Session cookies are `HttpOnly` + `SameSite=Lax`; set `SESSION_COOKIE_SECURE=1`
  behind HTTPS in production.
- Email confirmation and password-reset tokens are time-limited signed tokens
  (`itsdangerous`), not guessable IDs.

## Notes for Sprint 2

The `Expense` table will hang off `Group` exactly like `Membership` does, so
the isolation guards already in `groups/routes.py` extend to expenses with no
rework. Swap SQLite for PostgreSQL by setting `DATABASE_URL` — no code change.
