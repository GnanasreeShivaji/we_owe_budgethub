"""Build auditable spending reports from saved transaction rows."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from .. import db
from ..budgets.routes import BUDGET_CATEGORIES, EXPENSE_CATEGORY_MAP
from ..models import (Expense, ExpenseSplit, MonthlyBudget, PersonalExpense,
                      RecurringBillOccurrence)


CENT = Decimal("0.01")


def month_bounds(month):
    """Return the first and last dates for a validated YYYY-MM value."""
    try:
        year, month_number = (int(part) for part in month.split("-"))
        start = date(year, month_number, 1)
    except (TypeError, ValueError):
        raise ValueError("Choose a valid report month.")
    return start, date(year, month_number, monthrange(year, month_number)[1])


def previous_months(month, count=6):
    start, _ = month_bounds(month)
    months = []
    year, month_number = start.year, start.month
    for offset in range(count - 1, -1, -1):
        index = year * 12 + month_number - 1 - offset
        months.append(f"{index // 12:04d}-{index % 12 + 1:02d}")
    return months


def _normal_category(category):
    return EXPENSE_CATEGORY_MAP.get(category, "Other expenses")


def spending_rows(user_id, month, scope="all", group_ids=(), include_recurring=True,
                  currency="EUR"):
    """Return report rows. Their sum is the single source for every total/chart."""
    start, end = month_bounds(month)
    rows = []
    allowed_groups = set(group_ids)

    if scope != "personal":
        query = (
            db.session.query(Expense, ExpenseSplit.amount)
            .join(ExpenseSplit, ExpenseSplit.expense_id == Expense.id)
            .filter(
                ExpenseSplit.user_id == user_id,
                Expense.expense_date.between(start, end),
                Expense.currency == currency,
            )
        )
        if scope.startswith("group:"):
            try:
                group_id = int(scope.split(":", 1)[1])
            except ValueError:
                group_id = -1
            if group_id not in allowed_groups:
                return []
            query = query.filter(Expense.group_id == group_id)
        elif allowed_groups:
            query = query.filter(Expense.group_id.in_(allowed_groups))
        else:
            query = query.filter(db.false())
        for expense, share in query.all():
            rows.append({
                "date": expense.expense_date,
                "source": "Group split",
                "group": expense.group.name,
                "description": expense.title,
                "category": _normal_category(expense.category),
                "amount": Decimal(share).quantize(CENT),
            })

    if scope in {"all", "personal"}:
        for entry in PersonalExpense.query.filter(
            PersonalExpense.user_id == user_id,
            PersonalExpense.expense_date.between(start, end),
            PersonalExpense.currency == currency,
        ).all():
            rows.append({
                "date": entry.expense_date,
                "source": "Personal",
                "group": "—",
                "description": entry.description,
                "category": _normal_category(entry.category),
                "amount": Decimal(entry.amount).quantize(CENT),
            })
        if include_recurring:
            for occurrence in RecurringBillOccurrence.query.filter_by(
                    user_id=user_id, month=month, currency=currency).all():
                rows.append({
                    "date": occurrence.paid_on,
                    "source": "Recurring bill",
                    "group": "—",
                    "description": occurrence.bill.description,
                    "category": "Bills",
                    "amount": Decimal(occurrence.amount).quantize(CENT),
                })

    return sorted(rows, key=lambda row: (row["date"], row["description"].lower()), reverse=True)


def build_report(user_id, month, scope="all", group_ids=(), include_recurring=True,
                 currency="EUR"):
    rows = spending_rows(user_id, month, scope, group_ids, include_recurring, currency)
    category_totals = {label: Decimal("0.00") for label, _ in BUDGET_CATEGORIES}
    for row in rows:
        category_totals[row["category"]] += row["amount"]
    categories = [
        {"name": name, "amount": amount.quantize(CENT)}
        for name, amount in category_totals.items() if amount
    ]
    total = sum((row["amount"] for row in rows), Decimal("0.00")).quantize(CENT)
    for item in categories:
        item["percentage"] = float(item["amount"] / total * 100) if total else 0

    budget = MonthlyBudget.query.filter_by(user_id=user_id, month=month).first()
    planned = Decimal("0.00")
    usage = []
    if budget and budget.currency == currency and scope in {"all", "personal"}:
        for name, field in BUDGET_CATEGORIES:
            limit = Decimal(getattr(budget, field) or 0).quantize(CENT)
            actual = category_totals[name].quantize(CENT)
            planned += limit
            usage.append({
                "name": name,
                "planned": limit,
                "actual": actual,
                "percentage": float(actual / limit * 100) if limit else (100.0 if actual else 0.0),
            })
    largest = max(categories, key=lambda item: item["amount"], default=None)
    return {
        "rows": rows,
        "categories": categories,
        "total": total,
        "count": len(rows),
        "average": (total / len(rows)).quantize(CENT) if rows else Decimal("0.00"),
        "largest": largest,
        "planned": planned.quantize(CENT),
        "budget_percentage": float(total / planned * 100) if planned else None,
        "usage": usage,
    }


def build_insights(report, current_activity, previous_activity, symbol="€"):
    """Create deterministic insights whose numbers all come from report rows."""
    source_amounts = {}
    source_counts = {}
    for row in report["rows"]:
        source_amounts[row["source"]] = source_amounts.get(row["source"], Decimal("0.00")) + row["amount"]
        source_counts[row["source"]] = source_counts.get(row["source"], 0) + 1
    sources = [
        {"name": name, "amount": amount.quantize(CENT), "count": source_counts[name]}
        for name, amount in sorted(source_amounts.items())
    ]
    source_total = sum((item["amount"] for item in sources), Decimal("0.00")).quantize(CENT)

    if not report["rows"]:
        return {
            "sources": [], "source_total": Decimal("0.00"), "verified": True,
            "trends": [], "actions": [], "has_data": False,
        }

    trends = []
    if report["largest"]:
        trends.append({
            "kind": "category",
            "title": f"{report['largest']['name']} is your largest category",
            "detail": f"{symbol}{report['largest']['amount']:.2f}, or {report['largest']['percentage']:.0f}% of this report.",
        })

    over_budget = [item for item in report["usage"] if item["planned"] and item["actual"] > item["planned"]]
    near_budget = [item for item in report["usage"] if item["planned"] and 70 <= item["percentage"] <= 100]
    if over_budget:
        item = max(over_budget, key=lambda value: value["actual"] - value["planned"])
        trends.append({
            "kind": "alert", "title": f"{item['name']} is over its limit",
            "detail": f"{symbol}{item['actual'] - item['planned']:.2f} above the {symbol}{item['planned']:.2f} plan.",
        })
    elif near_budget:
        item = max(near_budget, key=lambda value: value["percentage"])
        trends.append({
            "kind": "watch", "title": f"{item['name']} is nearing its limit",
            "detail": f"{item['percentage']:.0f}% used, with {symbol}{item['planned'] - item['actual']:.2f} remaining.",
        })

    if previous_activity["count"]:
        change = current_activity["total"] - previous_activity["total"]
        percentage = abs(change / previous_activity["total"] * 100) if previous_activity["total"] else Decimal("0")
        direction = "higher" if change > 0 else "lower" if change < 0 else "the same as"
        trends.append({
            "kind": "trend", "title": f"Saved activity is {direction} last month",
            "detail": f"{symbol}{current_activity['total']:.2f} versus {symbol}{previous_activity['total']:.2f} ({percentage:.0f}% {'change' if change else 'difference'}).",
        })

    actions = []
    if over_budget:
        for item in sorted(over_budget, key=lambda value: value["actual"] - value["planned"], reverse=True)[:2]:
            actions.append({
                "title": f"Review {item['name']}",
                "detail": f"Reduce future spending by {symbol}{item['actual'] - item['planned']:.2f} to return to this month's limit.",
            })
    flexible = [item for item in report["categories"] if item["name"] not in {"Rent", "Bills"}]
    if flexible:
        item = max(flexible, key=lambda value: value["amount"])
        saving = (item["amount"] * Decimal("0.10")).quantize(CENT)
        if saving:
            actions.append({
                "title": f"Start with {item['name']}",
                "detail": f"A 10% reduction in this category would keep {symbol}{saving:.2f} available.",
            })
    if not actions:
        actions.append({
            "title": "Keep recording transactions",
            "detail": "Your saved data does not show an over-budget category that needs action.",
        })

    return {
        "sources": sources, "source_total": source_total,
        "verified": source_total == report["total"], "trends": trends[:3],
        "actions": actions[:3], "has_data": True,
    }
