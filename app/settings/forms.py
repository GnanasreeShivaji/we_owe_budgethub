from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField
from wtforms.validators import DataRequired


class PreferencesForm(FlaskForm):
    timezone = SelectField("Timezone", choices=[
        ("Europe/Berlin", "Germany · Europe/Berlin"),
        ("Asia/Kolkata", "India · Asia/Kolkata"),
        ("America/New_York", "USA Eastern · America/New_York"),
        ("America/Los_Angeles", "USA Pacific · America/Los_Angeles"),
        ("UTC", "UTC"),
    ], validators=[DataRequired()])
    currency = SelectField("Currency", choices=[
        ("EUR", "EUR · Euro (€)"), ("USD", "USD · US Dollar ($)"),
        ("INR", "INR · Indian Rupee (₹)"), ("GBP", "GBP · British Pound (£)"),
    ], validators=[DataRequired()])
    notify_immediate = BooleanField("Email me immediate payment reminders")
    notify_scheduled = BooleanField("Email me scheduled payment reminders")


class DeleteAccountForm(FlaskForm):
    password = PasswordField("Current password", validators=[DataRequired()])
