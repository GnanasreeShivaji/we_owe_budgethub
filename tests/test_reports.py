"""US-10 spending report, chart and export acceptance tests."""

from datetime import date
from decimal import Decimal

from app import db
from app.models import (
    Expense, ExpenseSplit, Group, Membership, MonthlyBudget,
    PersonalExpense, RecurringBill, RecurringBillOccurrence,
)
from tests.conftest import login


def _report_data(app, make_user):
    user = make_user(name="Loki", email="loki@srh.de")
    member = make_user(name="Ananya", email="ananya@srh.de")
    with app.app_context():
        group = Group(name="Flat", owner_id=user.id)
        db.session.add(group); db.session.flush()
        db.session.add_all([
            Membership(user_id=user.id, group_id=group.id, role=Membership.ADMIN),
            Membership(user_id=member.id, group_id=group.id, role=Membership.MEMBER),
        ])
        expense = Expense(group_id=group.id, paid_by_id=member.id, title="Lidl",
                          amount=Decimal("30.00"), category="Groceries",
                          expense_date=date(2026, 7, 12), split_method="exact")
        db.session.add(expense); db.session.flush()
        db.session.add(ExpenseSplit(expense_id=expense.id, user_id=user.id,
                                    amount=Decimal("12.50"), input_value=Decimal("12.50")))
        db.session.add(PersonalExpense(user_id=user.id, description="Coffee",
                                      category="Eating out", amount=Decimal("3.50"),
                                      expense_date=date(2026, 7, 14)))
        bill = RecurringBill(user_id=user.id, bill_type="Mobile recharge",
                             description="SIM", amount=Decimal("10.00"))
        db.session.add(bill); db.session.flush()
        db.session.add(RecurringBillOccurrence(user_id=user.id, bill_id=bill.id,
                                               month="2026-07", amount=Decimal("10.00"),
                                               paid_on=date(2026, 7, 1)))
        db.session.add(MonthlyBudget(user_id=user.id, month="2026-07",
                                    groceries_budget=Decimal("100.00"),
                                    food_budget=Decimal("20.00"),
                                    utilities_budget=Decimal("20.00")))
        db.session.commit()
        return group.id


def test_report_summary_and_charts_match_transaction_rows(client, app, make_user):
    _report_data(app, make_user)
    login(client)
    response = client.get("/reports/?month=2026-07")
    assert response.status_code == 200
    assert b"Your spending report" in response.data
    assert b"\xe2\x82\xac26.00" in response.data
    assert b"These rows add up exactly to" in response.data
    assert b"Lidl" in response.data and b"Coffee" in response.data and b"SIM" in response.data
    assert b'id="category-chart"' in response.data
    assert b'id="trend-chart"' in response.data
    # Recurring templates must not fabricate spending in inactive past months.
    assert b'"label": "Feb", "month": "2026-02", "total": 0.0' in response.data
    # The selected month must equal the report total, including recurring bills.
    assert b'"label": "Jul", "month": "2026-07", "total": 26.0' in response.data
    assert b"What your data is saying" in response.data
    assert b"Totals verified" in response.data
    assert b"Source total" in response.data and b"Groceries is your largest category" in response.data
    assert b"Start with Groceries" in response.data


def test_group_scope_excludes_personal_and_recurring(client, app, make_user):
    group_id = _report_data(app, make_user)
    login(client)
    response = client.get(f"/reports/?month=2026-07&scope=group:{group_id}")
    assert b"\xe2\x82\xac12.50" in response.data
    assert b"Lidl" in response.data
    assert b"Coffee" not in response.data and b">SIM<" not in response.data


def test_report_never_adds_different_currencies_together(client, app, make_user):
    _report_data(app, make_user)
    with app.app_context():
        user = db.session.query(PersonalExpense.user_id).first()[0]
        db.session.add(PersonalExpense(user_id=user, description="Rupee purchase",
                                      category="Other", amount=Decimal("500.00"),
                                      currency="INR", expense_date=date(2026, 7, 20)))
        db.session.commit()
    login(client)
    eur = client.get("/reports/?month=2026-07&currency=EUR")
    inr = client.get("/reports/?month=2026-07&currency=INR")
    assert b"Rupee purchase" not in eur.data and b"\xe2\x82\xac26.00" in eur.data
    assert b"Rupee purchase" in inr.data and "₹500.00".encode() in inr.data


def test_csv_export_rows_and_verified_total(client, app, make_user):
    _report_data(app, make_user)
    login(client)
    response = client.get("/reports/export.csv?month=2026-07")
    text = response.data.decode("utf-8-sig")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="we-owe-spending-2026-07.csv"'
    assert "Lidl,Groceries,12.50" in text
    assert "Coffee,Eating out,3.50" in text
    assert "TOTAL,,,,,26.00" in text


def test_report_rejects_group_outside_membership(client, app, make_user):
    _report_data(app, make_user)
    outsider = make_user(name="Outsider", email="outside@srh.de")
    with app.app_context():
        other = Group(name="Private", owner_id=outsider.id)
        db.session.add(other); db.session.flush()
        db.session.add(Membership(user_id=outsider.id, group_id=other.id, role=Membership.ADMIN))
        db.session.commit(); other_id = other.id
    login(client)
    assert client.get(f"/reports/?month=2026-07&scope=group:{other_id}").status_code == 403


def test_report_requires_login(client):
    response = client.get("/reports/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_empty_month_does_not_invent_insights(client, app, make_user):
    make_user(name="Loki", email="loki@srh.de")
    login(client)
    response = client.get("/reports/?month=2025-01")
    assert response.status_code == 200
    assert b"Not enough saved data for insights" in response.data
    assert b"Recommendations will appear only after real transactions exist" in response.data
    assert b"Largest category" in response.data and b"No spending" in response.data
