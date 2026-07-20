"""Record, confirm and audit group settlement payments."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user, login_required

from .. import db
from ..models import Group, SettlementTransaction
from ..services.balances import calculate_group_balances
from ..services.settlements import calculate_settlements
from ..services.calculation_audit import audit_group_calculations
from ..services.preferences import symbol_for


settlement_records_bp = Blueprint(
    "settlement_records", __name__, url_prefix="/groups/<int:group_id>/settlements"
)


def _group_for_member(group_id):
    group = db.session.get(Group, group_id) or abort(404)
    if not group.has_member(current_user):
        abort(403)
    return group


def _transaction(group, transaction_id):
    return SettlementTransaction.query.filter_by(
        id=transaction_id, group_id=group.id
    ).first_or_404()


def _recommended_amount(group, from_user_id, to_user_id):
    for item in calculate_settlements(calculate_group_balances(group)):
        if item["from_user"].id == from_user_id and item["to_user"].id == to_user_id:
            return Decimal(item["amount"])
    return Decimal("0.00")


@settlement_records_bp.route("/record", methods=["POST"])
@login_required
def record_payment(group_id):
    group = _group_for_member(group_id)
    if not audit_group_calculations(group)["healthy"]:
        flash("Settlement is paused because this group has a calculation error. Review Calculation health.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id, _anchor="calculation-health"))
    try:
        from_user_id = int(request.form.get("from_user_id", ""))
        to_user_id = int(request.form.get("to_user_id", ""))
        amount = Decimal(request.form.get("amount", "")).quantize(Decimal("0.01"))
    except (ValueError, InvalidOperation):
        abort(400)
    member_ids = {membership.user_id for membership in group.memberships}
    if from_user_id not in member_ids or to_user_id not in member_ids or from_user_id == to_user_id:
        abort(400)
    if current_user.id not in {from_user_id, to_user_id} and not group.is_admin(current_user):
        abort(403)
    recommended = _recommended_amount(group, from_user_id, to_user_id)
    if amount <= 0 or amount > recommended:
        symbol = symbol_for(group.currency)
        flash(f"Payment must be between {symbol}0.01 and the current {symbol}{recommended:.2f} recommendation.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-plan"))
    duplicate = SettlementTransaction.query.filter_by(
        group_id=group.id, from_user_id=from_user_id, to_user_id=to_user_id,
        status=SettlementTransaction.PENDING,
    ).first()
    if duplicate:
        flash("This payment is already waiting for confirmation.", "info")
        return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-history"))
    receiver_recorded = current_user.id == to_user_id
    transaction = SettlementTransaction(
        group_id=group.id, from_user_id=from_user_id, to_user_id=to_user_id,
        amount=amount, note=request.form.get("note", "").strip()[:240],
        created_by_id=current_user.id,
        status=SettlementTransaction.COMPLETED if receiver_recorded else SettlementTransaction.PENDING,
        confirmed_by_id=current_user.id if receiver_recorded else None,
        completed_at=datetime.now(timezone.utc) if receiver_recorded else None,
        currency=group.currency,
    )
    db.session.add(transaction)
    db.session.commit()
    flash(
        "Settlement recorded and completed." if receiver_recorded
        else "Payment recorded. The receiver must confirm it.",
        "success",
    )
    return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-history"))


@settlement_records_bp.route("/<int:transaction_id>/confirm", methods=["POST"])
@login_required
def confirm_payment(group_id, transaction_id):
    group = _group_for_member(group_id)
    transaction = _transaction(group, transaction_id)
    if current_user.id != transaction.to_user_id and not group.is_admin(current_user):
        abort(403)
    if not audit_group_calculations(group)["healthy"]:
        flash("This payment cannot be confirmed until the group calculation error is fixed.", "error")
        return redirect(url_for("groups.view_group", group_id=group.id, _anchor="calculation-health"))
    if transaction.status != SettlementTransaction.PENDING:
        flash("This settlement is no longer awaiting confirmation.", "info")
    else:
        transaction.status = SettlementTransaction.COMPLETED
        transaction.confirmed_by_id = current_user.id
        transaction.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Settlement confirmed. Group balances were updated.", "success")
    return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-history"))


@settlement_records_bp.route("/<int:transaction_id>/reject", methods=["POST"])
@login_required
def reject_payment(group_id, transaction_id):
    group = _group_for_member(group_id)
    transaction = _transaction(group, transaction_id)
    if current_user.id != transaction.to_user_id and not group.is_admin(current_user):
        abort(403)
    if transaction.status == SettlementTransaction.PENDING:
        transaction.status = SettlementTransaction.REJECTED
        transaction.confirmed_by_id = current_user.id
        db.session.commit()
        flash("Settlement payment rejected. Balances were not changed.", "info")
    return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-history"))


@settlement_records_bp.route("/<int:transaction_id>/cancel", methods=["POST"])
@login_required
def cancel_payment(group_id, transaction_id):
    group = _group_for_member(group_id)
    transaction = _transaction(group, transaction_id)
    if current_user.id != transaction.created_by_id and not group.is_admin(current_user):
        abort(403)
    if transaction.status == SettlementTransaction.PENDING:
        transaction.status = SettlementTransaction.CANCELLED
        db.session.commit()
        flash("Pending settlement cancelled.", "info")
    return redirect(url_for("groups.view_group", group_id=group.id, _anchor="settlement-history"))
