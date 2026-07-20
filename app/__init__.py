"""Application factory.

WE_OWE Student Budget Hub -- Sprint 1 (US-01 Auth, US-02 Groups).
"""
import click
from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


def create_app(config_object="app.config.Config"):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy is aware of them before create_all
    from . import models  # noqa: F401

    from .auth.routes import auth_bp
    from .groups.routes import groups_bp
    from .expenses.routes import expenses_bp
    from .budgets.routes import budgets_bp
    from .shopping.routes import shopping_bp
    from .reminders.routes import reminders_bp
    from .settlement_records.routes import settlement_records_bp
    from .reports.routes import reports_bp
    from .settings.routes import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(shopping_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(settlement_records_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)

    @app.context_processor
    def display_preferences():
        from .services.preferences import CURRENCY_SYMBOLS, symbol_for
        currency = current_user.currency if current_user.is_authenticated else "EUR"
        return {"currency_code": currency, "currency_symbol": CURRENCY_SYMBOLS.get(currency, currency + " "),
                "currency_symbol_for": symbol_for}

    @app.template_filter("localtime")
    def localtime(value):
        from datetime import timezone
        from .services.preferences import user_zone
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        user = current_user if current_user.is_authenticated else None
        return value.astimezone(user_zone(user)).strftime("%d %b %Y · %H:%M")

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not app.debug:
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("groups.dashboard"))
        return redirect(url_for("auth.login"))

    @app.cli.command("dispatch-reminders")
    def dispatch_reminders_command():
        """Send all scheduled payment reminders that are currently due."""
        from .reminders.routes import dispatch_due_reminders
        count = dispatch_due_reminders()
        click.echo(f"Processed {count} due reminder{'s' if count != 1 else ''}.")

    with app.app_context():
        db.create_all()
        # Lightweight upgrade for databases created before US-04. create_all()
        # creates new tables but does not add columns to an existing table.
        if db.engine.dialect.name == "sqlite" and "expenses" in inspect(db.engine).get_table_names():
            columns = {column["name"] for column in inspect(db.engine).get_columns("expenses")}
            if "split_method" not in columns:
                db.session.execute(
                    text("ALTER TABLE expenses ADD COLUMN split_method VARCHAR(20) NOT NULL DEFAULT 'equal'")
                )
                db.session.commit()
            # Preserve US-03 records by giving each old expense a payer-only
            # equal split until the user edits it and selects participants.
            db.session.execute(text("""
                INSERT INTO expense_splits (expense_id, user_id, amount, input_value)
                SELECT e.id, e.paid_by_id, e.amount, 1
                FROM expenses AS e
                WHERE NOT EXISTS (
                    SELECT 1 FROM expense_splits AS s WHERE s.expense_id = e.id
                )
            """))
            # Backfill expenses created before multiple-payer support. Their
            # original paid_by member paid the complete expense.
            db.session.execute(text("""
                INSERT INTO expense_payments (expense_id, user_id, amount)
                SELECT e.id, e.paid_by_id, e.amount
                FROM expenses AS e
                WHERE NOT EXISTS (
                    SELECT 1 FROM expense_payments AS p WHERE p.expense_id = e.id
                )
            """))
            db.session.commit()
            # Lightweight additive migrations for existing local databases.
            table_columns = {
                table: {column["name"] for column in inspect(db.engine).get_columns(table)}
                for table in ("users", "receipt_items", "shopping_items", "groups", "expenses",
                              "monthly_budgets", "personal_expenses", "recurring_bills",
                              "recurring_bill_occurrences", "payment_reminders", "settlement_transactions")
                if table in inspect(db.engine).get_table_names()
            }
            additions = {
                "users": {
                    "timezone": "VARCHAR(60) NOT NULL DEFAULT 'Europe/Berlin'",
                    "currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'",
                    "notify_immediate": "BOOLEAN NOT NULL DEFAULT 1",
                    "notify_scheduled": "BOOLEAN NOT NULL DEFAULT 1",
                    "account_deleted": "BOOLEAN NOT NULL DEFAULT 0",
                },
                "receipt_items": {"quantity": "INTEGER NOT NULL DEFAULT 1", "unit_price": "NUMERIC(12,2)"},
                "shopping_items": {"price": "NUMERIC(12,2)", "converted_expense_id": "INTEGER"},
                "groups": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "expenses": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "monthly_budgets": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "personal_expenses": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "recurring_bills": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "recurring_bill_occurrences": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "payment_reminders": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
                "settlement_transactions": {"currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'"},
            }
            for table, columns_to_add in additions.items():
                for column, definition in columns_to_add.items():
                    if column not in table_columns.get(table, set()):
                        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            db.session.commit()

    return app
