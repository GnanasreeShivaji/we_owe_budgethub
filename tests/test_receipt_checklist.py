"""Receipt OCR parsing and product-level member allocation tests."""

from decimal import Decimal

from app.models import Expense, ExpenseSplit, Group, ReceiptItem
from app.services.receipt_ocr import parse_receipt_text
from tests.conftest import register


LIDL_TEXT = """
Borek Spinat 0,75 A
Croissant Wien. 0,99 A
Croissant Nuss @,69 x 2 1,38 A
Zu zahlen 3,12
Kreditkarte 3,12
"""


def test_lidl_receipt_parser_preserves_editable_quantity_items():
    items = parse_receipt_text(LIDL_TEXT)
    assert [(item["name"], item["price"]) for item in items] == [
        ("Borek Spinat", Decimal("0.75")),
        ("Croissant Wien", Decimal("0.99")),
        ("Croissant Nuss", Decimal("1.38")),
    ]
    assert items[2]["quantity"] == 2
    assert items[2]["unit_price"] == Decimal("0.69")
    assert sum(item["price"] for item in items) == Decimal("3.12")


def test_quantity_total_repairs_misread_unit_price():
    items = parse_receipt_text("Croissant Nuss 6,69 x 2 1,38 A\nZu zahlen 1,38")
    assert items == [{"name": "Croissant Nuss", "quantity": 2,
                      "unit_price": Decimal("0.69"), "price": Decimal("1.38")}]


def test_receipt_checklist_calculates_splits_from_selected_products(client, app, make_user):
    friend = make_user(name="Kavin", email="kavin@srh.de")
    register(client)
    client.post("/groups/create", data={"name": "Friends", "description": ""})
    with app.app_context():
        group = Group.query.one()
        gid, owner_id, friend_id = group.id, group.owner_id, friend.id
    client.post(f"/groups/{gid}/invite", data={"email": friend.email, "role": "member"})

    data = {
        "title": "Lidl with friends", "amount": "3.12", "category": "Eating out",
        "expense_date": "2026-07-18", "notes": "Receipt checklist",
        "split_method": "receipt", "receipt_item_count": "4",
        "receipt_item_name_0": "Borek Spinat", "receipt_item_price_0": "0.75",
        f"receipt_item_0_member_{owner_id}": "1",
        "receipt_item_name_1": "Croissant Wien", "receipt_item_price_1": "0.99",
        f"receipt_item_1_member_{friend_id}": "1",
        "receipt_item_name_2": "Croissant Nuss", "receipt_item_price_2": "0.69",
        f"receipt_item_2_member_{owner_id}": "1",
        "receipt_item_name_3": "Croissant Nuss", "receipt_item_price_3": "0.69",
        f"receipt_item_3_member_{friend_id}": "1",
    }
    response = client.post(f"/groups/{gid}/expenses/new", data=data, follow_redirects=True)
    assert b"Expense saved successfully" in response.data
    assert b"Receipt item checklist" in response.data
    assert b"Borek Spinat" in response.data
    with app.app_context():
        assert ReceiptItem.query.count() == 4
        splits = {split.user_id: Decimal(split.amount) for split in ExpenseSplit.query.all()}
        assert splits[owner_id] == Decimal("1.44")
        assert splits[friend_id] == Decimal("1.68")
        assert Expense.query.one().split_method == "receipt"


def test_receipt_item_requires_a_selected_member(client, app):
    register(client)
    client.post("/groups/create", data={"name": "Friends", "description": ""})
    with app.app_context():
        gid = Group.query.one().id
    response = client.post(f"/groups/{gid}/expenses/new", data={
        "title": "Lidl", "amount": "0.75", "category": "Eating out",
        "expense_date": "2026-07-18", "split_method": "receipt",
        "receipt_item_count": "1", "receipt_item_name_0": "Borek",
        "receipt_item_price_0": "0.75",
    }, follow_redirects=True)
    assert b"Choose who had Borek" in response.data
    with app.app_context():
        assert Expense.query.count() == 0
