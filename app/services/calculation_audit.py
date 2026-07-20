"""Detect inconsistent money records before they affect transfers (US-15)."""

from decimal import Decimal

from .balances import calculate_group_balances

CENT = Decimal("0.01")


def _money(value):
    return Decimal(value or 0).quantize(CENT)


def audit_group_calculations(group):
    """Return a read-only audit of expense payments, splits, and balances."""
    member_ids = {membership.user_id for membership in group.memberships}
    errors = []
    checked_payments = 0
    checked_splits = 0
    for expense in group.expenses:
        amount = _money(expense.amount)
        if amount <= 0:
            errors.append({"code": "invalid-expense-amount", "expense": expense,
                           "title": f"{expense.title} has an invalid amount",
                           "detail": f"The expense amount is €{amount:.2f}; it must be greater than zero."})
        if expense.payments:
            payment_total = sum((_money(item.amount) for item in expense.payments), Decimal("0.00"))
            checked_payments += len(expense.payments)
            if any(item.user_id not in member_ids for item in expense.payments):
                errors.append({"code": "unknown-payer", "expense": expense,
                               "title": f"{expense.title} includes a non-member payer",
                               "detail": "Edit the expense and select current group members as payers."})
            if payment_total != amount:
                errors.append({"code": "payment-total", "expense": expense,
                               "title": f"Payment total does not match {expense.title}",
                               "detail": f"Payments total €{payment_total:.2f}, but the expense is €{amount:.2f}."})
        elif expense.paid_by_id not in member_ids:
            errors.append({"code": "unknown-legacy-payer", "expense": expense,
                           "title": f"{expense.title} has no valid payer",
                           "detail": "Edit the expense and choose a current group member who paid."})
        split_total = sum((_money(item.amount) for item in expense.splits), Decimal("0.00"))
        checked_splits += len(expense.splits)
        if any(item.user_id not in member_ids for item in expense.splits):
            errors.append({"code": "unknown-participant", "expense": expense,
                           "title": f"{expense.title} includes a non-member participant",
                           "detail": "Edit the expense and split it among current group members."})
        if not expense.splits or split_total != amount:
            errors.append({"code": "split-total", "expense": expense,
                           "title": f"Split total does not match {expense.title}",
                           "detail": f"Shares total €{split_total:.2f}, but the expense is €{amount:.2f}."})
    balances = calculate_group_balances(group)
    balance_total = sum((item["net"] for item in balances), Decimal("0.00")).quantize(CENT)
    if balance_total != Decimal("0.00"):
        errors.append({"code": "unbalanced-group", "expense": None,
                       "title": "Group balances do not add up to zero",
                       "detail": f"The current balance difference is €{balance_total:.2f}. Review the flagged expenses."})
    return {"healthy": not errors, "errors": errors, "expense_count": len(group.expenses),
            "checked_payments": checked_payments, "checked_splits": checked_splits,
            "balance_total": balance_total}
