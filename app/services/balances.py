"""Automatic group balance calculation for US-05."""

from decimal import Decimal


CENT = Decimal("0.01")


def calculate_group_balances(group):
    """Return each active member's net balance.

    Net balance = total paid - total share owed.
    Positive values mean the member should receive money; negative values mean
    the member owes money. A valid group's balances always add up to zero.
    """

    balances = {
        membership.user_id: {
            "user": membership.user,
            "paid": Decimal("0.00"),
            "owed": Decimal("0.00"),
            "net": Decimal("0.00"),
        }
        for membership in group.memberships
    }

    for expense in group.expenses:
        if expense.payments:
            for payment in expense.payments:
                if payment.user_id in balances:
                    balances[payment.user_id]["paid"] += Decimal(payment.amount)
        elif expense.paid_by_id in balances:  # compatibility with old records
            balances[expense.paid_by_id]["paid"] += Decimal(expense.amount)
        for split in expense.splits:
            if split.user_id in balances:
                balances[split.user_id]["owed"] += Decimal(split.amount)

    # A confirmed settlement moves value from the creditor's positive balance
    # to the debtor's negative balance without changing the original expense.
    for settlement in group.settlement_transactions:
        if settlement.status != "completed":
            continue
        amount = Decimal(settlement.amount)
        if settlement.from_user_id in balances:
            balances[settlement.from_user_id]["net"] += amount
        if settlement.to_user_id in balances:
            balances[settlement.to_user_id]["net"] -= amount

    for balance in balances.values():
        balance["paid"] = balance["paid"].quantize(CENT)
        balance["owed"] = balance["owed"].quantize(CENT)
        balance["net"] = (
            balance["paid"] - balance["owed"] + balance["net"]
        ).quantize(CENT)

    return sorted(balances.values(), key=lambda item: (-item["net"], item["user"].name.lower()))
