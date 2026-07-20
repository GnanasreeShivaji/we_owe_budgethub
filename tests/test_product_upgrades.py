"""Acceptance coverage for US-16 through US-23 upgrades."""

import json
from datetime import datetime
from decimal import Decimal

from app import db
from app.models import (Expense, Group, MonthlyBudget, PaymentReminder, ReceiptItem,
                        RecurringBill, RecurringBillOccurrence, ShoppingItem, User)
from tests.conftest import login, register


def test_preferences_save_currency_timezone_and_notifications(client, app):
    register(client)
    response = client.post("/settings/", data={
        "timezone": "Asia/Kolkata", "currency": "INR",
        "notify_immediate": "y",
    }, follow_redirects=True)
    assert b"Preferences saved" in response.data
    assert "₹".encode() in client.get("/budget/").data
    with app.app_context():
        user = User.query.one()
        assert user.timezone == "Asia/Kolkata" and user.currency == "INR"
        assert user.notify_immediate is True and user.notify_scheduled is False


def test_currency_change_only_affects_new_records(client, app):
    register(client)
    with app.app_context():
        user = User.query.one()
        db.session.add(MonthlyBudget(user_id=user.id, month="2026-07", currency="EUR",
                                    income_sources="Job: 100.00"))
        db.session.commit()
    client.post("/settings/", data={
        "timezone": "Europe/Berlin", "currency": "INR",
        "notify_immediate": "y", "notify_scheduled": "y",
    })
    old_month = client.get("/budget/?month=2026-07")
    assert "€100.00".encode() in old_month.data
    assert "₹100.00".encode() not in old_month.data
    client.post("/groups/create", data={"name": "New INR group", "description": ""})
    with app.app_context():
        assert Group.query.filter_by(name="New INR group").one().currency == "INR"


def test_first_group_expense_can_choose_currency_then_locks_it(client, app):
    register(client)
    client.post("/groups/create", data={"name": "Travel", "description": ""})
    with app.app_context():
        group = Group.query.one()
        group_id, owner_id = group.id, group.owner_id
    page = client.get(f"/groups/{group_id}/expenses/new")
    assert b"This sets the currency for this group" in page.data
    payer_script = client.get("/static/js/expense-payers.js")
    assert 'symbols = {EUR: "€", USD: "$", INR: "₹", GBP: "£"}'.encode() in payer_script.data
    assert b"Paid \xe2\x82\xac${paid" not in payer_script.data
    response = client.post(f"/groups/{group_id}/expenses/new", data={
        "title": "Taxi", "amount": "10.00", "currency": "INR",
        "category": "Other expenses", "expense_date": "2026-07-21",
        "split_method": "equal", f"participant_{owner_id}": "1",
    }, follow_redirects=True)
    assert b"Expense saved successfully" in response.data
    with app.app_context():
        assert Group.query.one().currency == "INR"
        assert Expense.query.one().currency == "INR"
    locked = client.get(f"/groups/{group_id}/expenses/new")
    assert b"group currency is locked" in locked.data


def test_account_export_requires_login_and_contains_user_data(client, app):
    assert client.get("/settings/export.json").status_code == 302
    register(client)
    response = client.get("/settings/export.json")
    payload = json.loads(response.data)
    assert response.headers["Content-Disposition"].endswith("we-owe-account-export.json")
    assert payload["profile"]["email"] == "loki@srh.de"
    assert "personal_expenses" in payload and "settlements" in payload


def test_account_deletion_requires_password_and_anonymizes(client, app):
    register(client)
    wrong = client.post("/settings/delete", data={"password": "wrong"}, follow_redirects=True)
    assert b"correct password" in wrong.data
    deleted = client.post("/settings/delete", data={"password": "Str0ng!pw"}, follow_redirects=True)
    assert b"account was deleted" in deleted.data
    with app.app_context():
        user = User.query.one()
        assert user.account_deleted is True and user.name == "Deleted user"
        assert user.email.endswith("@invalid.local")


def _shopping_group(client, app, make_user):
    friend = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Shopping Flat", "description": ""})
    with app.app_context():
        group = Group.query.one(); group_id, owner_id = group.id, group.owner_id
    client.post(f"/groups/{group_id}/invite", data={"email": friend.email, "role": "member"})
    return group_id, owner_id, friend.id


def test_purchased_shopping_items_convert_once_to_equal_expense(client, app, make_user):
    group_id, owner_id, friend_id = _shopping_group(client, app, make_user)
    client.post(f"/groups/{group_id}/shopping/add", data={
        "name": "Milk", "quantity": "2", "category": "Groceries",
        "note": "", "assigned_to": 0, "price": "3.60",
    })
    with app.app_context(): item_id = ShoppingItem.query.one().id
    client.post(f"/groups/{group_id}/shopping/{item_id}/toggle")
    response = client.post(f"/groups/{group_id}/shopping/completed/to-expense", follow_redirects=True)
    assert b"Created a 3.60 group expense" in response.data
    with app.app_context():
        expense = Expense.query.one()
        assert expense.amount == Decimal("3.60")
        assert {split.user_id: split.amount for split in expense.splits} == {
            owner_id: Decimal("1.80"), friend_id: Decimal("1.80")}
        assert ShoppingItem.query.one().converted_expense_id == expense.id
    again = client.post(f"/groups/{group_id}/shopping/completed/to-expense", follow_redirects=True)
    assert b"Add prices" in again.data
    with app.app_context(): assert Expense.query.count() == 1


def test_deleting_generated_expense_releases_shopping_items(client, app, make_user):
    group_id, owner_id, _ = _shopping_group(client, app, make_user)
    client.post(f"/groups/{group_id}/shopping/add", data={
        "name": "Bread", "quantity": "1", "category": "Groceries",
        "note": "", "assigned_to": 0, "price": "2.50",
    })
    with app.app_context():
        item_id = ShoppingItem.query.one().id
    client.post(f"/groups/{group_id}/shopping/{item_id}/toggle")
    client.post(f"/groups/{group_id}/shopping/completed/to-expense")
    with app.app_context():
        expense_id = Expense.query.one().id
    client.post(f"/groups/{group_id}/expenses/{expense_id}/delete")
    page = client.get(f"/groups/{group_id}/shopping/")
    assert b"Create expense" in page.data
    assert b"expense created" not in page.data
    with app.app_context():
        assert ShoppingItem.query.one().converted_expense_id is None


def test_reviewed_receipt_quantity_and_unit_price_are_stored(client, app, make_user):
    group_id, owner_id, friend_id = _shopping_group(client, app, make_user)
    response = client.post(f"/groups/{group_id}/expenses/new", data={
        "title": "Lidl", "amount": "1.38", "category": "Groceries",
        "expense_date": "2026-07-21", "notes": "", "split_method": "receipt",
        "receipt_item_count": "1", "receipt_item_name_0": "Croissant Nuss",
        "receipt_item_quantity_0": "2", "receipt_item_unit_price_0": "0.69",
        f"receipt_item_0_member_{owner_id}": "1",
    }, follow_redirects=True)
    assert b"Expense saved successfully" in response.data
    with app.app_context():
        item = ReceiptItem.query.one()
        assert item.quantity == 2 and item.unit_price == Decimal("0.69")
        assert item.price == Decimal("1.38")


def test_custom_reminder_time_uses_sender_timezone(client, app, make_user):
    group_id, owner_id, friend_id = _shopping_group(client, app, make_user)
    # Create debt: owner pays, both share.
    client.post(f"/groups/{group_id}/expenses/new", data={
        "title": "Dinner", "amount": "10", "category": "Eating out",
        "expense_date": "2026-07-21", "notes": "", "split_method": "equal",
        f"participant_{owner_id}": "1", f"participant_{friend_id}": "1",
    })
    with app.app_context():
        owner = db.session.get(User, owner_id); owner.timezone = "Asia/Kolkata"; db.session.commit()
    client.post(f"/groups/{group_id}/reminders/create", data={
        "recipient_id": friend_id, "amount": "5", "timing": "custom",
        "scheduled_for": "2027-01-10T10:00", "message": "",
    })
    with app.app_context():
        reminder = PaymentReminder.query.one()
        stored = reminder.scheduled_for.replace(tzinfo=None)
        assert stored == datetime(2027, 1, 10, 4, 30)


def test_recipient_notification_preference_skips_immediate_email(client, app, make_user, monkeypatch):
    group_id, owner_id, friend_id = _shopping_group(client, app, make_user)
    client.post(f"/groups/{group_id}/expenses/new", data={
        "title": "Dinner", "amount": "10", "category": "Eating out",
        "expense_date": "2026-07-21", "notes": "", "split_method": "equal",
        f"participant_{owner_id}": "1", f"participant_{friend_id}": "1",
    })
    with app.app_context():
        friend = db.session.get(User, friend_id); friend.notify_immediate = False; db.session.commit()
    called = []
    monkeypatch.setattr("app.reminders.routes.send_email", lambda *args: called.append(args))
    response = client.post(f"/groups/{group_id}/reminders/create", data={
        "recipient_id": friend_id, "amount": "5", "timing": "now", "message": "",
    }, follow_redirects=True)
    assert b"disabled immediate emails" in response.data
    assert called == []
    with app.app_context():
        reminder = PaymentReminder.query.one()
        assert reminder.status == PaymentReminder.CANCELLED
        assert reminder.delivery_channel == "notification preference"


def test_login_rate_limit_and_security_headers(client, app, make_user):
    make_user(name="Loki", email="loki@srh.de")
    for _ in range(5):
        response = client.post("/auth/login", data={
            "email": "loki@srh.de", "password": "Wrong!123"
        })
        assert response.status_code == 200
    limited = client.post("/auth/login", data={
        "email": "loki@srh.de", "password": "Wrong!123"
    })
    assert limited.status_code == 429
    assert b"Too many login attempts" in limited.data
    assert limited.headers["X-Content-Type-Options"] == "nosniff"
    assert limited.headers["X-Frame-Options"] == "DENY"
