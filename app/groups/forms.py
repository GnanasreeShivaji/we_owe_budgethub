"""Group forms (US-02)."""
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from ..models import Membership


class GroupForm(FlaskForm):
    name = StringField("Group name", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])


class InviteForm(FlaskForm):
    email = StringField("Member email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField(
        "Role",
        choices=[(Membership.MEMBER, "Member"), (Membership.ADMIN, "Admin")],
        default=Membership.MEMBER,
    )
