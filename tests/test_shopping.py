"""US-08 shared shopping-list acceptance tests."""

from app.models import Group, ShoppingItem
from tests.conftest import login, register


def _group_with_member(client, app, make_user):
    member = make_user(name="Kavin", email="kavin@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Flat", "description": ""})
    with app.app_context():
        group = Group.query.one()
        gid, owner_id, member_id = group.id, group.owner_id, member.id
    client.post(f"/groups/{gid}/invite", data={"email": member.email, "role": "member"})
    return gid, owner_id, member_id


def _item_data(**changes):
    data = {
        "name": "Oat milk", "quantity": "2 cartons", "category": "Groceries",
        "note": "Unsweetened", "assigned_to": "0",
    }
    data.update(changes)
    return data


def test_group_member_can_add_and_view_shopping_item(client, app, make_user):
    gid, _, member_id = _group_with_member(client, app, make_user)
    response = client.post(
        f"/groups/{gid}/shopping/add",
        data=_item_data(assigned_to=str(member_id)), follow_redirects=True,
    )
    assert b"Oat milk added" in response.data
    assert b"2 cartons" in response.data
    assert b"Kavin will buy" in response.data
    with app.app_context():
        item = ShoppingItem.query.one()
        assert item.group_id == gid
        assert item.assigned_to_id == member_id


def test_member_can_edit_and_check_off_shared_item(client, app, make_user):
    gid, _, _ = _group_with_member(client, app, make_user)
    client.post(f"/groups/{gid}/shopping/add", data=_item_data())
    with app.app_context():
        item_id = ShoppingItem.query.one().id
    client.get("/auth/logout")
    login(client, email="kavin@srh.de")
    edited = client.post(f"/groups/{gid}/shopping/{item_id}/edit", data=_item_data(
        name="Soy milk", quantity="1 carton", note="Barista",
    ), follow_redirects=True)
    assert b"Shopping item updated" in edited.data
    assert b"Soy milk" in edited.data
    completed = client.post(
        f"/groups/{gid}/shopping/{item_id}/toggle", follow_redirects=True
    )
    assert b"marked purchased" in completed.data
    assert b"Purchased by Kavin" in completed.data


def test_non_member_cannot_access_group_shopping_list(client, app, make_user):
    outsider = make_user(name="Outsider", email="outside@srh.de")
    gid, _, _ = _group_with_member(client, app, make_user)
    client.get("/auth/logout")
    login(client, email=outsider.email)
    assert client.get(f"/groups/{gid}/shopping/").status_code == 403
    assert client.post(f"/groups/{gid}/shopping/add", data=_item_data()).status_code == 403


def test_only_creator_or_admin_can_delete_item(client, app, make_user):
    gid, _, _ = _group_with_member(client, app, make_user)
    client.post(f"/groups/{gid}/shopping/add", data=_item_data())
    with app.app_context():
        item_id = ShoppingItem.query.one().id
    client.get("/auth/logout")
    login(client, email="kavin@srh.de")
    assert client.post(f"/groups/{gid}/shopping/{item_id}/delete").status_code == 403
    client.get("/auth/logout")
    login(client)
    response = client.post(
        f"/groups/{gid}/shopping/{item_id}/delete", follow_redirects=True
    )
    assert b"removed from the shopping list" in response.data
    with app.app_context():
        assert ShoppingItem.query.count() == 0


def test_clear_completed_keeps_needed_items(client, app, make_user):
    gid, _, _ = _group_with_member(client, app, make_user)
    client.post(f"/groups/{gid}/shopping/add", data=_item_data(name="Milk"))
    client.post(f"/groups/{gid}/shopping/add", data=_item_data(name="Bread"))
    with app.app_context():
        milk_id = ShoppingItem.query.filter_by(name="Milk").one().id
    client.post(f"/groups/{gid}/shopping/{milk_id}/toggle")
    response = client.post(
        f"/groups/{gid}/shopping/completed/clear", follow_redirects=True
    )
    assert b"Cleared 1 purchased item" in response.data
    assert b"Bread" in response.data
    with app.app_context():
        assert ShoppingItem.query.filter_by(name="Milk").count() == 0
        assert ShoppingItem.query.filter_by(name="Bread").count() == 1
