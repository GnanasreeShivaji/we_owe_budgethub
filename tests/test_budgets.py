"""US-07 monthly budget planner tests."""

from decimal import Decimal

from app import db
from app.budgets.routes import _chart_breakdown
from app.models import Expense, ExpenseSplit, Group, MonthlyBudget, PersonalExpense, RecurringBill
from tests.conftest import register


def _budget_data(**changes):
    data = {
        "month": "2026-07",
        "income_sources": "Student job: 900.00\nFamily support: 300.00",
        "fixed_expenses": "Rent: 450.00\nHealth insurance: 140.00",
        "savings_target": "100.00",
        "food_budget": "100.00",
        "groceries_budget": "160.00",
        "transport_budget": "58.00",
        "utilities_budget": "50.00",
        "entertainment_budget": "40.00",
        "other_budget": "102.00",
    }
    data.update(changes)
    return data


def test_create_and_calculate_monthly_budget(client, app):
    register(client)
    response = client.post("/budget/", data=_budget_data(), follow_redirects=True)
    assert b"Monthly budget saved" in response.data
    assert b"Monthly income" in response.data
    assert "€1200.00".encode() in response.data
    assert "€590.00".encode() in response.data  # 1200 - 510 planned - 100 savings
    with app.app_context():
        assert MonthlyBudget.query.one().month == "2026-07"


def test_adjust_budget_without_creating_duplicate(client, app):
    register(client)
    client.post("/budget/", data=_budget_data())
    client.post("/budget/", data=_budget_data(savings_target="150.00"))
    with app.app_context():
        assert MonthlyBudget.query.count() == 1
        assert MonthlyBudget.query.one().savings_target == Decimal("150.00")


def test_income_line_validation(client, app):
    register(client)
    response = client.post(
        "/budget/", data=_budget_data(income_sources="Student job 900"), follow_redirects=True
    )
    assert b"must look like Name: 100.00" in response.data
    with app.app_context():
        assert MonthlyBudget.query.count() == 0


def test_actual_expense_share_is_compared_by_month(client, app):
    register(client)
    client.post("/groups/create", data={"name": "WG", "description": ""})
    with app.app_context():
        group = Group.query.one()
        expense = Expense(
            group_id=group.id, paid_by_id=group.owner_id, title="Lidl", amount=Decimal("40.00"),
            category="Groceries", expense_date=__import__("datetime").date(2026, 7, 10), split_method="equal",
        )
        expense.splits.append(ExpenseSplit(user_id=group.owner_id, amount=Decimal("20.00"), input_value=1))
        db.session.add(expense)
        db.session.commit()
    response = client.post("/budget/", data=_budget_data(), follow_redirects=True)
    assert b"Spending overview" in response.data
    assert "€20.00".encode() in response.data


def test_personal_spending_updates_actual_and_can_be_deleted(client, app):
    register(client)
    client.post("/budget/", data=_budget_data())
    response = client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Lidl shopping", "amount": "24.50",
        "category": "Groceries", "expense_date": "2026-07-18",
    }, follow_redirects=True)
    assert b"Personal spending recorded" in response.data
    assert b"Lidl shopping" in response.data
    assert "€24.50".encode() in response.data
    with app.app_context():
        entry_id = PersonalExpense.query.one().id
    deleted = client.post(f"/budget/spending/{entry_id}/delete", follow_redirects=True)
    assert b"Personal spending deleted" in deleted.data
    with app.app_context():
        assert PersonalExpense.query.count() == 0


def test_personal_spending_is_private(client, app, make_user):
    other = make_user(name="Other", email="other@srh.de")
    register(client)
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Private purchase", "amount": "12.00",
        "category": "Other expenses", "expense_date": "2026-07-18",
    })
    client.get("/auth/logout")
    from tests.conftest import login
    login(client, email=other.email)
    page = client.get("/budget/?month=2026-07")
    assert b"Private purchase" not in page.data
    with app.app_context():
        entry_id = PersonalExpense.query.one().id
    assert client.post(f"/budget/spending/{entry_id}/delete").status_code == 404


def test_recurring_bill_counts_only_after_monthly_confirmation(client, app):
    register(client)
    response = client.post("/budget/recurring/add", data={
        "month": "2026-07", "bill_type": "Health insurance",
        "description": "TK student insurance", "amount": "145.20",
    }, follow_redirects=True)
    assert b"template added" in response.data
    assert b"TK student insurance" in response.data
    assert "€145.20".encode() in response.data

    august = client.get("/budget/?month=2026-08")
    assert b"TK student insurance" in august.data
    assert "€145.20".encode() in august.data
    with app.app_context():
        bill_id = RecurringBill.query.one().id
    paid = client.post(f"/budget/recurring/{bill_id}/confirm",
                       data={"month": "2026-07"}, follow_redirects=True)
    assert b"confirmed as paid" in paid.data
    assert b"145.20 paid" in paid.data
    august = client.get("/budget/?month=2026-08")
    assert b"0.00 paid" in august.data
    removed = client.post(
        f"/budget/recurring/{bill_id}/delete",
        data={"month": "2026-08"}, follow_redirects=True,
    )
    assert b"Recurring bill removed" in removed.data


def test_split_expense_description_is_visible_in_budget_activity(client, app):
    register(client)
    client.post("/groups/create", data={"name": "WG", "description": ""})
    with app.app_context():
        group = Group.query.one()
        expense = Expense(
            group_id=group.id, paid_by_id=group.owner_id,
            title="Dinner at Mensa", notes="Friday study group",
            amount=Decimal("18.00"), category="Eating out",
            expense_date=__import__("datetime").date(2026, 7, 12), split_method="equal",
        )
        expense.splits.append(ExpenseSplit(
            user_id=group.owner_id, amount=Decimal("9.00"), input_value=1,
        ))
        db.session.add(expense)
        db.session.commit()
    page = client.get("/budget/?month=2026-07")
    assert b"Dinner at Mensa" in page.data
    assert b"Friday study group" in page.data
    assert b"Split in WG" in page.data


def test_category_limit_can_be_edited_inline(client, app):
    register(client)
    client.post("/budget/", data=_budget_data())
    response = client.post(
        "/budget/category/food_budget",
        data={"month": "2026-07", "amount": "75.50"},
        follow_redirects=True,
    )
    assert b"Eating out limit updated" in response.data
    assert "€75.50".encode() in response.data
    with app.app_context():
        assert MonthlyBudget.query.one().food_budget == Decimal("75.50")


def test_delete_budget_keeps_spending_and_recurring_bills(client, app):
    register(client)
    client.post("/budget/", data=_budget_data())
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Mensa lunch", "amount": "6.50",
        "category": "Eating out", "expense_date": "2026-07-18",
    })
    client.post("/budget/recurring/add", data={
        "month": "2026-07", "bill_type": "Mobile phone",
        "description": "Monthly SIM", "amount": "12.00",
    })
    response = client.post("/budget/2026-07/delete", follow_redirects=True)
    assert b"Monthly budget deleted" in response.data
    assert b"Mensa lunch" in response.data
    assert b"Monthly SIM" in response.data
    with app.app_context():
        assert MonthlyBudget.query.count() == 0
        assert PersonalExpense.query.count() == 1
        assert RecurringBill.query.count() == 1


def test_chart_display_percentages_always_total_one_hundred():
    categories = [
        {"name": "Bills", "actual": Decimal("418.00")},
        {"name": "Groceries", "actual": Decimal("3.50")},
        {"name": "Eating out", "actual": Decimal("15.56")},
        {"name": "Other", "actual": Decimal("4.89")},
    ]
    chart = _chart_breakdown(categories, Decimal("441.95"))
    assert sum(item["display_percentage"] for item in chart) == 100


def test_recurring_bill_can_be_edited(client, app):
    register(client)
    client.post("/budget/recurring/add", data={
        "month": "2026-07", "bill_type": "Mobile phone",
        "description": "Old mobile amount", "amount": "30.00",
    })
    with app.app_context():
        bill_id = RecurringBill.query.one().id
    response = client.post(f"/budget/recurring/{bill_id}/edit", data={
        "month": "2026-07", "bill_type": "Health insurance",
        "description": "TK student tariff", "amount": "145.20",
    }, follow_redirects=True)
    assert b"Recurring bill updated" in response.data
    assert b"TK student tariff" in response.data
    with app.app_context():
        bill = RecurringBill.query.one()
        assert bill.bill_type == "Health insurance"
        assert bill.amount == Decimal("145.20")


def test_reset_month_removes_plan_and_personal_spending(client, app):
    register(client)
    client.post("/budget/", data=_budget_data())
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Wrong entry", "amount": "9.00",
        "category": "Other expenses", "expense_date": "2026-07-18",
    })
    response = client.post("/budget/2026-07/reset", follow_redirects=True)
    assert b"Month reset" in response.data
    with app.app_context():
        assert MonthlyBudget.query.count() == 0
        assert PersonalExpense.query.count() == 0


def test_reset_remains_available_after_budget_was_deleted(client):
    register(client)
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Old rent", "amount": "367.00",
        "category": "Rent", "expense_date": "2026-07-01",
    })
    page = client.get("/budget/?month=2026-07")
    assert b"Reset month" in page.data
    assert b"Old rent" in page.data
    reset = client.post("/budget/2026-07/reset", follow_redirects=True)
    assert b"Old rent" not in reset.data


def test_pie_chart_exposes_amounts_in_hover_tooltips(client):
    register(client)
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Supermarket", "amount": "56.25",
        "category": "Groceries", "expense_date": "2026-07-18",
    })
    page = client.get("/budget/?month=2026-07")
    assert b"Groceries: \xe2\x82\xac56.25 spent" in page.data
    assert b"\xe2\x82\xac56.25 spent on Groceries" in page.data


def test_available_balance_does_not_deduct_optional_savings(client):
    register(client)
    client.post("/budget/", data=_budget_data(
        income_sources="Student job: 987.00", savings_target="150.00"
    ))
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Monthly spending", "amount": "880.31",
        "category": "Other expenses", "expense_date": "2026-07-18",
    })
    page = client.get("/budget/?month=2026-07")
    assert b"Available balance" in page.data
    assert "€106.69".encode() in page.data
    assert "€-43.31 left if you save this".encode() in page.data


def test_money_sent_home_has_its_own_budget_and_spending_category(client, app):
    register(client)
    client.post("/budget/", data=_budget_data(entertainment_budget="200.00"))
    response = client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Transfer to family", "amount": "75.00",
        "category": "Money sent home", "expense_date": "2026-07-18",
    }, follow_redirects=True)
    assert b"Money sent home" in response.data
    assert b"Transfer to family" in response.data
    assert b"Money sent home: \xe2\x82\xac75.00 spent" in response.data
    with app.app_context():
        assert PersonalExpense.query.one().category == "Money sent home"


def test_over_budget_usage_is_capped_at_one_hundred_with_overage(client):
    register(client)
    client.post("/budget/", data=_budget_data(utilities_budget="185.00"))
    client.post("/budget/spending/add", data={
        "month": "2026-07", "description": "Bills", "amount": "267.00",
        "category": "Bills", "expense_date": "2026-07-18",
    })
    page = client.get("/budget/?month=2026-07")
    assert b"Bills</strong> has used 100%" in page.data
    assert b"\xe2\x82\xac82.00 over budget" in page.data
    assert b"144%" not in page.data
