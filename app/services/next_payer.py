"""Fair, explainable next-payer recommendation for a group (US-12)."""

from decimal import Decimal


CENT = Decimal("0.01")


def recommend_next_payer(group, symbol="€"):
    """Recommend a payer from actual payment and assigned-share history.

    A member who has paid less than their accumulated share is selected first.
    If nobody is behind, the member who paid least recently is suggested. An
    empty group history never produces a made-up recommendation.
    """
    positions = {
        membership.user_id: {
            "user": membership.user,
            "paid": Decimal("0.00"),
            "share": Decimal("0.00"),
            "times_paid": 0,
            "last_paid": None,
        }
        for membership in group.memberships
    }

    for expense in group.expenses:
        payments = expense.payments or []
        if payments:
            for payment in payments:
                if payment.user_id not in positions:
                    continue
                item = positions[payment.user_id]
                item["paid"] += Decimal(payment.amount)
                item["times_paid"] += 1
                if item["last_paid"] is None or expense.expense_date > item["last_paid"]:
                    item["last_paid"] = expense.expense_date
        elif expense.paid_by_id in positions:
            item = positions[expense.paid_by_id]
            item["paid"] += Decimal(expense.amount)
            item["times_paid"] += 1
            if item["last_paid"] is None or expense.expense_date > item["last_paid"]:
                item["last_paid"] = expense.expense_date
        for split in expense.splits:
            if split.user_id in positions:
                positions[split.user_id]["share"] += Decimal(split.amount)

    active = []
    for item in positions.values():
        item["paid"] = item["paid"].quantize(CENT)
        item["share"] = item["share"].quantize(CENT)
        item["gap"] = (item["share"] - item["paid"]).quantize(CENT)
        if item["paid"] or item["share"]:
            active.append(item)
    if not active:
        return None

    behind = [item for item in active if item["gap"] > 0]
    if behind:
        selected = sorted(
            behind,
            key=lambda item: (-item["gap"], item["times_paid"], item["user"].name.lower()),
        )[0]
        reason = (
            f"They have paid {symbol}{selected['paid']:.2f} toward {symbol}{selected['share']:.2f} "
            f"of assigned shares, leaving a {symbol}{selected['gap']:.2f} contribution gap."
        )
        basis = "contribution gap"
    else:
        selected = sorted(
            active,
            key=lambda item: (
                item["last_paid"] is not None,
                item["last_paid"] or group.created_at.date(),
                item["times_paid"],
                item["user"].name.lower(),
            ),
        )[0]
        last = selected["last_paid"].strftime("%d %b %Y") if selected["last_paid"] else "never"
        reason = (
            "Everyone's recorded contribution is currently covered. "
            f"This member paid least recently ({last}), so rotating to them is fairest."
        )
        basis = "payment rotation"

    ordered = sorted(active, key=lambda item: (-item["gap"], item["user"].name.lower()))
    return {"user": selected["user"], "reason": reason, "basis": basis, "positions": ordered}
