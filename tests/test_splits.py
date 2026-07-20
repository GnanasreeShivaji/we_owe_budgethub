"""US-04 acceptance tests for equal, exact, percentage and shares splits."""

from decimal import Decimal

from app import db
from app.models import Expense, ExpenseSplit, Group, User
from tests.conftest import register


def _group_with_two_members(client, app, make_user):
    member = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Team", "description": ""})
    with app.app_context():
        group = Group.query.filter_by(name="Team").one()
        gid = group.id
        owner_id = group.owner_id
        member_id = member.id
    client.post(
        f"/groups/{gid}/invite",
        data={"email": "ananya@srh.de", "role": "member"},
    )
    return gid, owner_id, member_id


def _post_split(client, gid, owner_id, member_id, method, first=None, second=None):
    data = {
        "title": "Claude subscription",
        "amount": "12.00",
        "category": "Other",
        "expense_date": "2026-07-16",
        "notes": "Shared project subscription",
        "split_method": method,
        f"participant_{owner_id}": "1",
        f"participant_{member_id}": "1",
    }
    if first is not None:
        data[f"split_value_{owner_id}"] = str(first)
    if second is not None:
        data[f"split_value_{member_id}"] = str(second)
    return client.post(f"/groups/{gid}/expenses/new", data=data, follow_redirects=True)


def _amounts(app):
    with app.app_context():
        return sorted(Decimal(split.amount) for split in ExpenseSplit.query.all())


def test_equal_split(client, app, make_user):
    gid, owner, member = _group_with_two_members(client, app, make_user)
    response = _post_split(client, gid, owner, member, "equal")
    assert b"Expense saved successfully" in response.data
    assert b"Member contribution" in response.data
    assert b"contribution-pie" in response.data
    assert b"contribution-legend" in response.data
    assert b"Percentage" in response.data
    assert response.data.count(b"50.0%") == 4  # legend and bar label for both members
    assert _amounts(app) == [Decimal("6.00"), Decimal("6.00")]


def test_exact_amount_split_and_total_validation(client, app, make_user):
    gid, owner, member = _group_with_two_members(client, app, make_user)
    bad = _post_split(client, gid, owner, member, "exact", 8, 3)
    assert b"Exact amounts must add up to 12.00" in bad.data
    with app.app_context():
        assert Expense.query.count() == 0

    good = _post_split(client, gid, owner, member, "exact", 8, 4)
    assert b"Expense saved successfully" in good.data
    assert _amounts(app) == [Decimal("4.00"), Decimal("8.00")]


def test_percentage_split_and_validation(client, app, make_user):
    gid, owner, member = _group_with_two_members(client, app, make_user)
    bad = _post_split(client, gid, owner, member, "percentage", 60, 30)
    assert b"Percentages must add up to 100%" in bad.data

    good = _post_split(client, gid, owner, member, "percentage", 75, 25)
    assert b"Expense saved successfully" in good.data
    assert _amounts(app) == [Decimal("3.00"), Decimal("9.00")]


def test_shares_split(client, app, make_user):
    gid, owner, member = _group_with_two_members(client, app, make_user)
    response = _post_split(client, gid, owner, member, "shares", 1, 3)
    assert b"Expense saved successfully" in response.data
    assert _amounts(app) == [Decimal("3.00"), Decimal("9.00")]


def test_edit_saved_split(client, app, make_user):
    gid, owner, member = _group_with_two_members(client, app, make_user)
    _post_split(client, gid, owner, member, "equal")
    with app.app_context():
        expense_id = Expense.query.one().id

    data = {
        "title": "Claude subscription",
        "amount": "12.00",
        "category": "Other",
        "expense_date": "2026-07-16",
        "notes": "Updated split",
        "split_method": "exact",
        f"participant_{owner}": "1",
        f"participant_{member}": "1",
        f"split_value_{owner}": "7.00",
        f"split_value_{member}": "5.00",
    }
    response = client.post(
        f"/groups/{gid}/expenses/{expense_id}/edit", data=data, follow_redirects=True
    )
    assert b"Expense updated successfully" in response.data
    assert _amounts(app) == [Decimal("5.00"), Decimal("7.00")]
