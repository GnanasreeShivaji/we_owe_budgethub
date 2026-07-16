"""Application factory.

WE_OWE Student Budget Hub -- Sprint 1 (US-01 Auth, US-02 Groups).
"""
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(expenses_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("groups.dashboard"))
        return redirect(url_for("auth.login"))

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
            db.session.commit()

    return app
