"""Data model for Sprint 1 (US-01 Auth, US-02 Groups).

Group isolation (US-02 acceptance criterion "group expense logs are fully
isolated") is enforced structurally: every group-scoped record carries a
group_id foreign key, and a user only ever sees a group they hold a
Membership row for. Sprint 2's Expense table will hang off Group the same way.
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

    memberships = db.relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan"
    )
    groups_owned = db.relationship("Group", back_populates="owner")
    expenses_paid = db.relationship("Expense", back_populates="paid_by")
    expense_splits = db.relationship("ExpenseSplit", back_populates="user")

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
