"""Collaborative shopping-list routes scoped to a group."""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from .. import db
from ..models import Expense, ExpensePayment, ExpenseSplit, Group, ShoppingItem
from ..services.preferences import symbol_for
from .forms import ShoppingItemForm


shopping_bp = Blueprint(
    "shopping", __name__, url_prefix="/groups/<int:group_id>/shopping"
)


def _group_for_member(group_id):
    group = db.session.get(Group, group_id) or abort(404)
    if not group.has_member(current_user):
        abort(403)
    return group


def _item_in_group(group, item_id):
    return ShoppingItem.query.filter_by(id=item_id, group_id=group.id).first_or_404()


def _repair_stale_conversion_links(group):
    """Make items reusable if their generated expense was later deleted."""
    repaired = False
    for item in group.shopping_items:
        if item.converted_expense_id and item.converted_expense is None:
            item.converted_expense_id = None
            repaired = True
    if repaired:
        db.session.commit()


def _member_choices(group):
    return [(0, "Anyone")] + [
        (membership.user_id, membership.user.name)
        for membership in sorted(group.memberships, key=lambda value: value.user.name.lower())
    ]


@shopping_bp.route("/")
@login_required
def view_list(group_id):
    group = _group_for_member(group_id)
    _repair_stale_conversion_links(group)
    form = ShoppingItemForm()
    form.assigned_to.choices = _member_choices(group)
    active = [item for item in group.shopping_items if not item.is_purchased]
    completed = [item for item in group.shopping_items if item.is_purchased]
    total = len(active) + len(completed)
    progress = round(len(completed) / total * 100) if total else 0
    return render_template(
        "shopping/list.html", group=group, form=form, active=active,
        completed=completed, progress=progress, is_admin=group.is_admin(current_user),
        member_choices=_member_choices(group),
        convertible=[item for item in completed if item.price and not item.converted_expense_id],
        currency_symbol=symbol_for(group.currency),
    )


@shopping_bp.route("/add", methods=["POST"])
@login_required
def add_item(group_id):
    group = _group_for_member(group_id)
    form = ShoppingItemForm()
    form.assigned_to.choices = _member_choices(group)
    if form.validate_on_submit():
        assigned_id = form.assigned_to.data or None
        if assigned_id and not any(m.user_id == assigned_id for m in group.memberships):
            abort(400)
        db.session.add(ShoppingItem(
            group_id=group.id, name=form.name.data.strip(),
            quantity=form.quantity.data.strip(), category=form.category.data,
            note=(form.note.data or "").strip(), added_by_id=current_user.id,
            assigned_to_id=assigned_id,
            price=form.price.data,
        ))
        db.session.commit()
        flash(f"{form.name.data.strip()} added to the shopping list.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
    return redirect(url_for("shopping.view_list", group_id=group.id))


@shopping_bp.route("/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_item(group_id, item_id):
    group = _group_for_member(group_id)
    item = _item_in_group(group, item_id)
    item.is_purchased = not item.is_purchased
    item.purchased_by_id = current_user.id if item.is_purchased else None
    item.purchased_at = datetime.now(timezone.utc) if item.is_purchased else None
    db.session.commit()
    flash(f"{item.name} marked {'purchased' if item.is_purchased else 'needed'}.", "success")
    return redirect(url_for("shopping.view_list", group_id=group.id))


@shopping_bp.route("/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_item(group_id, item_id):
    group = _group_for_member(group_id)
    item = _item_in_group(group, item_id)
    form = ShoppingItemForm()
    form.assigned_to.choices = _member_choices(group)
    if form.validate_on_submit():
        assigned_id = form.assigned_to.data or None
        if assigned_id and not any(m.user_id == assigned_id for m in group.memberships):
            abort(400)
        item.name = form.name.data.strip()
        item.quantity = form.quantity.data.strip()
        item.category = form.category.data
        item.note = (form.note.data or "").strip()
        item.price = form.price.data
        item.assigned_to_id = assigned_id
        db.session.commit()
        flash("Shopping item updated.", "success")
    return redirect(url_for("shopping.view_list", group_id=group.id))


@shopping_bp.route("/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(group_id, item_id):
    group = _group_for_member(group_id)
    item = _item_in_group(group, item_id)
    if item.added_by_id != current_user.id and not group.is_admin(current_user):
        abort(403)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f"{name} removed from the shopping list.", "info")
    return redirect(url_for("shopping.view_list", group_id=group.id))


@shopping_bp.route("/completed/clear", methods=["POST"])
@login_required
def clear_completed(group_id):
    group = _group_for_member(group_id)
    count = ShoppingItem.query.filter_by(group_id=group.id, is_purchased=True).delete()
    db.session.commit()
    flash(f"Cleared {count} purchased item{'s' if count != 1 else ''}.", "info")
    return redirect(url_for("shopping.view_list", group_id=group.id))


@shopping_bp.route("/completed/to-expense", methods=["POST"])
@login_required
def completed_to_expense(group_id):
    group = _group_for_member(group_id)
    _repair_stale_conversion_links(group)
    items = [item for item in group.shopping_items
             if item.is_purchased and item.price and not item.converted_expense_id]
    if not items:
        flash("Add prices to purchased items before creating an expense.", "error")
        return redirect(url_for("shopping.view_list", group_id=group.id))
    total = sum((Decimal(item.price) for item in items), Decimal("0.00")).quantize(Decimal("0.01"))
    payer_totals = {}
    for item in items:
        payer_id = item.purchased_by_id or current_user.id
        payer_totals[payer_id] = payer_totals.get(payer_id, Decimal("0.00")) + Decimal(item.price)
    expense = Expense(group_id=group.id, paid_by_id=next(iter(payer_totals)),
                      title=f"Shopping list · {date.today().strftime('%d %b %Y')}",
                      amount=total, category="Groceries", expense_date=date.today(),
                      notes=", ".join(item.name for item in items)[:500], split_method="equal",
                      currency=group.currency)
    for payer_id, paid in payer_totals.items():
        expense.payments.append(ExpensePayment(user_id=payer_id, amount=paid))
    members = [membership.user for membership in group.memberships]
    allocated = Decimal("0.00")
    for user in members[:-1]:
        share = (total / len(members)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expense.splits.append(ExpenseSplit(user_id=user.id, amount=share, input_value=1))
        allocated += share
    expense.splits.append(ExpenseSplit(user_id=members[-1].id, amount=total - allocated, input_value=1))
    db.session.add(expense)
    db.session.flush()
    for item in items:
        item.converted_expense_id = expense.id
    db.session.commit()
    flash(f"Created a {total:.2f} group expense from {len(items)} purchased items.", "success")
    return redirect(url_for("groups.view_group", group_id=group.id))
