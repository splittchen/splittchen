"""WTForms for Splittchen application."""

from datetime import datetime, timezone
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, SelectField, DateField, HiddenField, SelectMultipleField, BooleanField
from wtforms.validators import DataRequired, Email, Optional, NumberRange, Length
from wtforms.widgets import TextArea


class CreateGroupForm(FlaskForm):
    """Form for creating a new expense group."""
    group_name = StringField('Group Name', validators=[
        DataRequired(message='Group name is required'),
        Length(min=1, max=100, message='Group name must be between 1 and 100 characters')
    ])
    your_name = StringField('Your Name', validators=[
        DataRequired(message='Your name is required'),
        Length(min=1, max=100, message='Name must be between 1 and 100 characters')
    ])
    email = StringField('Your Email', validators=[
        DataRequired(message='Email is required for group confirmation'),
        Email(message='Please enter a valid email address'),
        Length(max=120, message='Email cannot exceed 120 characters')
    ])
    description = TextAreaField('Description (Optional)', validators=[
        Optional(),
        Length(max=500, message='Description cannot exceed 500 characters')
    ], widget=TextArea())
    default_currency = SelectField('Group Currency', validators=[
        DataRequired(message='Please select a default currency')
    ])
    expires_at = DateField('Expiration Date (Optional)', validators=[Optional()])
    is_recurring = BooleanField('Monthly Auto-Settlement', default=False, 
                               description='Automatically settle balances monthly and send reports')


class JoinGroupForm(FlaskForm):
    """Form for joining a group via token."""
    share_token = StringField('Group Code', validators=[
        DataRequired(message='Group code is required'),
        Length(min=6, max=12, message='Invalid group code format')
    ])


class AddParticipantForm(FlaskForm):
    """Form for adding a participant to a group."""
    name = StringField('Your Name', validators=[
        DataRequired(message='Name is required'),
        Length(min=1, max=100, message='Name must be between 1 and 100 characters')
    ])
    email = StringField('Email (Optional)', validators=[
        Optional(),
        Email(message='Please enter a valid email address'),
        Length(max=120, message='Email cannot exceed 120 characters')
    ])
    color = HiddenField('Color')


class AddExpenseForm(FlaskForm):
    """Form for adding an expense."""
    title = StringField('Expense Title', validators=[
        DataRequired(message='Expense title is required'),
        Length(min=1, max=200, message='Title must be between 1 and 200 characters')
    ])
    description = TextAreaField('Description (Optional)', validators=[
        Optional(),
        Length(max=500, message='Description cannot exceed 500 characters')
    ])
    amount = DecimalField('Amount', validators=[
        DataRequired(message='Amount is required'),
        NumberRange(min=0.01, message='Amount must be greater than 0')
    ], places=2)
    currency = SelectField('Currency', validators=[
        DataRequired(message='Please select a currency')
    ])
    category = SelectField('Category', choices=[
        ('general', 'General'),
        ('food', 'Food & Dining'),
        ('transport', 'Transportation'),
        ('accommodation', 'Accommodation'),
        ('entertainment', 'Entertainment'),
        ('shopping', 'Shopping'),
        ('utilities', 'Utilities'),
        ('other', 'Other')
    ], default='general')
    paid_by_id = SelectField('Paid By', coerce=int, validators=[
        DataRequired(message='Please select who paid for this expense')
    ])
    split_between = SelectMultipleField('Split Between', coerce=int, validators=[
        DataRequired(message='Please select at least one person to split this expense between')
    ])
    split_type = SelectField('Split Method', choices=[
        ('EQUAL', 'Split Equally'),
        ('EXACT', 'Enter Exact Amounts'),
        ('PERCENTAGE', 'Enter Percentages')
    ], default='EQUAL')
    date = DateField('Date', validators=[DataRequired()])


class EditExpenseForm(FlaskForm):
    """Form for editing an existing expense."""
    title = StringField('Expense Title', validators=[
        DataRequired(message='Expense title is required'),
        Length(min=1, max=200, message='Title must be between 1 and 200 characters')
    ])
    description = TextAreaField('Description (Optional)', validators=[
        Optional(),
        Length(max=500, message='Description cannot exceed 500 characters')
    ])
    amount = DecimalField('Amount', validators=[
        DataRequired(message='Amount is required'),
        NumberRange(min=0.01, message='Amount must be greater than 0')
    ], places=2)
    currency = SelectField('Currency', validators=[
        DataRequired(message='Please select a currency')
    ])
    category = SelectField('Category', choices=[
        ('general', 'General'),
        ('food', 'Food & Dining'),
        ('transport', 'Transportation'),
        ('accommodation', 'Accommodation'),
        ('entertainment', 'Entertainment'),
        ('shopping', 'Shopping'),
        ('utilities', 'Utilities'),
        ('other', 'Other')
    ], default='general')
    paid_by_id = SelectField('Paid By', coerce=int, validators=[
        DataRequired(message='Please select who paid for this expense')
    ])
    split_between = SelectMultipleField('Split Between', coerce=int, validators=[
        DataRequired(message='Please select at least one person to split this expense between')
    ])
    split_type = SelectField('Split Method', choices=[
        ('EQUAL', 'Split Equally'),
        ('EXACT', 'Enter Exact Amounts'),
        ('PERCENTAGE', 'Enter Percentages')
    ], default='EQUAL')
    date = DateField('Date', validators=[DataRequired()])


class ShareGroupForm(FlaskForm):
    """Form for sharing group via email."""
    email = StringField('Email Address', validators=[
        DataRequired(message='Email address is required'),
        Email(message='Please enter a valid email address')
    ])
    message = TextAreaField('Personal Message (Optional)', validators=[
        Optional(),
        Length(max=500, message='Message cannot exceed 500 characters')
    ])