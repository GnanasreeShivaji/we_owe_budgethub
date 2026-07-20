"""Smart debt settlement calculation for US-06."""

from decimal import Decimal, InvalidOperation


CENT = Decimal("0.01")


def calculate_settlements(balances):
    """Create a small set of debtor-to-creditor transfers.

    ``balances`` is the output of ``calculate_group_balances``. Negative net
    values owe money and positive values should receive money. The greedy
    largest-debt/largest-credit match settles at least one member per transfer,
    so no more than n-1 transfers are produced for n unsettled members.
    """
    debtors = []
    creditors = []
    total = Decimal("0.00")

    for balance in balances:
        try:
            net = Decimal(balance["net"]).quantize(CENT)
            user = balance["user"]
        except (KeyError, InvalidOperation, TypeError) as error:
            raise ValueError("Invalid balance data supplied for settlement.") from error
        total += net
        if net < 0:
            debtors.append([user, -net])
        elif net > 0:
            creditors.append([user, net])

    if total.quantize(CENT) != Decimal("0.00"):
        raise ValueError("Balances do not add up to zero; settlement cannot be calculated.")

    debtors.sort(key=lambda item: (-item[1], item[0].name.lower()))
    creditors.sort(key=lambda item: (-item[1], item[0].name.lower()))
    transfers = []
    debtor_index = creditor_index = 0

    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor, debt = debtors[debtor_index]
        creditor, credit = creditors[creditor_index]
        amount = min(debt, credit).quantize(CENT)
        if amount > 0:
            transfers.append({"from_user": debtor, "to_user": creditor, "amount": amount})
        debtors[debtor_index][1] = (debt - amount).quantize(CENT)
        creditors[creditor_index][1] = (credit - amount).quantize(CENT)
        if debtors[debtor_index][1] == 0:
            debtor_index += 1
        if creditors[creditor_index][1] == 0:
            creditor_index += 1

    return transfers
