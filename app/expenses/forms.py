"""Forms for creating and editing group expenses (US-03)."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import DateField, DecimalField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional


class ExpenseForm(FlaskForm):
    title = StringField("Expense", validators=[DataRequired(), Length(max=120)])
    amount = DecimalField(
        "Amount", places=2, validators=[InputRequired(), NumberRange(min=0.01, max=9999999999)]
    )
    currency = SelectField(
        "Currency",
        choices=[("EUR", "EUR · Euro (€)"), ("USD", "USD · US Dollar ($)"),
                 ("INR", "INR · Indian Rupee (₹)"), ("GBP", "GBP · Pound (£)")],
        validators=[Optional()],
    )
    category = SelectField(
        "Category",
        choices=[
            ("Eating out", "Eating out"),
            ("Groceries", "Groceries"),
            ("Rent", "Rent"),
            ("Bills", "Bills"),
            ("Money sent home", "Money sent home"),
            ("Other expenses", "Other expenses"),
        ],
        validators=[DataRequired()],
        validate_choice=False,  # accept legacy category values on existing records
    )
    expense_date = DateField("Date", validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=500)])
    receipt = FileField(
        "Receipt (optional)",
        validators=[FileAllowed(["jpg", "jpeg", "png", "gif", "webp", "pdf"], "Upload an image or PDF receipt.")],
    )
    split_method = SelectField(
        "Split method",
        choices=[
            ("equal", "Equally"),
            ("exact", "Exact amounts"),
            ("percentage", "Percentages"),
            ("shares", "Shares"),
            ("receipt", "Receipt item checklist"),
        ],
        validators=[DataRequired()],
    )
