"""US-06 smart settlement calculation tests."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.settlements import calculate_settlements


def _user(name):
    return SimpleNamespace(name=name)


def _balance(name, amount):
    return {"user": _user(name), "net": Decimal(amount)}


def test_two_member_settlement_instruction():
    plan = calculate_settlements([
        _balance("Gnanasree", "10.00"),
        _balance("Ananya", "-10.00"),
    ])
    assert len(plan) == 1
    assert plan[0]["from_user"].name == "Ananya"
    assert plan[0]["to_user"].name == "Gnanasree"
    assert plan[0]["amount"] == Decimal("10.00")


def test_multiple_debts_are_settled_with_few_transfers():
    plan = calculate_settlements([
        _balance("A", "15.00"),
        _balance("B", "5.00"),
        _balance("C", "-12.00"),
        _balance("D", "-8.00"),
    ])
    assert sum(item["amount"] for item in plan) == Decimal("20.00")
    assert len(plan) <= 3


def test_settled_group_requires_no_transfers():
    assert calculate_settlements([_balance("A", "0"), _balance("B", "0")]) == []


def test_rounding_and_invalid_unbalanced_input():
    plan = calculate_settlements([
        _balance("A", "6.67"),
        _balance("B", "-3.335"),
        _balance("C", "-3.33"),
    ])
    assert [item["amount"] for item in plan] == [Decimal("3.34"), Decimal("3.33")]
    with pytest.raises(ValueError, match="do not add up to zero"):
        calculate_settlements([_balance("A", "5"), _balance("B", "-4")])
