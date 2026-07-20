"""Balance-aware payment reminder scheduling, delivery and tracking."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from .. import db
from ..models import Group, PaymentReminder
from ..services.balances import calculate_group_balances
from ..services.email import send_email
from .forms import PaymentReminderForm
from ..services.preferences import symbol_for, user_zone


reminders_bp = Blueprint(
    "reminders", __name__, url_prefix="/groups/<int:group_id>/reminders"
)


def _group_for_member(group_id):
    group = db.session.get(Group, group_id) or abort(404)
    if not group.has_member(current_user):
        abort(403)
    return group


def _reminder_in_group(group, reminder_id):
    return PaymentReminder.query.filter_by(id=reminder_id, group_id=group.id).first_or_404()


def _debts(group):
    return {
        balance["user"].id: -Decimal(balance["net"])
        for balance in calculate_group_balances(group) if balance["net"] < 0
    }


def _schedule_for(form, user):
    now = datetime.now(timezone.utc)
    if form.timing.data == "now":
        return now
    if form.timing.data == "tomorrow":
        return now + timedelta(days=1)
    if form.timing.data == "three_days":
        return now + timedelta(days=3)
    if form.timing.data == "custom" and form.scheduled_for.data:
        custom = form.scheduled_for.data
        if custom.tzinfo is None:
            custom = custom.replace(tzinfo=user_zone(user))
        return custom.astimezone(timezone.utc)
    raise ValueError("Choose a valid reminder date and time.")


def _deliver(reminder):
    symbol = symbol_for(reminder.currency)
    body = (
        f"Hi {reminder.recipient.name},\n\n"
        f"{reminder.sender.name} sent you a payment reminder for "
        f"{symbol}{Decimal(reminder.amount):.2f} in '{reminder.group.name}'.\n"
    )
    if reminder.message:
        body += f"\nMessage: {reminder.message}\n"
    body += f"\nReview the group balance and payment plan:\n{reminder.payment_url}\n"
    try:
        delivered = send_email(
            reminder.recipient.email,
            f"Payment reminder · {reminder.group.name} · {symbol}{Decimal(reminder.amount):.2f}",
            body,
        )
        reminder.status = PaymentReminder.SENT
        reminder.sent_at = datetime.now(timezone.utc)
        reminder.delivery_channel = "email" if delivered else "local outbox"
        reminder.delivery_error = None
    except RuntimeError as error:
        reminder.status = PaymentReminder.FAILED
        reminder.delivery_error = str(error)[:500]
    db.session.commit()
    return reminder.status == PaymentReminder.SENT


def dispatch_due_reminders(now=None, group_id=None):
    """Deliver scheduled reminders that are due; suitable for cron/Flask CLI."""
    now = now or datetime.now(timezone.utc)
    query = PaymentReminder.query.filter(
        PaymentReminder.status == PaymentReminder.SCHEDULED,
        PaymentReminder.scheduled_for <= now,
    )
    if group_id is not None:
        query = query.filter(PaymentReminder.group_id == group_id)
    processed = 0
    for reminder in query.all():
        if not reminder.recipient.notify_scheduled:
            reminder.status = PaymentReminder.CANCELLED
            reminder.delivery_channel = "notification preference"
            reminder.delivery_error = "Recipient disabled scheduled reminder emails."
            db.session.commit()
            processed += 1
            continue
        current_debt = _debts(reminder.group).get(reminder.recipient_id, Decimal("0.00"))
        if current_debt <= 0:
            reminder.status = PaymentReminder.CANCELLED
            reminder.delivery_error = "Automatically cancelled because this balance is settled."
            db.session.commit()
        else:
            if Decimal(reminder.amount) > current_debt:
                reminder.amount = current_debt
            _deliver(reminder)
        processed += 1
    return processed


@reminders_bp.route("/")
@login_required
def view_reminders(group_id):
    group = _group_for_member(group_id)
    debts = _debts(group)
    form = PaymentReminderForm()
    form.recipient_id.choices = [
        (membership.user_id, f"{membership.user.name} · owes {symbol_for(group.currency)}{debts[membership.user_id]:.2f}")
        for membership in group.memberships if membership.user_id in debts
    ]
    reminders = list(group.payment_reminders)
    return render_template(
        "reminders/index.html", group=group, form=form, debts=debts,
        reminders=reminders, now=datetime.now(timezone.utc),
        pending=sum(1 for item in reminders if item.status == PaymentReminder.SCHEDULED),
        sent=sum(1 for item in reminders if item.status == PaymentReminder.SENT),
        currency_symbol=symbol_for(group.currency),
    )


@reminders_bp.route("/create", methods=["POST"])
@login_required
def create_reminder(group_id):
    group = _group_for_member(group_id)
    debts = _debts(group)
    form = PaymentReminderForm()
    form.recipient_id.choices = [(user_id, str(user_id)) for user_id in debts]
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
        return redirect(url_for("reminders.view_reminders", group_id=group.id))
    if form.recipient_id.data not in debts:
        abort(400)
    amount = Decimal(form.amount.data)
    if amount > debts[form.recipient_id.data]:
        flash(f"The reminder cannot exceed the current {symbol_for(group.currency)}{debts[form.recipient_id.data]:.2f} debt.", "error")
        return redirect(url_for("reminders.view_reminders", group_id=group.id))
    try:
        scheduled_for = _schedule_for(form, current_user)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("reminders.view_reminders", group_id=group.id))
    if scheduled_for < datetime.now(timezone.utc) - timedelta(minutes=1):
        flash("The reminder time cannot be in the past.", "error")
        return redirect(url_for("reminders.view_reminders", group_id=group.id))
    reminder = PaymentReminder(
        group_id=group.id, sender_id=current_user.id,
        recipient_id=form.recipient_id.data, amount=amount,
        message=(form.message.data or "").strip(), scheduled_for=scheduled_for,
        payment_url=url_for("groups.view_group", group_id=group.id,
                            _anchor="settlement-plan", _external=True),
        currency=group.currency,
    )
    db.session.add(reminder)
    db.session.commit()
    if form.timing.data == "now":
        if not reminder.recipient.notify_immediate:
            reminder.status = PaymentReminder.CANCELLED
            reminder.delivery_channel = "notification preference"
            reminder.delivery_error = "Recipient disabled immediate reminder emails."
            db.session.commit()
            flash("Reminder recorded, but the recipient disabled immediate emails.", "info")
        elif _deliver(reminder):
            flash("Payment reminder sent and tracked.", "success")
        else:
            flash("The reminder could not be delivered. Check its delivery log.", "error")
    else:
        flash("Payment reminder scheduled.", "success")
    return redirect(url_for("reminders.view_reminders", group_id=group.id))


def _can_manage(group, reminder):
    return reminder.sender_id == current_user.id or group.is_admin(current_user)


@reminders_bp.route("/<int:reminder_id>/send", methods=["POST"])
@login_required
def send_reminder(group_id, reminder_id):
    group = _group_for_member(group_id)
    reminder = _reminder_in_group(group, reminder_id)
    if not _can_manage(group, reminder):
        abort(403)
    if reminder.status not in {PaymentReminder.SCHEDULED, PaymentReminder.FAILED}:
        flash("This reminder has already been processed.", "info")
    elif _deliver(reminder):
        flash("Payment reminder sent and tracked.", "success")
    else:
        flash("Delivery failed. Review the error in the reminder log.", "error")
    return redirect(url_for("reminders.view_reminders", group_id=group.id))


@reminders_bp.route("/<int:reminder_id>/cancel", methods=["POST"])
@login_required
def cancel_reminder(group_id, reminder_id):
    group = _group_for_member(group_id)
    reminder = _reminder_in_group(group, reminder_id)
    if not _can_manage(group, reminder):
        abort(403)
    if reminder.status == PaymentReminder.SCHEDULED:
        reminder.status = PaymentReminder.CANCELLED
        db.session.commit()
        flash("Scheduled reminder cancelled.", "info")
    return redirect(url_for("reminders.view_reminders", group_id=group.id))


@reminders_bp.route("/due/send", methods=["POST"])
@login_required
def send_due(group_id):
    group = _group_for_member(group_id)
    if not group.is_admin(current_user):
        abort(403)
    count = dispatch_due_reminders(group_id=group.id)
    flash(f"Processed {count} due reminder{'s' if count != 1 else ''}.", "info")
    return redirect(url_for("reminders.view_reminders", group_id=group.id))
