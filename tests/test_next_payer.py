"""US-12 fair next-payer recommendation tests."""

from datetime import date
from decimal import Decimal

from app import db
from app.models import Expense, ExpensePayment, ExpenseSplit, Group, Membership
from app.services.next_payer import recommend_next_payer
from tests.conftest import register


def _group_with_member(client, app, make_user):
    member = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Fair Flat", "description": ""})
    with app.app_context():
        group = Group.query.filter_by(name="Fair Flat").one()
        group_id, owner_id, member_id = group.id, group.owner_id, member.id
    client.post(f"/groups/{group_id}/invite",
                data={"email": member.email, "role": Membership.MEMBER})
    return group_id, owner_id, member_id


def _saved_expense(app, group_id, payer_id, owner_id, member_id, amount="12.00", day=17):
    with app.app_context():
        expense = Expense(group_id=group_id, paid_by_id=payer_id, title="Shared food",
                          amount=Decimal(amount), category="Groceries",
                          expense_date=date(2026, 7, day), split_method="equal")
        db.session.add(expense); db.session.flush()
        db.session.add(ExpensePayment(expense_id=expense.id, user_id=payer_id,
                                      amount=Decimal(amount)))
        half = Decimal(amount) / 2
        db.session.add_all([
            ExpenseSplit(expense_id=expense.id, user_id=owner_id, amount=half, input_value=1),
            ExpenseSplit(expense_id=expense.id, user_id=member_id, amount=half, input_value=1),
        ])
        db.session.commit()


def test_no_history_does_not_invent_next_payer(client, app, make_user):
    group_id, _owner_id, _member_id = _group_with_member(client, app, make_user)
    response = client.get(f"/groups/{group_id}")
    assert b"No recommendation yet" in response.data
    assert b"only after real payment history exists" in response.data
    with app.app_context():
        assert recommend_next_payer(db.session.get(Group, group_id)) is None


def test_member_with_largest_contribution_gap_is_recommended(client, app, make_user):
    group_id, owner_id, member_id = _group_with_member(client, app, make_user)
    _saved_expense(app, group_id, owner_id, owner_id, member_id)
    response = client.get(f"/groups/{group_id}")
    assert b"Ananya should pay next" in response.data
    assert b"leaving a \xe2\x82\xac6.00 contribution gap" in response.data
    assert b"Paid \xe2\x82\xac0.00" in response.data
    assert b"Assigned \xe2\x82\xac6.00" in response.data


def test_recommended_member_is_preselected_on_new_expense(client, app, make_user):
    group_id, owner_id, member_id = _group_with_member(client, app, make_user)
    _saved_expense(app, group_id, owner_id, owner_id, member_id)
    response = client.get(f"/groups/{group_id}/expenses/new")
    html = response.data.decode()
    assert "Suggested next payer: Ananya" in html
    member_checkbox = html.split(f'name="payer_{member_id}"', 1)[1].split(">", 1)[0]
    owner_checkbox = html.split(f'name="payer_{owner_id}"', 1)[1].split(">", 1)[0]
    assert "checked" in member_checkbox
    assert "checked" not in owner_checkbox


def test_rotation_uses_oldest_payment_when_contributions_are_even(client, app, make_user):
    group_id, owner_id, member_id = _group_with_member(client, app, make_user)
    _saved_expense(app, group_id, owner_id, owner_id, member_id, day=17)
    _saved_expense(app, group_id, member_id, owner_id, member_id, day=18)
    with app.app_context():
        result = recommend_next_payer(db.session.get(Group, group_id))
        assert result["user"].id == owner_id
        assert result["basis"] == "payment rotation"
        assert all(item["gap"] == Decimal("0.00") for item in result["positions"])
    response = client.get(f"/groups/{group_id}")
    assert b"Loki should pay next" in response.data
    assert b"paid least recently" in response.data
