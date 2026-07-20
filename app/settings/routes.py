import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from flask import Blueprint, Response, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user

from .. import db
from ..models import (MonthlyBudget, PersonalExpense, RecurringBill,
                      RecurringBillOccurrence, SettlementTransaction)
from .forms import DeleteAccountForm, PreferencesForm


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/", methods=["GET", "POST"])
@login_required
def preferences():
    form = PreferencesForm(obj=current_user)
    delete_form = DeleteAccountForm()
    if form.validate_on_submit():
        form.populate_obj(current_user)
        db.session.commit()
        flash("Preferences saved. Existing records kept their original currency.", "success")
        return redirect(url_for("settings.preferences"))
    return render_template("settings/preferences.html", form=form, delete_form=delete_form)


def _json_value(value):
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    return value


@settings_bp.route("/export.json")
@login_required
def export_data():
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": {"name": current_user.name, "email": current_user.email,
                    "timezone": current_user.timezone, "currency": current_user.currency},
        "personal_expenses": [{column.name: _json_value(getattr(item, column.name))
                               for column in PersonalExpense.__table__.columns}
                              for item in current_user.personal_expenses],
        "monthly_budgets": [{column.name: _json_value(getattr(item, column.name))
                             for column in MonthlyBudget.__table__.columns}
                            for item in current_user.monthly_budgets],
        "recurring_bills": [{column.name: _json_value(getattr(item, column.name))
                             for column in RecurringBill.__table__.columns}
                            for item in current_user.recurring_bills],
        "groups": [{"name": group.name, "expenses": [
            {"title": expense.title, "amount": str(expense.amount),
             "category": expense.category, "date": str(expense.expense_date)}
            for expense in group.expenses]} for group in current_user.groups],
        "settlements": [{"group": item.group.name, "from": item.from_user.name,
                         "to": item.to_user.name, "amount": str(item.amount),
                         "status": item.status, "created_at": str(item.created_at)}
                        for item in SettlementTransaction.query.filter(
                            (SettlementTransaction.from_user_id == current_user.id) |
                            (SettlementTransaction.to_user_id == current_user.id)).all()],
    }
    return Response(json.dumps(payload, indent=2, ensure_ascii=False),
                    mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=we-owe-account-export.json"})


@settings_bp.route("/delete", methods=["POST"])
@login_required
def delete_account():
    form = DeleteAccountForm()
    if not form.validate_on_submit() or not current_user.check_password(form.password.data):
        flash("Enter your correct password to delete the account.", "error")
        return redirect(url_for("settings.preferences"))
    user = current_user._get_current_object()
    for group in list(user.groups_owned):
        db.session.delete(group)
    PersonalExpense.query.filter_by(user_id=user.id).delete()
    MonthlyBudget.query.filter_by(user_id=user.id).delete()
    RecurringBillOccurrence.query.filter_by(user_id=user.id).delete()
    RecurringBill.query.filter_by(user_id=user.id).delete()
    user.name = "Deleted user"
    user.email = f"deleted-{uuid4().hex}@invalid.local"
    user.password_hash = "!deleted"
    user.is_confirmed = False
    user.account_deleted = True
    db.session.commit()
    logout_user()
    flash("Your account was deleted. Shared financial history was anonymized.", "info")
    return redirect(url_for("auth.login"))
