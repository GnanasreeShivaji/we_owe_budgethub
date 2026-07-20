"""US-10 spending summary, charts and CSV export routes."""

import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required

from .service import build_insights, build_report, month_bounds, previous_months
from ..models import MonthlyBudget
from ..services.preferences import CURRENCY_SYMBOLS, symbol_for


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _context():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    try:
        month_bounds(month)
    except ValueError:
        abort(400)
    groups = sorted(current_user.groups, key=lambda group: group.name.lower())
    group_ids = {group.id for group in groups}
    scope = request.args.get("scope", "all")
    allowed = {"all", "personal", *(f"group:{group_id}" for group_id in group_ids)}
    if scope not in allowed:
        abort(403)
    budget = MonthlyBudget.query.filter_by(user_id=current_user.id, month=month).first()
    default_currency = budget.currency if budget else current_user.currency
    currency = request.args.get("currency", default_currency)
    if currency not in CURRENCY_SYMBOLS:
        abort(400)
    return month, scope, groups, group_ids, currency


@reports_bp.route("/")
@login_required
def spending_report():
    month, scope, groups, group_ids, currency = _context()
    report = build_report(current_user.id, month, scope, group_ids, currency=currency)
    comparison_months = previous_months(month, 2)
    current_activity = build_report(
        current_user.id, month, scope, group_ids, include_recurring=False, currency=currency
    )
    previous_activity = build_report(
        current_user.id, comparison_months[0], scope, group_ids,
        include_recurring=False, currency=currency,
    )
    insights = build_insights(report, current_activity, previous_activity,
                              symbol_for(currency))
    trend = []
    for trend_month in previous_months(month):
        # A recurring bill is a current template, not evidence that it was paid
        # in every historical month. Include it for the actively selected month
        # so that month matches the report total, but never fabricate history.
        item = build_report(
            current_user.id, trend_month, scope, group_ids,
            include_recurring=(trend_month == month),
            currency=currency,
        )
        trend.append({"month": trend_month, "label": date.fromisoformat(f"{trend_month}-01").strftime("%b"),
                      "total": float(item["total"])})
    return render_template("reports/spending.html", month=month, scope=scope,
                           groups=groups, report=report, trend=trend,
                           insights=insights, currency=currency,
                           currencies=CURRENCY_SYMBOLS,
                           currency_symbol=symbol_for(currency))


@reports_bp.route("/export.csv")
@login_required
def export_csv():
    month, scope, _groups, group_ids, currency = _context()
    report = build_report(current_user.id, month, scope, group_ids, currency=currency)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Source", "Group", "Description", "Category", f"Amount ({currency})"])
    for row in report["rows"]:
        writer.writerow([row["date"].isoformat(), row["source"], row["group"],
                         row["description"], row["category"], f"{row['amount']:.2f}"])
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", "", "", f"{report['total']:.2f}"])
    filename = f"we-owe-spending-{month}.csv"
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
