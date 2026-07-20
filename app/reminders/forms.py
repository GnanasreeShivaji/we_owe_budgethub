from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, DecimalField, SelectField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional


class PaymentReminderForm(FlaskForm):
    recipient_id = SelectField("Remind", coerce=int, choices=[], validators=[DataRequired()])
    amount = DecimalField(
        "Amount", places=2, validators=[InputRequired(), NumberRange(min=0.01)]
    )
    timing = SelectField("When", choices=[
        ("now", "Send now"), ("tomorrow", "Tomorrow"),
        ("three_days", "In 3 days"), ("custom", "Choose date and time"),
    ], validators=[DataRequired()])
    scheduled_for = DateTimeLocalField("Custom date and time", validators=[Optional()])
    message = TextAreaField(
        "Personal message (optional)", validators=[Optional(), Length(max=500)]
    )
