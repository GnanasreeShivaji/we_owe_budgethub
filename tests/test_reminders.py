"""US-09 payment reminder scheduling, delivery and tracking tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import db
from app.models import Group, PaymentReminder
from app.reminders.routes import dispatch_due_reminders
from tests.conftest import login, register


def _group_with_debt(client, app, make_user):
    debtor = make_user(name="Ananya", email="ananya@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Reminder Team", "description": ""})
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


def _reminder_data(recipient_id, **changes):
    data = {
        "recipient_id": str(recipient_id), "amount": "6.00", "timing": "tomorrow",
        "scheduled_for": "", "message": "Please settle when you can.",
    }
    data.update(changes)
    return data


def test_reminder_center_targets_only_members_who_owe(client, app, make_user):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    page = client.get(f"/groups/{gid}/reminders/")
    assert b"Ananya" in page.data
    assert b"owes \xe2\x82\xac6.00" in page.data
    assert b"Loki \xc2\xb7 owes" not in page.data


def test_send_now_delivers_content_payment_link_and_tracks_status(
    client, app, make_user, monkeypatch
):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    delivered = []
    monkeypatch.setattr(
        "app.reminders.routes.send_email",
        lambda to, subject, body: delivered.append((to, subject, body)) or True,
    )
    response = client.post(f"/groups/{gid}/reminders/create", data=_reminder_data(
        debtor_id, timing="now"
    ), follow_redirects=True)
    assert b"Payment reminder sent and tracked" in response.data
    assert delivered[0][0] == "ananya@srh.de"
    assert "€6.00" in delivered[0][1]
    assert "Please settle when you can" in delivered[0][2]
    assert f"/groups/{gid}#settlement-plan" in delivered[0][2]
    with app.app_context():
        reminder = PaymentReminder.query.one()
        assert reminder.status == PaymentReminder.SENT
        assert reminder.delivery_channel == "email"
        assert reminder.sent_at is not None


def test_reminder_cannot_exceed_current_debt(client, app, make_user):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    response = client.post(f"/groups/{gid}/reminders/create", data=_reminder_data(
        debtor_id, amount="20.00"
    ), follow_redirects=True)
    assert b"cannot exceed the current \xe2\x82\xac6.00 debt" in response.data
    with app.app_context():
        assert PaymentReminder.query.count() == 0


def test_schedule_and_cancel_reminder(client, app, make_user):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    scheduled = client.post(
        f"/groups/{gid}/reminders/create", data=_reminder_data(debtor_id),
        follow_redirects=True,
    )
    assert b"Payment reminder scheduled" in scheduled.data
    with app.app_context():
        reminder = PaymentReminder.query.one()
        reminder_id = reminder.id
        assert reminder.status == PaymentReminder.SCHEDULED
        assert reminder.scheduled_for > datetime.now(timezone.utc).replace(tzinfo=None)
    cancelled = client.post(
        f"/groups/{gid}/reminders/{reminder_id}/cancel", follow_redirects=True
    )
    assert b"Scheduled reminder cancelled" in cancelled.data


def test_due_dispatch_delivers_scheduled_reminder(client, app, make_user, monkeypatch):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    client.post(f"/groups/{gid}/reminders/create", data=_reminder_data(debtor_id))
    calls = []
    monkeypatch.setattr(
        "app.reminders.routes.send_email",
        lambda to, subject, body: calls.append(to) or True,
    )
    with app.app_context():
        reminder = PaymentReminder.query.one()
        reminder.scheduled_for = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
        assert dispatch_due_reminders() == 1
        assert PaymentReminder.query.one().status == PaymentReminder.SENT
    assert calls == ["ananya@srh.de"]


def test_delivery_failure_is_logged(client, app, make_user, monkeypatch):
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    monkeypatch.setattr(
        "app.reminders.routes.send_email",
        lambda *args: (_ for _ in ()).throw(RuntimeError("SMTP unavailable")),
    )
    response = client.post(f"/groups/{gid}/reminders/create", data=_reminder_data(
        debtor_id, timing="now"
    ), follow_redirects=True)
    assert b"could not be delivered" in response.data
    assert b"SMTP unavailable" in response.data
    with app.app_context():
        reminder = PaymentReminder.query.one()
        assert reminder.status == PaymentReminder.FAILED
        assert reminder.delivery_error == "SMTP unavailable"


def test_non_member_cannot_access_or_create_reminders(client, app, make_user):
    outsider = make_user(name="Outside", email="outside@srh.de")
    gid, _, debtor_id = _group_with_debt(client, app, make_user)
    client.get("/auth/logout")
    login(client, email=outsider.email)
    assert client.get(f"/groups/{gid}/reminders/").status_code == 403
    assert client.post(
        f"/groups/{gid}/reminders/create", data=_reminder_data(debtor_id)
    ).status_code == 403
