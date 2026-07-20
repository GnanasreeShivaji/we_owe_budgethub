"""Database models for authentication, groups, expenses and budgets.

Group isolation (US-02 acceptance criterion "group expense logs are fully
isolated") is enforced structurally: every group-scoped record carries a
group_id foreign key, and a user only ever sees a group they hold a
Membership row for.
"""
from datetime import datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager


def _utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    timezone = db.Column(db.String(60), default="Europe/Berlin", nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    notify_immediate = db.Column(db.Boolean, default=True, nullable=False)
    notify_scheduled = db.Column(db.Boolean, default=True, nullable=False)
    account_deleted = db.Column(db.Boolean, default=False, nullable=False)

    memberships = db.relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan"
    )
    groups_owned = db.relationship("Group", back_populates="owner")
    expenses_paid = db.relationship("Expense", back_populates="paid_by")
    expense_payments = db.relationship("ExpensePayment", back_populates="user")
    expense_splits = db.relationship("ExpenseSplit", back_populates="user")
    monthly_budgets = db.relationship(
        "MonthlyBudget", back_populates="user", cascade="all, delete-orphan"
    )
    personal_expenses = db.relationship(
        "PersonalExpense", back_populates="user", cascade="all, delete-orphan"
    )
    recurring_bills = db.relationship(
        "RecurringBill", back_populates="user", cascade="all, delete-orphan"
    )
    recurring_bill_occurrences = db.relationship(
        "RecurringBillOccurrence", back_populates="user", cascade="all, delete-orphan"
    )

    # --- password handling (never store plaintext) ---
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @property
    def groups(self):
        """Groups this user can see -- the core of group isolation."""
        return [m.group for m in self.memberships]

    def __repr__(self):
        return f"<User {self.email}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Group(db.Model):
    __tablename__ = "groups"
    __table_args__ = (
        # A user's own group names must be unique (US-02: "unique name").
        db.UniqueConstraint("owner_id", "name", name="uq_owner_group_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), default="")
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    owner = db.relationship("User", back_populates="groups_owned")
    memberships = db.relationship(
        "Membership", back_populates="group", cascade="all, delete-orphan"
    )
    invitations = db.relationship(
        "Invitation", back_populates="group", cascade="all, delete-orphan"
    )
    expenses = db.relationship(
        "Expense", back_populates="group", cascade="all, delete-orphan"
    )
    shopping_items = db.relationship(
        "ShoppingItem", back_populates="group", cascade="all, delete-orphan",
        order_by="ShoppingItem.created_at.desc()",
    )
    payment_reminders = db.relationship(
        "PaymentReminder", back_populates="group", cascade="all, delete-orphan",
        order_by="PaymentReminder.created_at.desc()",
    )
    settlement_transactions = db.relationship(
        "SettlementTransaction", back_populates="group", cascade="all, delete-orphan",
        order_by="SettlementTransaction.created_at.desc()",
    )

    def member_role(self, user):
        for m in self.memberships:
            if m.user_id == user.id:
                return m.role
        return None

    def is_admin(self, user):
        return self.member_role(user) == Membership.ADMIN

    def has_member(self, user):
        return self.member_role(user) is not None

    def __repr__(self):
        return f"<Group {self.name!r} owner={self.owner_id}>"


class Membership(db.Model):
    """Join row between User and Group, carrying the role (US-02: roles)."""

    __tablename__ = "memberships"
    __table_args__ = (
        db.UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )

    ADMIN = "admin"
    MEMBER = "member"
    ROLES = (ADMIN, MEMBER)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    role = db.Column(db.String(20), default=MEMBER, nullable=False)
    joined_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User", back_populates="memberships")
    group = db.relationship("Group", back_populates="memberships")


class Invitation(db.Model):
    """Pending invite for an email that isn't registered yet (US-02: invite)."""

    __tablename__ = "invitations"

    PENDING = "pending"
    ACCEPTED = "accepted"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    role = db.Column(db.String(20), default=Membership.MEMBER, nullable=False)
    status = db.Column(db.String(20), default=PENDING, nullable=False)
    invited_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    group = db.relationship("Group", back_populates="invitations")


class Expense(db.Model):
    """A group expense with an optional securely stored receipt (US-03)."""

    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    paid_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Other")
    expense_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(500), default="")
    receipt_filename = db.Column(db.String(255))
    receipt_original_name = db.Column(db.String(255))
    split_method = db.Column(db.String(20), nullable=False, default="equal")
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    group = db.relationship("Group", back_populates="expenses")
    paid_by = db.relationship("User", back_populates="expenses_paid")
    splits = db.relationship(
        "ExpenseSplit", back_populates="expense", cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "ExpensePayment", back_populates="expense", cascade="all, delete-orphan"
    )
    receipt_items = db.relationship(
        "ReceiptItem", back_populates="expense", cascade="all, delete-orphan",
        order_by="ReceiptItem.id",
    )

    @property
    def amount_value(self) -> Decimal:
        return Decimal(self.amount)


class ExpenseSplit(db.Model):
    """One participant's calculated share of an expense (US-04)."""

    __tablename__ = "expense_splits"
    __table_args__ = (
        db.UniqueConstraint("expense_id", "user_id", name="uq_expense_split_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    input_value = db.Column(db.Numeric(12, 4))

    expense = db.relationship("Expense", back_populates="splits")
    user = db.relationship("User", back_populates="expense_splits")


class ExpensePayment(db.Model):
    """One group member's contribution toward paying an expense."""

    __tablename__ = "expense_payments"
    __table_args__ = (
        db.UniqueConstraint("expense_id", "user_id", name="uq_expense_payment_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(
        db.Integer, db.ForeignKey("expenses.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    expense = db.relationship("Expense", back_populates="payments")
    user = db.relationship("User", back_populates="expense_payments")


class ReceiptItem(db.Model):
    """One product extracted from a receipt, stored at per-unit price."""

    __tablename__ = "receipt_items"

    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(
        db.Integer, db.ForeignKey("expenses.id"), nullable=False, index=True
    )
    name = db.Column(db.String(180), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2))

    expense = db.relationship("Expense", back_populates="receipt_items")
    assignments = db.relationship(
        "ReceiptItemAssignment", back_populates="item", cascade="all, delete-orphan"
    )


class ReceiptItemAssignment(db.Model):
    """A member who consumed an item; multi-member items split equally."""

    __tablename__ = "receipt_item_assignments"
    __table_args__ = (
        db.UniqueConstraint("receipt_item_id", "user_id", name="uq_receipt_item_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    receipt_item_id = db.Column(
        db.Integer, db.ForeignKey("receipt_items.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    item = db.relationship("ReceiptItem", back_populates="assignments")
    user = db.relationship("User")


class MonthlyBudget(db.Model):
    """A user's editable monthly budget plan (US-07)."""

    __tablename__ = "monthly_budgets"
    __table_args__ = (
        db.UniqueConstraint("user_id", "month", name="uq_user_budget_month"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    month = db.Column(db.String(7), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    income_sources = db.Column(db.Text, default="", nullable=False)
    fixed_expenses = db.Column(db.Text, default="", nullable=False)
    savings_target = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    # Legacy column names are retained for database compatibility. The UI
    # labels these as Eating out, Groceries, Rent, Bills and Other expenses.
    food_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    groceries_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    transport_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    utilities_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    entertainment_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    other_budget = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user = db.relationship("User", back_populates="monthly_budgets")


class PersonalExpense(db.Model):
    """A private spending entry used by the monthly budget tracker."""

    __tablename__ = "personal_expenses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    description = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User", back_populates="personal_expenses")


class RecurringBill(db.Model):
    """A fixed monthly cost that is automatically counted in every month."""

    __tablename__ = "recurring_bills"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    bill_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User", back_populates="recurring_bills")
    occurrences = db.relationship(
        "RecurringBillOccurrence", back_populates="bill", cascade="all, delete-orphan"
    )


class RecurringBillOccurrence(db.Model):
    """A recurring bill explicitly confirmed as paid for one month."""

    __tablename__ = "recurring_bill_occurrences"
    __table_args__ = (db.UniqueConstraint("bill_id", "month", name="uq_bill_occurrence_month"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("recurring_bills.id"), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    paid_on = db.Column(db.Date, nullable=False)
    confirmed_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    user = db.relationship("User", back_populates="recurring_bill_occurrences")
    bill = db.relationship("RecurringBill", back_populates="occurrences")


class ShoppingItem(db.Model):
    """A collaborative checklist item belonging to one expense group (US-08)."""

    __tablename__ = "shopping_items"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.String(50), default="1", nullable=False)
    category = db.Column(db.String(50), default="Groceries", nullable=False)
    note = db.Column(db.String(240), default="", nullable=False)
    added_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    is_purchased = db.Column(db.Boolean, default=False, nullable=False)
    purchased_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    purchased_at = db.Column(db.DateTime)
    price = db.Column(db.Numeric(12, 2))
    converted_expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"))

    group = db.relationship("Group", back_populates="shopping_items")
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    purchased_by = db.relationship("User", foreign_keys=[purchased_by_id])
    converted_expense = db.relationship("Expense", foreign_keys=[converted_expense_id])


class PaymentReminder(db.Model):
    """A scheduled and tracked balance reminder for a group debtor (US-09)."""

    __tablename__ = "payment_reminders"

    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    message = db.Column(db.String(500), default="", nullable=False)
    scheduled_for = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(20), default=SCHEDULED, nullable=False, index=True)
    delivery_channel = db.Column(db.String(40))
    delivery_error = db.Column(db.String(500))
    payment_url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    sent_at = db.Column(db.DateTime)

    group = db.relationship("Group", back_populates="payment_reminders")
    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])


class SettlementTransaction(db.Model):
    """A recorded debtor-to-creditor payment with receiver confirmation."""

    __tablename__ = "settlement_transactions"

    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True
    )
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    note = db.Column(db.String(240), default="", nullable=False)
    status = db.Column(db.String(20), default=PENDING, nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    group = db.relationship("Group", back_populates="settlement_transactions")
    from_user = db.relationship("User", foreign_keys=[from_user_id])
    to_user = db.relationship("User", foreign_keys=[to_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_id])
