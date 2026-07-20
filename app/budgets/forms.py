import re

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError


def valid_month(form, field):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", field.data or ""):
        raise ValidationError("Choose a valid month.")


class MonthlyBudgetForm(FlaskForm):
    month = StringField("Month", validators=[DataRequired(), valid_month])
    income_sources = TextAreaField("Monthly income sources", validators=[DataRequired()])
    savings_target = DecimalField("Savings goal (optional)", default=0, validators=[NumberRange(min=0)])
    food_budget = DecimalField("Eating out", default=0, validators=[NumberRange(min=0)])
    groceries_budget = DecimalField("Groceries", default=0, validators=[NumberRange(min=0)])
    transport_budget = DecimalField("Rent", default=0, validators=[NumberRange(min=0)])
    utilities_budget = DecimalField("Bills", default=0, validators=[NumberRange(min=0)])
    entertainment_budget = DecimalField("Money sent home", default=0, validators=[NumberRange(min=0)])
    other_budget = DecimalField("Other expenses", default=0, validators=[NumberRange(min=0)])


class PersonalExpenseForm(FlaskForm):
    description = StringField("What did you spend on?", validators=[DataRequired(), Length(max=120)])
    amount = DecimalField("Amount", places=2, validators=[InputRequired(), NumberRange(min=0.01)])
    category = SelectField("Category", choices=[
        ("Rent", "Rent"), ("Bills", "Bills"), ("Groceries", "Groceries"),
        ("Eating out", "Eating out"), ("Money sent home", "Money sent home"),
        ("Other expenses", "Other expenses"),
    ], validators=[DataRequired()])
    expense_date = DateField("Date", validators=[DataRequired()])


class RecurringBillForm(FlaskForm):
    bill_type = SelectField("Bill type", choices=[
        ("Health insurance", "Health insurance"),
        ("Rundfunkbeitrag", "Radio tax (Rundfunkbeitrag)"),
        ("Mobile phone", "Mobile phone / recharge"),
        ("Internet", "Internet"),
        ("Electricity", "Electricity"),
        ("Public transport", "Public transport"),
        ("Other", "Other recurring bill"),
    ], validators=[DataRequired()])
    description = StringField(
        "Description", validators=[DataRequired(), Length(max=120)]
    )
    amount = DecimalField(
        "Monthly amount", places=2,
        validators=[InputRequired(), NumberRange(min=0.01)],
    )
