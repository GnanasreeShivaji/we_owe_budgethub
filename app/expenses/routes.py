"""US-03: create, edit and delete expenses with receipt uploads."""

from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from .. import db
from ..models import (Expense, ExpensePayment, ExpenseSplit, Group, ReceiptItem,
                      ReceiptItemAssignment, ShoppingItem)
from ..services.receipt_ocr import scan_image
from ..services.next_payer import recommend_next_payer
from ..services.preferences import symbol_for
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


def _calculate_payments(group: Group, total: Decimal):
    """Validate selected payers and require their payments to equal the bill."""
    has_payer_fields = any(key.startswith("payer_") for key in request.form)
    if not has_payer_fields:
        # Backward compatibility for older clients: the member submitting the
        # expense is treated as the sole payer.
        return [(current_user, Decimal(total).quantize(Decimal("0.01")))]
    payments = []
    for membership in group.memberships:
        user = membership.user
        if f"payer_{user.id}" not in request.form:
            continue
        value = request.form.get(f"payment_value_{user.id}", "").strip()
        if not value and len([key for key in request.form if key.startswith("payer_")]) == 1:
            value = str(total)
        try:
            amount = Decimal(value).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Enter a valid amount paid by {user.name}.")
        if amount <= 0:
            raise ValueError("Each payer's amount must be greater than zero.")
        payments.append((user, amount))
    if not payments:
        raise ValueError("Select at least one person who paid.")
    total = Decimal(total).quantize(Decimal("0.01"))
    if sum(amount for _, amount in payments) != total:
        raise ValueError(f"Amounts paid must add up to €{total:.2f}.")
    return payments


def _replace_payments(expense: Expense, calculated) -> None:
    existing = {payment.user_id: payment for payment in expense.payments}
    desired_ids = {user.id for user, _ in calculated}
    for user_id, payment in existing.items():
        if user_id not in desired_ids:
            db.session.delete(payment)
    for user, amount in calculated:
        payment = existing.get(user.id)
        if payment is None:
            payment = ExpensePayment(user_id=user.id)
            expense.payments.append(payment)
        payment.amount = amount


def _posted_receipt_items(group):
    """Validate receipt checklist rows and calculate member totals."""
    try:
        count = int(request.form.get("receipt_item_count", "0"))
    except ValueError:
        raise ValueError("The receipt checklist is invalid. Scan the receipt again.")
    if count <= 0:
        return [], None, None
    if count > 100:
        raise ValueError("A receipt can contain at most 100 checklist items.")

    members = {membership.user_id: membership.user for membership in group.memberships}
    items = []
    member_totals = {user_id: Decimal("0.00") for user_id in members}
    total = Decimal("0.00")
    for index in range(count):
        name = request.form.get(f"receipt_item_name_{index}", "").strip()[:180]
        try:
            quantity = int(request.form.get(f"receipt_item_quantity_{index}", "1"))
            unit_raw = request.form.get(f"receipt_item_unit_price_{index}")
            unit_price = (Decimal(unit_raw) if unit_raw else Decimal(
                request.form.get(f"receipt_item_price_{index}", "")
            )).quantize(Decimal("0.01"))
            price = (unit_price * quantity).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Enter a valid price for receipt item {index + 1}.")
        selected_ids = [user_id for user_id in members
                        if f"receipt_item_{index}_member_{user_id}" in request.form]
        if not name or price <= 0 or quantity < 1 or quantity > 100:
            raise ValueError(f"Receipt item {index + 1} needs a name and price.")
        if not selected_ids:
            raise ValueError(f"Choose who had {name}.")
        weights = {user_id: Decimal("1") for user_id in selected_ids}
        users = [members[user_id] for user_id in selected_ids]
        shares = _proportional_amounts(users, weights, price, Decimal(len(users)))
        for user_id, amount in shares.items():
            member_totals[user_id] += amount
        items.append({"name": name, "price": price, "quantity": quantity,
                      "unit_price": unit_price,
                      "assignments": [(members[user_id], shares[user_id]) for user_id in selected_ids]})
        total += price
    calculated = [(members[user_id], amount, amount) for user_id, amount in member_totals.items() if amount > 0]
    return items, total, calculated


def _store_receipt_items(expense, items):
    for item_data in items:
        item = ReceiptItem(name=item_data["name"], price=item_data["price"],
                           quantity=item_data.get("quantity", 1),
                           unit_price=item_data.get("unit_price", item_data["price"]))
        for user, amount in item_data["assignments"]:
            item.assignments.append(ReceiptItemAssignment(user_id=user.id, amount=amount))
        expense.receipt_items.append(item)


@expenses_bp.route("/receipt/scan", methods=["POST"])
@login_required
def scan_receipt(group_id):
    group = _group_for_member(group_id)
    upload = request.files.get("receipt")
    if not upload or not upload.filename:
        return jsonify(error="Choose a receipt image first."), 400
    suffix = Path(secure_filename(upload.filename)).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return jsonify(error="Automatic scanning supports JPG, PNG, GIF, or WebP images."), 400
    try:
        items = scan_image(upload)
    except Exception:
        current_app.logger.exception("Receipt OCR failed")
        return jsonify(error="We could not read this receipt. Try a clearer image or enter the expense manually."), 422
    if not items:
        return jsonify(error="No product lines were found. Try a clearer, tightly cropped receipt image."), 422
    return jsonify(
        items=[{"name": item["name"], "quantity": item.get("quantity", 1),
                "unit_price": f"{item.get('unit_price', item['price']):.2f}",
                "price": f"{item['price']:.2f}"} for item in items],
        total=f"{sum((item['price'] for item in items), Decimal('0.00')):.2f}",
        members=[{"id": membership.user_id, "name": membership.user.name}
                 for membership in group.memberships],
        currency=symbol_for(group.currency),
    )


@expenses_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_expense(group_id):
    group = _group_for_member(group_id)
    can_choose_currency = group.is_admin(current_user) and not (
        group.expenses or group.settlement_transactions or group.payment_reminders
        or any(item.price for item in group.shopping_items)
    )
    next_payer = recommend_next_payer(group, symbol_for(group.currency))
    form = ExpenseForm()
    if request.method == "GET":
        form.currency.data = group.currency
    if request.method == "POST" and not form.split_method.data:
        form.split_method.data = "equal"
    if form.validate_on_submit():
        if can_choose_currency and form.currency.data:
            group.currency = form.currency.data
            next_payer = recommend_next_payer(group, symbol_for(group.currency))
        try:
            receipt_items, receipt_total, receipt_calculated = _posted_receipt_items(group)
            if receipt_items:
                form.amount.data = receipt_total
                calculated = receipt_calculated
            else:
                calculated = _calculate_splits(group, form.split_method.data, form.amount.data)
            payments = _calculate_payments(group, form.amount.data)
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "expenses/form.html", form=form, group=group, expense=None,
                memberships=group.memberships, selected_ids=_posted_selected_ids(group), split_values=request.form,
                payer_ids=_posted_payer_ids(group), payment_values=request.form,
                next_payer=next_payer, currency_symbol=symbol_for(group.currency),
                can_choose_currency=can_choose_currency,
            )
        expense = Expense(
            group_id=group.id,
            paid_by_id=payments[0][0].id,
            title=form.title.data.strip(),
            amount=form.amount.data,
            category=form.category.data,
            expense_date=form.expense_date.data,
            notes=(form.notes.data or "").strip(),
            split_method="receipt" if receipt_items else form.split_method.data,
            currency=group.currency,
        )
        if form.receipt.data:
            expense.receipt_filename, expense.receipt_original_name = _save_receipt(form.receipt.data)
        _replace_splits(expense, calculated)
        _replace_payments(expense, payments)
        _store_receipt_items(expense, receipt_items)
        db.session.add(expense)
        db.session.commit()
        flash("Expense saved successfully.", "success")
        return redirect(url_for("groups.view_group", group_id=group.id))
    return render_template(
        "expenses/form.html", form=form, group=group, expense=None,
        memberships=group.memberships,
        selected_ids={m.user_id for m in group.memberships}, split_values={},
        payer_ids={next_payer["user"].id if next_payer else current_user.id},
        payment_values={}, next_payer=next_payer,
        currency_symbol=symbol_for(group.currency),
        can_choose_currency=can_choose_currency,
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
            payments = _calculate_payments(group, form.amount.data)
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "expenses/form.html", form=form, group=group, expense=expense,
                memberships=group.memberships, selected_ids=_posted_selected_ids(group), split_values=request.form,
                payer_ids=_posted_payer_ids(group), payment_values=request.form,
                next_payer=None, can_choose_currency=False,
            )
        expense.title = form.title.data.strip()
        expense.amount = form.amount.data
        expense.category = form.category.data
        expense.expense_date = form.expense_date.data
        expense.notes = (form.notes.data or "").strip()
        expense.split_method = form.split_method.data
        expense.paid_by_id = payments[0][0].id
        _replace_splits(expense, calculated)
        _replace_payments(expense, payments)
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
        payer_ids={p.user_id for p in expense.payments} or {expense.paid_by_id},
        payment_values={f"payment_value_{p.user_id}": p.amount for p in expense.payments},
        next_payer=None, can_choose_currency=False,
    )


def _posted_selected_ids(group):
    return {m.user_id for m in group.memberships if f"participant_{m.user_id}" in request.form}


def _posted_payer_ids(group):
    return {m.user_id for m in group.memberships if f"payer_{m.user_id}" in request.form}


@expenses_bp.route("/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(group_id, expense_id):
    group = _group_for_member(group_id)
    expense = _expense_in_group(group, expense_id)
    payer_ids = {payment.user_id for payment in expense.payments} or {expense.paid_by_id}
    if current_user.id not in payer_ids and not group.is_admin(current_user):
        abort(403)
    receipt = expense.receipt_filename
    ShoppingItem.query.filter_by(converted_expense_id=expense.id).update(
        {ShoppingItem.converted_expense_id: None}, synchronize_session=False
    )
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
