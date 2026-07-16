"""US-03: create, edit and delete expenses with receipt uploads."""

from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from .. import db
from ..models import Expense, ExpenseSplit, Group
from .forms import ExpenseForm

expenses_bp = Blueprint("expenses", __name__, url_prefix="/groups/<int:group_id>/expenses")


def _group_for_member(group_id: int) -> Group:
    group = db.session.get(Group, group_id) or abort(404)
    if not group.has_member(current_user):
        abort(403)
    return group


def _expense_in_group(group: Group, expense_id: int) -> Expense:
    return Expense.query.filter_by(id=expense_id, group_id=group.id).first_or_404()


def _save_receipt(upload) -> tuple[str, str]:
    original = secure_filename(upload.filename or "receipt")
    suffix = Path(original).suffix.lower()
    stored = f"{uuid4().hex}{suffix}"
    folder = Path(current_app.config["RECEIPT_UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    upload.save(folder / stored)
    return stored, original


def _delete_receipt(filename: str | None) -> None:
    if filename:
        path = Path(current_app.config["RECEIPT_UPLOAD_FOLDER"]) / filename
        path.unlink(missing_ok=True)


def _selected_participants(group: Group):
    """Return selected group members; default to the payer for old/API clients."""
    selected = [m.user for m in group.memberships if f"participant_{m.user_id}" in request.form]
    has_participant_fields = any(key.startswith("participant_") for key in request.form)
    return selected if has_participant_fields else [current_user]


def _calculate_splits(group: Group, method: str, total: Decimal):
    participants = _selected_participants(group)
    if not participants:
        raise ValueError("Select at least one participant.")

    total = total.quantize(Decimal("0.01"))
    raw = {}
    if method != "equal":
        for user in participants:
            value = request.form.get(f"split_value_{user.id}", "").strip()
            try:
                raw[user.id] = Decimal(value)
            except (InvalidOperation, ValueError):
                raise ValueError(f"Enter a valid split value for {user.name}.")
            if raw[user.id] <= 0:
                raise ValueError("Split values must be greater than zero.")

    if method == "exact":
        if sum(raw.values()) != total:
            raise ValueError(f"Exact amounts must add up to {total:.2f}.")
        amounts = raw
    elif method == "percentage":
        if sum(raw.values()) != Decimal("100"):
            raise ValueError("Percentages must add up to 100%.")
        amounts = _proportional_amounts(participants, raw, total, Decimal("100"))
    elif method == "shares":
        amounts = _proportional_amounts(participants, raw, total, sum(raw.values()))
    else:
        weights = {user.id: Decimal("1") for user in participants}
        amounts = _proportional_amounts(participants, weights, total, Decimal(len(participants)))
        raw = weights
    return [(user, amounts[user.id], raw.get(user.id)) for user in participants]


def _proportional_amounts(participants, weights, total, divisor):
    amounts = {}
    allocated = Decimal("0")
    for user in participants[:-1]:
        amount = (total * weights[user.id] / divisor).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        amounts[user.id] = amount
        allocated += amount
    amounts[participants[-1].id] = total - allocated
    return amounts


def _replace_splits(expense: Expense, calculated) -> None:
    existing = {split.user_id: split for split in expense.splits}
    desired_ids = {user.id for user, _, _ in calculated}
    for user_id, split in existing.items():
        if user_id not in desired_ids:
            db.session.delete(split)
    for user, amount, input_value in calculated:
        split = existing.get(user.id)
        if split is None:
            split = ExpenseSplit(user_id=user.id)
            expense.splits.append(split)
        split.amount = amount
        split.input_value = input_value


@expenses_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_expense(group_id):
    group = _group_for_member(group_id)
    form = ExpenseForm()
    if request.method == "POST" and not form.split_method.data:
        form.split_method.data = "equal"
    if form.validate_on_submit():
        try:
            calculated = _calculate_splits(group, form.split_method.data, form.amount.data)
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "expenses/form.html", form=form, group=group, expense=None,
                memberships=group.memberships, selected_ids=_posted_selected_ids(group), split_values=request.form,
            )
        expense = Expense(
            group_id=group.id,
            paid_by_id=current_user.id,
            title=form.title.data.strip(),
            amount=form.amount.data,
            category=form.category.data,
            expense_date=form.expense_date.data,
            notes=(form.notes.data or "").strip(),
            split_method=form.split_method.data,
        )
        if form.receipt.data:
            expense.receipt_filename, expense.receipt_original_name = _save_receipt(form.receipt.data)
        _replace_splits(expense, calculated)
        db.session.add(expense)
        db.session.commit()
        flash("Expense saved successfully.", "success")
        return redirect(url_for("groups.view_group", group_id=group.id))
    return render_template(
        "expenses/form.html", form=form, group=group, expense=None,
        memberships=group.memberships,
        selected_ids={m.user_id for m in group.memberships}, split_values={},
    )


@expenses_bp.route("/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(group_id, expense_id):
    group = _group_for_member(group_id)
    expense = _expense_in_group(group, expense_id)
    form = ExpenseForm(obj=expense)
    if request.method == "POST" and not form.split_method.data:
        form.split_method.data = expense.split_method or "equal"
    if form.validate_on_submit():
        try:
            calculated = _calculate_splits(group, form.split_method.data, form.amount.data)
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "expenses/form.html", form=form, group=group, expense=expense,
                memberships=group.memberships, selected_ids=_posted_selected_ids(group), split_values=request.form,
            )
        expense.title = form.title.data.strip()
        expense.amount = form.amount.data
        expense.category = form.category.data
        expense.expense_date = form.expense_date.data
        expense.notes = (form.notes.data or "").strip()
        expense.split_method = form.split_method.data
        _replace_splits(expense, calculated)
        if form.receipt.data:
            _delete_receipt(expense.receipt_filename)
            expense.receipt_filename, expense.receipt_original_name = _save_receipt(form.receipt.data)
        db.session.commit()
        flash("Expense updated successfully.", "success")
        return redirect(url_for("groups.view_group", group_id=group.id))
    split_values = {f"split_value_{split.user_id}": split.input_value for split in expense.splits}
    return render_template(
        "expenses/form.html", form=form, group=group, expense=expense,
        memberships=group.memberships, selected_ids={s.user_id for s in expense.splits},
        split_values=split_values,
    )


def _posted_selected_ids(group):
    return {m.user_id for m in group.memberships if f"participant_{m.user_id}" in request.form}


@expenses_bp.route("/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(group_id, expense_id):
    group = _group_for_member(group_id)
    expense = _expense_in_group(group, expense_id)
    if expense.paid_by_id != current_user.id and not group.is_admin(current_user):
        abort(403)
    receipt = expense.receipt_filename
    db.session.delete(expense)
    db.session.commit()
    _delete_receipt(receipt)
    flash("Expense deleted.", "info")
    return redirect(url_for("groups.view_group", group_id=group.id))


@expenses_bp.route("/<int:expense_id>/receipt")
@login_required
def receipt(group_id, expense_id):
    group = _group_for_member(group_id)
    expense = _expense_in_group(group, expense_id)
    if not expense.receipt_filename:
        abort(404)
    return send_from_directory(
        current_app.config["RECEIPT_UPLOAD_FOLDER"],
        expense.receipt_filename,
        as_attachment=True,
        download_name=expense.receipt_original_name,
    )
