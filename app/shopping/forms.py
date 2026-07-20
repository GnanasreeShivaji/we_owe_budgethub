from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class ShoppingItemForm(FlaskForm):
    name = StringField("Item", validators=[DataRequired(), Length(max=120)])
    quantity = StringField("Quantity", default="1", validators=[DataRequired(), Length(max=50)])
    category = SelectField("Category", choices=[
        ("Groceries", "Groceries"), ("Household", "Household"),
        ("Personal care", "Personal care"), ("Study", "Study supplies"),
        ("Other", "Other"),
    ], validators=[DataRequired()])
    note = StringField("Note (optional)", validators=[Optional(), Length(max=240)])
    assigned_to = SelectField("Who should buy it?", coerce=int, choices=[], validate_choice=False)
    price = DecimalField("Price after purchase (optional)", places=2,
                         validators=[Optional(), NumberRange(min=0.01)])
