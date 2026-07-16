"""Auth forms + validators (US-01: email format & password strength checks)."""
import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
)

# Password policy: >= 8 chars, with an upper, lower, digit and special char.
_SPECIAL = r"!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~"


def strong_password(form, field):
    pw = field.data or ""
    problems = []
    if len(pw) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", pw):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", pw):
        problems.append("a lowercase letter")
    if not re.search(r"\d", pw):
        problems.append("a number")
    if not re.search(f"[{_SPECIAL}]", pw):
        problems.append("a special character")
    if problems:
        raise ValidationError("Password needs " + ", ".join(problems) + ".")


class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "Email", validators=[DataRequired(), Email(message="Enter a valid email address."), Length(max=255)]
    )
    password = PasswordField("Password", validators=[DataRequired(), strong_password])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), strong_password])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
