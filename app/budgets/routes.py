"""Personal monthly budget planner (US-07)."""

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import db
from ..models import (Expense, ExpenseSplit, MonthlyBudget, PersonalExpense,
                      RecurringBill, RecurringBillOccurrence)
from ..services.preferences import symbol_for
from .forms import MonthlyBudgetForm, PersonalExpenseForm, RecurringBillForm


budgets_bp = Blueprint("budgets", __name__, url_prefix="/budget")
# The stored column names are retained for existing databases, while the
# student-facing labels use a clearer real-life budget vocabulary.
BUDGET_CATEGORIES = (
    ("Rent", "transport_budget"),
    ("Bills", "utilities_budget"),
    ("Groceries", "groceries_budget"),
    ("Eating out", "food_budget"),
    ("Money sent home", "entertainment_budget"),
    ("Other expenses", "other_budget"),
)
EXPENSE_CATEGORY_MAP = {
    "Rent": "Rent",
    "Bills": "Bills",
    "Utilities": "Bills",       # existing records
    "Groceries": "Groceries",
    "Eating out": "Eating out",
    "Food": "Eating out",       # existing records
    "Money sent home": "Money sent home",
    "Other expenses": "Other expenses",
    "Other": "Other expenses",  # existing records
    "Transport": "Other expenses",
    "Entertainment": "Other expenses",
}


def _lines_total(value, label):
    total = Decimal("0.00")
    for line_number, line in enumerate((value or "").splitlines(), 1):
        if not line.strip():
            continue
        try:
            name, amount = line.rsplit(":", 1)
            if not name.strip():
                raise ValueError
            number = Decimal(amount.strip()).quantize(Decimal("0.01"))
            if number < 0:
                raise ValueError
            total += number
        except (ValueError, InvalidOperation):
            raise ValueError(f"{label} line {line_number} must look like Name: 100.00")
    return total


def _budget_summary(budget):
    income = _lines_total(budget.income_sources, "Income")
    savings = Decimal(budget.savings_target or 0)
    planned = sum(Decimal(getattr(budget, attribute) or 0) for _, attribute in BUDGET_CATEGORIES)
    return income, savings, planned, income - savings - planned


def _actual_by_category(month, currency):
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    rows = (
        db.session.query(Expense.category, db.func.sum(ExpenseSplit.amount))
        .join(Expense, Expense.id == ExpenseSplit.expense_id)
        .filter(ExpenseSplit.user_id == current_user.id, Expense.expense_date.between(start, end),
                Expense.currency == currency)
        .group_by(Expense.category).all()
    )
    group_actual = {label: Decimal("0.00") for label, _ in BUDGET_CATEGORIES}
    for category, amount in rows:
        key = EXPENSE_CATEGORY_MAP.get(category, "Other expenses")
        group_actual[key] += Decimal(amount or 0)
    personal_rows = (
        db.session.query(PersonalExpense.category, db.func.sum(PersonalExpense.amount))
        .filter(PersonalExpense.user_id == current_user.id,
                PersonalExpense.expense_date.between(start, end),
                PersonalExpense.currency == currency)
        .group_by(PersonalExpense.category).all()
    )
    personal_actual = {label: Decimal("0.00") for label, _ in BUDGET_CATEGORIES}
    for category, amount in personal_rows:
        key = EXPENSE_CATEGORY_MAP.get(category, "Other expenses")
        personal_actual[key] += Decimal(amount or 0)
    occurrences = RecurringBillOccurrence.query.filter_by(
        user_id=current_user.id, month=month, currency=currency
    ).all()
    recurring_total = sum((Decimal(item.amount) for item in occurrences), Decimal("0.00"))
    personal_actual["Bills"] += recurring_total
    return group_actual, personal_actual, start, end


def _group_activity(start, end, currency):
    """Return this user's split shares with the original payment description."""
    return (
        db.session.query(Expense, ExpenseSplit.amount)
        .join(ExpenseSplit, ExpenseSplit.expense_id == Expense.id)
        .filter(
            ExpenseSplit.user_id == current_user.id,
            Expense.expense_date.between(start, end),
            Expense.currency == currency,
        )
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
        .all()
    )


def _chart_breakdown(categories, total):
    """Return chart percentages whose displayed whole numbers total exactly 100."""
    if not total:
        return []
    rows = []
    allocated = 0
    for item in categories:
        exact = Decimal(item["actual"]) / Decimal(total) * 100
        whole = int(exact)
        rows.append({**item, "chart_percentage": float(exact),
                     "display_percentage": whole, "remainder": exact - whole})
        allocated += whole
    for row in sorted(rows, key=lambda value: value["remainder"], reverse=True)[:100 - allocated]:
        row["display_percentage"] += 1
    return rows


@budgets_bp.route("/", methods=["GET", "POST"])
@login_required
def monthly_budget():
    selected_month = request.values.get("month") or date.today().strftime("%Y-%m")
    budget = MonthlyBudget.query.filter_by(user_id=current_user.id, month=selected_month).first()
    form = MonthlyBudgetForm(obj=budget)
    if request.method == "GET":
        form.month.data = selected_month
    if form.validate_on_submit():
        try:
            _lines_total(form.income_sources.data, "Income")
        except ValueError as error:
            flash(str(error), "error")
        else:
            budget = MonthlyBudget.query.filter_by(user_id=current_user.id, month=form.month.data).first()
            if budget is None:
                budget = MonthlyBudget(user_id=current_user.id, month=form.month.data,
                                       currency=current_user.currency)
                db.session.add(budget)
            form.populate_obj(budget)
            db.session.commit()
            flash("Monthly budget saved.", "success")
            return redirect(url_for("budgets.monthly_budget", month=budget.month))

    summary = _budget_summary(budget) if budget else None
    recurring_bills = RecurringBill.query.filter_by(user_id=current_user.id).order_by(
        RecurringBill.bill_type, RecurringBill.description
    ).all()
    recurring_occurrences = {
        item.bill_id: item for item in RecurringBillOccurrence.query.filter_by(
            user_id=current_user.id, month=selected_month,
            currency=budget.currency if budget else current_user.currency,
        ).all()
    }
    budget_currency = budget.currency if budget else current_user.currency
    group_actual, personal_actual, month_start, month_end = _actual_by_category(
        selected_month, budget_currency
    )
    categories = []
    for label, attribute in BUDGET_CATEGORIES:
        planned = Decimal(getattr(budget, attribute) or 0) if budget else Decimal("0")
        spent = group_actual[label] + personal_actual[label]
        percentage = float(spent / planned * 100) if planned else (100.0 if spent else 0.0)
        level = "danger" if percentage >= 100 else "warning" if percentage >= 70 else "notice" if percentage >= 50 else "safe"
        categories.append({"name": label, "key": attribute, "planned": planned, "group": group_actual[label],
                           "personal": personal_actual[label], "actual": spent,
                           "remaining": planned - spent, "percentage": percentage,
                           "display_percentage": min(percentage, 100),
                           "bar_percentage": min(percentage, 100), "level": level})
    spending_entries = PersonalExpense.query.filter(
        PersonalExpense.user_id == current_user.id,
        PersonalExpense.expense_date.between(month_start, month_end),
        PersonalExpense.currency == budget_currency,
    ).order_by(PersonalExpense.expense_date.desc(), PersonalExpense.id.desc()).all()
    spending_form = PersonalExpenseForm()
    recurring_form = RecurringBillForm()
    spending_form.expense_date.data = date.today() if selected_month == date.today().strftime("%Y-%m") else month_start
    group_activity = _group_activity(month_start, month_end, budget_currency)
    total_spent = sum((item["actual"] for item in categories), Decimal("0.00"))
    chart_categories = _chart_breakdown(
        [item for item in categories if item["actual"] > 0], total_spent
    )
    income_total = summary[0] if summary else Decimal("0.00")
    savings_total = summary[1] if summary else Decimal("0.00")
    # Savings is an optional goal, not money already spent. Keep it in the
    # available balance and expose the post-goal figure separately.
    money_left = income_total - total_spent
    money_after_savings = money_left - savings_total
    recurring_total = sum((Decimal(item.amount) for item in recurring_occurrences.values()), Decimal("0.00"))
    return render_template("budgets/monthly.html", form=form, budget=budget, summary=summary,
                           categories=categories, selected_month=selected_month,
                           spending_form=spending_form, spending_entries=spending_entries,
                           recurring_form=recurring_form, recurring_bills=recurring_bills,
                           recurring_occurrences=recurring_occurrences,
                           group_activity=group_activity, total_spent=total_spent,
                           chart_categories=chart_categories, income_total=income_total,
                           savings_total=savings_total, money_left=money_left,
                           money_after_savings=money_after_savings,
                           recurring_total=recurring_total,
                           currency_symbol=symbol_for(budget_currency),
                           budget_currency=budget_currency)


@budgets_bp.route("/recurring/<int:bill_id>/confirm", methods=["POST"])
@login_required
def confirm_recurring_bill(bill_id):
    bill = RecurringBill.query.filter_by(id=bill_id, user_id=current_user.id).first_or_404()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    year, month_number = map(int, month.split("-"))
    occurrence = RecurringBillOccurrence.query.filter_by(bill_id=bill.id, month=month).first()
    if occurrence is None:
        paid_on_raw = request.form.get("paid_on")
        try:
            paid_on = date.fromisoformat(paid_on_raw) if paid_on_raw else date(year, month_number, 1)
        except ValueError:
            flash("Choose a valid payment date.", "error")
            return redirect(url_for("budgets.monthly_budget", month=month))
        occurrence = RecurringBillOccurrence(
            user_id=current_user.id, bill_id=bill.id, month=month,
            amount=bill.amount, paid_on=paid_on,
            currency=bill.currency,
        )
        db.session.add(occurrence)
        db.session.commit()
    flash("Bill confirmed as paid for this month.", "success")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/recurring/<int:bill_id>/unconfirm", methods=["POST"])
@login_required
def unconfirm_recurring_bill(bill_id):
    bill = RecurringBill.query.filter_by(id=bill_id, user_id=current_user.id).first_or_404()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    occurrence = RecurringBillOccurrence.query.filter_by(bill_id=bill.id, month=month).first()
    if occurrence:
        db.session.delete(occurrence)
        db.session.commit()
    flash("Bill marked unpaid for this month.", "info")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/recurring/add", methods=["POST"])
@login_required
def add_recurring_bill():
    form = RecurringBillForm()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    if form.validate_on_submit():
        db.session.add(RecurringBill(
            user_id=current_user.id,
            bill_type=form.bill_type.data,
            description=form.description.data.strip(),
            amount=form.amount.data,
            currency=current_user.currency,
        ))
        db.session.commit()
        flash("Recurring bill template added. Mark it paid in each applicable month.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/recurring/<int:bill_id>/delete", methods=["POST"])
@login_required
def delete_recurring_bill(bill_id):
    bill = RecurringBill.query.filter_by(id=bill_id, user_id=current_user.id).first_or_404()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    db.session.delete(bill)
    db.session.commit()
    flash("Recurring bill removed.", "info")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/recurring/<int:bill_id>/edit", methods=["POST"])
@login_required
def edit_recurring_bill(bill_id):
    bill = RecurringBill.query.filter_by(id=bill_id, user_id=current_user.id).first_or_404()
    form = RecurringBillForm()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    if form.validate_on_submit():
        bill.bill_type = form.bill_type.data
        bill.description = form.description.data.strip()
        bill.amount = form.amount.data
        db.session.commit()
        flash("Recurring bill updated.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/category/<category_key>", methods=["POST"])
@login_required
def update_category_limit(category_key):
    """Update one category limit directly from the spending tracker."""
    allowed = {attribute: label for label, attribute in BUDGET_CATEGORIES}
    if category_key not in allowed:
        return ("Unknown budget category", 404)
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    try:
        amount = Decimal(request.form.get("amount", "")).quantize(Decimal("0.01"))
        if amount < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Enter a valid category limit of zero or more.", "error")
        return redirect(url_for("budgets.monthly_budget", month=month))

    budget = MonthlyBudget.query.filter_by(user_id=current_user.id, month=month).first()
    if budget is None:
        budget = MonthlyBudget(user_id=current_user.id, month=month, income_sources="",
                               currency=current_user.currency)
        db.session.add(budget)
    setattr(budget, category_key, amount)
    db.session.commit()
    flash(f"{allowed[category_key]} limit updated.", "success")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/<month>/delete", methods=["POST"])
@login_required
def delete_monthly_budget(month):
    """Delete one month's plan without removing its recorded spending."""
    budget = MonthlyBudget.query.filter_by(
        user_id=current_user.id, month=month
    ).first_or_404()
    db.session.delete(budget)
    db.session.commit()
    flash(
        "Monthly budget deleted. Your spending and recurring bills were kept.",
        "info",
    )
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/<month>/reset", methods=["POST"])
@login_required
def reset_month(month):
    """Remove a monthly plan and private entries so the user can start again."""
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    budget = MonthlyBudget.query.filter_by(user_id=current_user.id, month=month).first()
    if budget:
        db.session.delete(budget)
    removed = PersonalExpense.query.filter(
        PersonalExpense.user_id == current_user.id,
        PersonalExpense.expense_date.between(start, end),
    ).delete(synchronize_session=False)
    db.session.commit()
    flash(
        f"Month reset. The budget and {removed} personal spending entr{'y' if removed == 1 else 'ies'} were removed. Recurring bills and group splits were kept.",
        "info",
    )
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/spending/add", methods=["POST"])
@login_required
def add_spending():
    form = PersonalExpenseForm()
    month = request.form.get("month") or date.today().strftime("%Y-%m")
    if form.validate_on_submit():
        entry_budget = MonthlyBudget.query.filter_by(
            user_id=current_user.id, month=form.expense_date.data.strftime("%Y-%m")
        ).first()
        entry = PersonalExpense(
            user_id=current_user.id,
            description=form.description.data.strip(),
            amount=form.amount.data,
            category=form.category.data,
            expense_date=form.expense_date.data,
            currency=entry_budget.currency if entry_budget else current_user.currency,
        )
        db.session.add(entry)
        db.session.commit()
        flash("Personal spending recorded.", "success")
        month = entry.expense_date.strftime("%Y-%m")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
    return redirect(url_for("budgets.monthly_budget", month=month))


@budgets_bp.route("/spending/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_spending(entry_id):
    entry = PersonalExpense.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    month = entry.expense_date.strftime("%Y-%m")
    db.session.delete(entry)
    db.session.commit()
    flash("Personal spending deleted.", "info")
    return redirect(url_for("budgets.monthly_budget", month=month))
