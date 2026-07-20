"""Recorded settlement payment, confirmation and history tests."""

from decimal import Decimal

from app import db
from app.models import Group, SettlementTransaction
from app.services.balances import calculate_group_balances
from tests.conftest import login, register


def _group_with_debt(client, app, make_user):
    debtor = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Settlement Team", "description": ""})
    with app.app_context():
        group = Group.query.one()
        gid, owner_id, debtor_id = group.id, group.owner_id, debtor.id
    client.post(f"/groups/{gid}/invite", data={"email": debtor.email, "role": "member"})
    client.post(f"/groups/{gid}/expenses/new", data={
        "title": "Dinner", "amount": "12.00", "category": "Eating out",
        "expense_date": "2026-07-20", "notes": "", "split_method": "equal",
        f"participant_{owner_id}": "1", f"participant_{debtor_id}": "1",
    })
    return gid, owner_id, debtor_id


def _record(client, gid, debtor_id, creditor_id, amount="6.00", follow=True):
    return client.post(f"/groups/{gid}/settlements/record", data={
        "from_user_id": str(debtor_id), "to_user_id": str(creditor_id),
        "amount": amount, "note": "Bank transfer",
    }, follow_redirects=follow)


def _nets(app, gid):
    with app.app_context():
        group = db.session.get(Group, gid)
        return {row["user"].name: row["net"] for row in calculate_group_balances(group)}


def test_debtor_records_payment_pending_receiver_confirmation(client, app, make_user):
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    client.get("/auth/logout")
    login(client, email="ananya@srh.de")
    response = _record(client, gid, debtor_id, creditor_id)
    assert b"receiver must confirm" in response.data
    assert b"Settlement history" in response.data
    assert b"Bank transfer" in response.data
    with app.app_context():
        transaction = SettlementTransaction.query.one()
        assert transaction.status == SettlementTransaction.PENDING
    assert _nets(app, gid) == {"Loki": Decimal("6.00"), "Ananya": Decimal("-6.00")}


def test_receiver_confirms_and_balances_become_settled(client, app, make_user):
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    client.get("/auth/logout")
    login(client, email="ananya@srh.de")
    _record(client, gid, debtor_id, creditor_id, follow=False)
    with app.app_context():
        transaction_id = SettlementTransaction.query.one().id
    client.get("/auth/logout")
    login(client)
    response = client.post(
        f"/groups/{gid}/settlements/{transaction_id}/confirm", follow_redirects=True
    )
    assert b"Settlement confirmed" in response.data
    assert b"Everyone is settled" in response.data
    assert b"Completed" in response.data
    assert _nets(app, gid) == {"Loki": Decimal("0.00"), "Ananya": Decimal("0.00")}


def test_receiver_can_record_received_payment_as_completed(client, app, make_user):
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    response = _record(client, gid, debtor_id, creditor_id)
    assert b"recorded and completed" in response.data
    with app.app_context():
        assert SettlementTransaction.query.one().status == SettlementTransaction.COMPLETED


def test_rejected_payment_does_not_change_balances(client, app, make_user):
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    client.get("/auth/logout")
    login(client, email="ananya@srh.de")
    _record(client, gid, debtor_id, creditor_id, follow=False)
    with app.app_context():
        transaction_id = SettlementTransaction.query.one().id
    client.get("/auth/logout")
    login(client)
    response = client.post(
        f"/groups/{gid}/settlements/{transaction_id}/reject", follow_redirects=True
    )
    assert b"payment rejected" in response.data
    assert _nets(app, gid)["Ananya"] == Decimal("-6.00")


def test_payment_cannot_exceed_recommended_amount(client, app, make_user):
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    response = _record(client, gid, debtor_id, creditor_id, amount="20.00")
    assert b"current \xe2\x82\xac6.00 recommendation" in response.data
    with app.app_context():
        assert SettlementTransaction.query.count() == 0


def test_outsider_cannot_record_or_confirm_settlement(client, app, make_user):
    outsider = make_user(name="Outsider", email="outside@srh.de")
    gid, creditor_id, debtor_id = _group_with_debt(client, app, make_user)
    client.get("/auth/logout")
    login(client, email=outsider.email)
    assert _record(client, gid, debtor_id, creditor_id, follow=False).status_code == 403
