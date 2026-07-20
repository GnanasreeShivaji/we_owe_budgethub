"""US-05 automatic balance calculation and UI refresh tests."""

from decimal import Decimal

from app import db
from app.models import Expense, ExpensePayment, Group
from app.services.balances import calculate_group_balances
from tests.conftest import login, register


def _two_member_group(client, app, make_user):
    member = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Balance Team", "description": ""})
    with app.app_context():
        group = Group.query.filter_by(name="Balance Team").one()
        gid, owner_id, member_id = group.id, group.owner_id, member.id
    client.post(
        f"/groups/{gid}/invite",
        data={"email": "ananya@srh.de", "role": "member"},
    )
    return gid, owner_id, member_id


def _expense(client, gid, owner_id, member_id, amount="12.00", title="Shared cost"):
    return client.post(
        f"/groups/{gid}/expenses/new",
        data={
            "title": title,
            "amount": amount,
            "category": "Other",
            "expense_date": "2026-07-17",
            "notes": "",
            "split_method": "equal",
            f"participant_{owner_id}": "1",
            f"participant_{member_id}": "1",
        },
        follow_redirects=True,
    )


def _nets(app, gid):
    with app.app_context():
        group = db.session.get(Group, gid)
        return {item["user"].name: item["net"] for item in calculate_group_balances(group)}


def test_one_expense_calculates_who_owes_and_receives(client, app, make_user):
    gid, owner, member = _two_member_group(client, app, make_user)
    response = _expense(client, gid, owner, member)

    assert b"Should receive" in response.data
    assert b"Owes" in response.data
    assert _nets(app, gid) == {
        "Loki": Decimal("6.00"),
        "Ananya": Decimal("-6.00"),
    }


def test_balances_update_with_sample_transactions(client, app, make_user):
    gid, owner, member = _two_member_group(client, app, make_user)
    _expense(client, gid, owner, member, "12.00", "Groceries")

    client.get("/auth/logout")
    login(client, email="ananya@srh.de")
    response = _expense(client, gid, owner, member, "8.00", "Transport")

    assert response.status_code == 200
    assert _nets(app, gid) == {
        "Loki": Decimal("2.00"),
        "Ananya": Decimal("-2.00"),
    }


def test_balance_ui_refreshes_after_edit_and_delete(client, app, make_user):
    gid, owner, member = _two_member_group(client, app, make_user)
    _expense(client, gid, owner, member)
    with app.app_context():
        expense_id = Expense.query.one().id

    edit = client.post(
        f"/groups/{gid}/expenses/{expense_id}/edit",
        data={
            "title": "Updated cost",
            "amount": "20.00",
            "category": "Other",
            "expense_date": "2026-07-17",
            "notes": "",
            "split_method": "equal",
            f"participant_{owner}": "1",
            f"participant_{member}": "1",
        },
        follow_redirects=True,
    )
    assert b"Should receive <strong>\xe2\x82\xac10.00" in edit.data
    assert _nets(app, gid)["Ananya"] == Decimal("-10.00")

    deleted = client.post(
        f"/groups/{gid}/expenses/{expense_id}/delete", follow_redirects=True
    )
    assert deleted.data.count(b"Settled up") == 2
    assert all(value == 0 for value in _nets(app, gid).values())


def test_group_balances_always_sum_to_zero(client, app, make_user):
    gid, owner, member = _two_member_group(client, app, make_user)
    _expense(client, gid, owner, member, "19.59")
    assert sum(_nets(app, gid).values()) == Decimal("0.00")


def test_two_members_can_pay_one_expense(client, app, make_user):
    gid, owner, member = _two_member_group(client, app, make_user)
    response = client.post(
        f"/groups/{gid}/expenses/new",
        data={
            "title": "WG groceries",
            "amount": "40.00",
            "category": "Groceries",
            "expense_date": "2026-07-17",
            "notes": "",
            "split_method": "equal",
            f"participant_{owner}": "1",
            f"participant_{member}": "1",
            f"payer_{owner}": "1",
            f"payment_value_{owner}": "30.00",
            f"payer_{member}": "1",
            f"payment_value_{member}": "10.00",
        },
        follow_redirects=True,
    )

    assert b"Expense saved successfully" in response.data
    assert "Loki €30.00".encode() in response.data
    assert "Ananya €10.00".encode() in response.data
    with app.app_context():
        assert ExpensePayment.query.count() == 2
    assert _nets(app, gid) == {
        "Loki": Decimal("10.00"),
        "Ananya": Decimal("-10.00"),
    }
