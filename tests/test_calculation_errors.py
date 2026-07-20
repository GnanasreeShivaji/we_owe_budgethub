"""US-15 calculation error management and transfer edge-case tests."""

from decimal import Decimal

from app import db
from app.models import Expense, ExpenseSplit, Group, SettlementTransaction
from app.services.calculation_audit import audit_group_calculations
from app.services.balances import calculate_group_balances
from tests.conftest import login, register


def _three_member_group(client, app, make_user):
    ananya = make_user(name="Ananya", email="ananya@srh.de")
    kavin = make_user(name="Kavin", email="kavin@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Audit Flat", "description": ""})
    with app.app_context():
        group = Group.query.one()
        ids = group.id, group.owner_id, ananya.id, kavin.id
    client.post(f"/groups/{ids[0]}/invite", data={"email": ananya.email, "role": "member"})
    client.post(f"/groups/{ids[0]}/invite", data={"email": kavin.email, "role": "member"})
    return ids


def _add_equal_expense(client, group_id, user_ids, amount="10.00"):
    data = {"title": "Cash groceries", "amount": amount, "category": "Groceries",
            "expense_date": "2026-07-21", "notes": "cash", "split_method": "equal"}
    data.update({f"participant_{user_id}": "1" for user_id in user_ids})
    return client.post(f"/groups/{group_id}/expenses/new", data=data, follow_redirects=True)


def test_cash_cent_rounding_stays_balanced(client, app, make_user):
    group_id, owner_id, ananya_id, kavin_id = _three_member_group(client, app, make_user)
    response = _add_equal_expense(client, group_id, [owner_id, ananya_id, kavin_id])
    assert b"Expense saved successfully" in response.data
    assert b"Calculations verified" in response.data
    with app.app_context():
        expense = Expense.query.one()
        assert sorted(split.amount for split in expense.splits) == [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")]
        audit = audit_group_calculations(db.session.get(Group, group_id))
        assert audit["healthy"] is True
        assert audit["balance_total"] == Decimal("0.00")


def test_corrupt_split_is_explained_and_settlement_is_paused(client, app, make_user):
    group_id, owner_id, ananya_id, _kavin_id = _three_member_group(client, app, make_user)
    _add_equal_expense(client, group_id, [owner_id, ananya_id], "12.00")
    with app.app_context():
        split = ExpenseSplit.query.filter_by(user_id=ananya_id).one()
        split.amount = Decimal("5.00")
        db.session.commit()
    page = client.get(f"/groups/{group_id}")
    assert b"calculation issue(s) found" in page.data
    assert b"Shares total \xe2\x82\xac11.00, but the expense is \xe2\x82\xac12.00" in page.data
    assert b"Settlement is paused" in page.data
    response = client.post(f"/groups/{group_id}/settlements/record", data={
        "from_user_id": ananya_id, "to_user_id": owner_id, "amount": "5.00"
    }, follow_redirects=True)
    assert b"calculation error" in response.data
    with app.app_context():
        assert SettlementTransaction.query.count() == 0


def test_payment_total_mismatch_is_detected(client, app, make_user):
    group_id, owner_id, ananya_id, _kavin_id = _three_member_group(client, app, make_user)
    _add_equal_expense(client, group_id, [owner_id, ananya_id], "12.00")
    with app.app_context():
        expense = Expense.query.one()
        expense.payments[0].amount = Decimal("11.99")
        db.session.commit()
        audit = audit_group_calculations(db.session.get(Group, group_id))
        assert audit["healthy"] is False
        assert "payment-total" in {error["code"] for error in audit["errors"]}


def test_invalid_transfer_does_not_partially_write(client, app, make_user):
    group_id, owner_id, ananya_id, _kavin_id = _three_member_group(client, app, make_user)
    _add_equal_expense(client, group_id, [owner_id, ananya_id], "12.00")
    response = client.post(f"/groups/{group_id}/settlements/record", data={
        "from_user_id": ananya_id, "to_user_id": owner_id, "amount": "6.01"
    }, follow_redirects=True)
    assert b"current \xe2\x82\xac6.00 recommendation" in response.data
    with app.app_context():
        assert SettlementTransaction.query.count() == 0


def test_partial_transfer_confirms_smoothly_and_keeps_remaining_balance(client, app, make_user):
    group_id, owner_id, ananya_id, _kavin_id = _three_member_group(client, app, make_user)
    _add_equal_expense(client, group_id, [owner_id, ananya_id], "12.00")
    client.get("/auth/logout"); login(client, email="ananya@srh.de")
    client.post(f"/groups/{group_id}/settlements/record", data={
        "from_user_id": ananya_id, "to_user_id": owner_id, "amount": "2.50"
    })
    with app.app_context():
        transaction_id = SettlementTransaction.query.one().id
    client.get("/auth/logout"); login(client)
    response = client.post(
        f"/groups/{group_id}/settlements/{transaction_id}/confirm", follow_redirects=True
    )
    assert b"Settlement confirmed" in response.data
    with app.app_context():
        balances = {item["user"].id: item["net"] for item in calculate_group_balances(db.session.get(Group, group_id))}
        assert balances[owner_id] == Decimal("3.50")
        assert balances[ananya_id] == Decimal("-3.50")
        assert sum(balances.values()) == Decimal("0.00")
