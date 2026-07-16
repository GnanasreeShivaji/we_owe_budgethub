"""US-01: User Registration & Login.

Covers every item on the Trello checklist for US-01:
registration form, field validation, password rules, confirmation email,
login form, credential authentication, invalid-login handling, password reset.
"""
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..models import Invitation, Membership, User
from ..services.email import generate_token, send_email, verify_token
from .forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

CONFIRM_SALT = "email-confirm"
RESET_SALT = "password-reset"


def _send_confirmation(user: User) -> None:
    token = generate_token(user.email, salt=CONFIRM_SALT)
    link = url_for("auth.confirm_email", token=token, _external=True)
    send_email(
        user.email,
        "Confirm your WE_OWE account",
        f"Hi {user.name},\n\nConfirm your email to activate your account:\n{link}\n\n"
        "This link expires in 24 hours.",
    )


def _claim_pending_invitations(user: User) -> None:
    """Turn any invites addressed to this email into real memberships."""
    pending = Invitation.query.filter_by(email=user.email, status=Invitation.PENDING).all()
    for inv in pending:
        if not inv.group.has_member(user):
            db.session.add(Membership(user_id=user.id, group_id=inv.group_id, role=inv.role))
        inv.status = Invitation.ACCEPTED
    if pending:
        db.session.commit()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("groups.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        # Prevent duplicate email registrations (US-01 acceptance criterion)
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists. Try logging in.", "error")
            return render_template("auth/register.html", form=form)

        user = User(name=form.name.data.strip(), email=email)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        _claim_pending_invitations(user)
        _send_confirmation(user)

        flash("Account created. We've emailed you a confirmation link.", "success")
        # Log the user straight in so they land on the dashboard
        login_user(user)
        return redirect(url_for("groups.dashboard"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/confirm/<token>")
def confirm_email(token):
    email = verify_token(token, salt=CONFIRM_SALT, max_age=current_app.config["CONFIRM_TOKEN_MAX_AGE"])
    if not email:
        flash("That confirmation link is invalid or has expired.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first_or_404()
    if user.is_confirmed:
        flash("Your email is already confirmed.", "info")
    else:
        user.is_confirmed = True
        db.session.commit()
        flash("Email confirmed. You're all set.", "success")
    return redirect(url_for("groups.dashboard") if current_user.is_authenticated else url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("groups.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("This email is not registered. Please sign up to log in.", "error")
            return render_template("auth/login.html", form=form)

        if not user.check_password(form.password.data):
            flash("Incorrect password. Please try again.", "error")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember.data)
        if not user.is_confirmed:
            flash("Reminder: please confirm your email from the link we sent.", "info")

        # Redirect to the originally requested page, else the dashboard
        next_page = request.args.get("next")
        if not next_page or not next_page.startswith("/"):
            next_page = url_for("groups.dashboard")
        return redirect(next_page)

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_token(user.email, salt=RESET_SALT)
            link = url_for("auth.reset_password", token=token, _external=True)
            send_email(
                user.email,
                "Reset your WE_OWE password",
                f"Hi {user.name},\n\nReset your password here (expires in 1 hour):\n{link}\n\n"
                "If you didn't request this, you can ignore this email.",
            )
        # Always show the same response so nobody can probe which emails exist
        flash("If that email is registered, we've sent a reset link.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = verify_token(token, salt=RESET_SALT, max_age=current_app.config["RESET_TOKEN_MAX_AGE"])
    if not email:
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=email).first_or_404()
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated. You can log in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form, token=token)
