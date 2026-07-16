"""US-03 acceptance tests: expense CRUD, validation and receipt uploads."""

from datetime import date
from io import BytesIO
from pathlib import Path

from app import db
from app.models import Expense, Group
from tests.conftest import register


def _group(client, app):
    register(client)
    client.post(
        "/groups/create",
        data={"name": "Flat 4B", "description": "Shared costs"},
        follow_redirects=True,
    )
    with app.app_context():
        return Group.query.filter_by(name="Flat 4B").first().id


def _expense_data(**changes):
    data = {
        "title": "Weekly groceries",
        "amount": "42.50",
        "category": "Groceries",
        "expense_date": "2026-07-16",
        "notes": "Milk and vegetables",
    }
    data.update(changes)
    return data


def test_create_expense_saves_and_displays(client, app):
    gid = _group(client, app)
    response = client.post(
        f"/groups/{gid}/expenses/new", data=_expense_data(), follow_redirects=True
    )

    assert b"Expense saved successfully" in response.data
    assert b"Weekly groceries" in response.data
    assert b"42.50" in response.data
    with app.app_context():
        expense = Expense.query.one()
        assert expense.group_id == gid
        assert expense.expense_date == date(2026, 7, 16)


def test_required_fields_and_positive_amount_are_validated(client, app):
    gid = _group(client, app)
    response = client.post(
        f"/groups/{gid}/expenses/new",
        data=_expense_data(title="", amount="0"),
        follow_redirects=True,
    )

    assert b"This field is required" in response.data
    assert b"Number must be between" in response.data
    with app.app_context():
        assert Expense.query.count() == 0


def test_edit_expense_details(client, app):
    gid = _group(client, app)
    client.post(f"/groups/{gid}/expenses/new", data=_expense_data())
    with app.app_context():
        eid = Expense.query.one().id

    response = client.post(
        f"/groups/{gid}/expenses/{eid}/edit",
        data=_expense_data(title="Dinner", amount="60.00", category="Food"),
        follow_redirects=True,
    )

    assert b"Expense updated successfully" in response.data
    with app.app_context():
        expense = db.session.get(Expense, eid)
        assert expense.title == "Dinner"
        assert float(expense.amount) == 60.0


def test_upload_and_download_receipt(client, app, tmp_path):
    app.config["RECEIPT_UPLOAD_FOLDER"] = str(tmp_path / "receipts")
    gid = _group(client, app)
    data = _expense_data()
    data["receipt"] = (BytesIO(b"fake-png-content"), "receipt.png")
    response = client.post(
        f"/groups/{gid}/expenses/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Receipt" in response.data

    with app.app_context():
        expense = Expense.query.one()
        eid = expense.id
        stored = expense.receipt_filename
        assert expense.receipt_original_name == "receipt.png"
        assert (Path(app.config["RECEIPT_UPLOAD_FOLDER"]) / stored).exists()

    download = client.get(f"/groups/{gid}/expenses/{eid}/receipt")
    assert download.status_code == 200
    assert download.data == b"fake-png-content"


def test_invalid_receipt_type_is_rejected(client, app):
    gid = _group(client, app)
    data = _expense_data()
    data["receipt"] = (BytesIO(b"bad"), "malware.exe")
    response = client.post(
        f"/groups/{gid}/expenses/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Upload an image or PDF receipt" in response.data
    with app.app_context():
        assert Expense.query.count() == 0


def test_delete_expense_and_receipt(client, app, tmp_path):
    app.config["RECEIPT_UPLOAD_FOLDER"] = str(tmp_path / "receipts")
    gid = _group(client, app)
    data = _expense_data(receipt=(BytesIO(b"receipt"), "receipt.pdf"))
    client.post(
        f"/groups/{gid}/expenses/new", data=data, content_type="multipart/form-data"
    )
    with app.app_context():
        expense = Expense.query.one()
        eid, filename = expense.id, expense.receipt_filename

    response = client.post(
        f"/groups/{gid}/expenses/{eid}/delete", follow_redirects=True
    )
    assert b"Expense deleted" in response.data
    with app.app_context():
        assert db.session.get(Expense, eid) is None
    assert not (Path(app.config["RECEIPT_UPLOAD_FOLDER"]) / filename).exists()


def test_non_member_cannot_access_expense(client, app, make_user):
    outsider = make_user(name="Outsider", email="outsider@srh.de")
    gid = _group(client, app)
    client.get("/auth/logout")
    client.post(
        "/auth/login",
        data={"email": outsider.email, "password": "Str0ng!pw"},
        follow_redirects=True,
    )
    assert client.get(f"/groups/{gid}/expenses/new").status_code == 403
