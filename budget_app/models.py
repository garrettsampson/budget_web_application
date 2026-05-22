# models.py
"""
This file defines the DATABASE STRUCTURE (tables) for your application
using SQLAlchemy, which is the ORM (Object Relational Mapper) used by
Flask-SQLAlchemy.

⚠️ IMPORTANT CONCEPTS TO UNDERSTAND:

1. SQLAlchemy turns Python CLASSES → SQL tables.
2. Each class variable defined with `db.Column()` becomes a column.
3. Every object you create (User(), IncomeWeek()) becomes a ROW.
4. SQLAlchemy automatically handles table creation, relationships,
   foreign keys, updates, deletes, etc.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date   # Needed for timestamp defaults
#from models import db

# -------------------------------------------------------------------
# db = SQLAlchemy()
# -------------------------------------------------------------------
# This creates ONE SQLAlchemy "database engine" object.
# You do NOT connect to the database yet — that happens in app.py when
# you call:
#       db.init_app(app)
#
# This db object is shared across the entire application.
# Every model class below uses THIS `db` instance.
db = SQLAlchemy()


# ===================================================================
# USER MODEL
# ===================================================================
class User(db.Model):
    """
    Represents ONE user of the application.

    A model class becomes a TABLE called 'user' by default.
    (SQLAlchemy lowercases the class name.)

    Later, when we add Google OAuth login:
        - Each person logging in will get exactly one User row.
        - Their email will be unique.
        - Every IncomeWeek they create will reference their user_id.
    """

    # --------------------------------------------------------------
    # id = PRIMARY KEY
    # --------------------------------------------------------------
    # Primary key = unique identifier for every row.
    # SQLAlchemy automatically assigns a new integer to each user.
    id = db.Column(db.Integer, primary_key=True)

    # --------------------------------------------------------------
    # email = STRING COLUMN
    # --------------------------------------------------------------
    # unique=True     → no two users may share the same email
    # nullable=False  → email cannot be NULL in the database
    #
    # NOTE: nullable=True means the database ALLOWS NULL values.
    #       nullable=False means the field MUST have a value.
    #
    # In professional applications, emails are ALWAYS required.
    email = db.Column(db.String(255), unique=True, nullable=False)

    # --------------------------------------------------------------
    # password_hash = SECURE STORED PASSWORD
    # --------------------------------------------------------------
    # We never store the user's real password in the database.
    # Instead, we store a hashed version created by Werkzeug.
    #
    # Login process later:
    #   1. User types password
    #   2. We hash/check it using check_password_hash()
    #   3. If it matches, we log them in
    password_hash = db.Column(db.String(255), nullable=True)

    # --------------------------------------------------------------
    # created_at = DATETIME COLUMN (automatic timestamp)
    # --------------------------------------------------------------
    # db.DateTime         → stores both date + time
    # default=datetime.utcnow
    #       - `default=` means SQLAlchemy will CALL this function
    #         whenever a new row is created.
    #       - We do not put parentheses, because SQLAlchemy must call
    #         the function itself each time.
    #
    # Why UTC?
    # - UTC timestamps are standard in databases.
    # - Local timezones cause major issues when traveling/international.
    #
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ===================================================================
# INCOME WEEK MODEL
# ===================================================================
class IncomeWeek(db.Model):
    """
    Represents ONE WEEK of income for a specific user, month, and year.

    Example:

        user_id     = 1
        year        = 2025
        month       = 11
        week_index  = 2
        hourly_pay  = 20.00
        hours       = 35
        tax_percent = 8
        gross       = 700.00
        net         = 644.00

    This is the core of your budgeting system. Every week you enter
    produces one row in this table.
    """

    # --------------------------------------------------------------
    # id = PRIMARY KEY
    # --------------------------------------------------------------
    # Just like User.id, this gives each income entry a unique ID.
    id = db.Column(db.Integer, primary_key=True)

    # --------------------------------------------------------------
    # FOREIGN KEY: user_id
    # --------------------------------------------------------------
    # This links each IncomeWeek to the user who created it.
    #
    # db.ForeignKey("user.id") means:
    #     - Look at the "user" table
    #     - Use the "id" column
    #
    # nullable=False means every IncomeWeek MUST belong to a user.
    #
    # IMPORTANT:
    #   SQLAlchemy does NOT automatically enforce cascading deletes
    #   unless you configure it (we'll talk about this later).
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # --------------------------------------------------------------
    # year & month (INTEGER COLUMNS)
    # --------------------------------------------------------------
    # These fields classify WHICH month the income belongs to.
    # They allow us to GROUP weekly entries into a monthly summary.
    #
    # Example:
    # year=2025, month=11 → November 2025
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)   # 1 to 12 only

    # --------------------------------------------------------------
    # week_index (INTEGER)
    # --------------------------------------------------------------
    # This identifies the "week number" within the month.
    # It is NOT tied to calendar dates — it's simply:
    #   - Week 1
    #   - Week 2
    #   - ... up to 5 possible entries
    #
    # Later, we will prevent duplicate week entries using:
    # filter_by(user_id, year, month, week_index)
    week_index = db.Column(db.Integer, nullable=False)

    # --------------------------------------------------------------
    # INPUT FIELDS (the data the user provides)
    # --------------------------------------------------------------
    # We store hourly pay, hours worked, and tax percent.
    #
    # Using Float type because:
    #   - Hours may not always be an integer (ex: 37.5 hrs)
    #   - Money values require decimals
    hourly_pay = db.Column(db.Float, nullable=False)
    hours = db.Column(db.Float, nullable=False)

    # tax_percent represents the PERCENT (like 8.0 for 8%),
    # not the decimal (0.08). We convert it manually.
    tax_percent = db.Column(db.Float, nullable=False)

    # --------------------------------------------------------------
    # COMPUTED FIELDS (gross + net income)
    # --------------------------------------------------------------
    # We calculate these BEFORE saving:
    #
    # gross = hourly_pay * hours
    # net   = gross * (1 - (tax_percent / 100))
    #
    # We store these values so we don’t need to recalculate them
    # every time we display them in a template.
    gross = db.Column(db.Float, nullable=False)
    net = db.Column(db.Float, nullable=False)

    # --------------------------------------------------------------
    # RELATIONSHIP: user = reference to parent User object
    # --------------------------------------------------------------
    # SQLAlchemy automatically creates a convenient link:
    #
    # income_week = IncomeWeek(...)
    # income_week.user → gives the User object for this income row
    #
    # backref='income_weeks'
    #       - Gives User objects a list of related income entries.
    #         Example:
    #              some_user.income_weeks → list of all IncomeWeek rows
    #
    # lazy=True:
    #       - Means SQLAlchemy loads related rows only when first accessed.
    #       - Prevents unnecessary database queries.
    user = db.relationship('User', backref=db.backref('income_weeks', lazy=True))


# ===================================================================
# PAYCHECK MODEL
# ===================================================================
class Paycheck(db.Model):
    """
    Represents ONE real-life income payment.

    This replaces the old "week_index" income style for real usage.

    Real-life paycheck logic:
      - pay_date = the day money hits the bank account
      - period_start = first work date covered by the paycheck
      - period_end = last work date covered by the paycheck
      - net_amount = money actually received
      - gross_amount/hours/hourly_rate/tax_withheld are optional details

    Monthly income totals should use pay_date, because budgeting usually
    cares about when money actually entered the account.
    """

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    pay_date = db.Column(db.Date, nullable=False)

    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)

    net_amount = db.Column(db.Float, nullable=False)
    gross_amount = db.Column(db.Float, nullable=True)

    hours_worked = db.Column(db.Float, nullable=True)
    hourly_rate = db.Column(db.Float, nullable=True)
    tax_withheld = db.Column(db.Float, nullable=True)

    pay_type = db.Column(db.String(50), nullable=False, default="Paycheck")
    notes = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("paychecks", lazy=True))

# ===================================================================
# EXPENSE MODEL
# ===================================================================
class Expense(db.Model):
    """
    ONE expense row inside a month/year for a user.

    New structure:
      - category: saved from dropdown (consistent for analytics)
      - description: user's custom text (details)
      - cost: money value
    """

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # NEW: dropdown bucket
    category = db.Column(db.String(64), nullable=True)

    # NEW: free text details
    description = db.Column(db.String(255), nullable=True)

    cost = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Track edits and soft-deletes
    updated_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Soft-delete flag
    # True = show in UI
    # False = hidden but kept for history 
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship("User", backref=db.backref("expenses", lazy=True))

    note = db.Column(db.String(50), nullable=True)

# ===================================================================
# EXPENSE HISTORY MODEL (AUDIT TRAIL)
# ===================================================================
class ExpenseHistory(db.Model):
    """
    Audit log of every meaningful change to an Expense row.

    We record:
      - what changed (create/update/delete)
      - when it changed
      - which expense row it belongs to
      - before-values and after-values

    This lets you do analytics later like:
      - "what did I change this from?"
      - "when did this expense first appear?"
      - "show removed expenses"
    """

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id"), nullable=False)

    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # create / update / delete
    action = db.Column(db.String(10), nullable=False)

    # BEFORE values
    old_category = db.Column(db.String(64), nullable=True)
    old_description = db.Column(db.String(255), nullable=True)
    old_cost = db.Column(db.Float, nullable=True)

    # AFTER values
    new_category = db.Column(db.String(64), nullable=True)
    new_description = db.Column(db.String(255), nullable=True)
    new_cost = db.Column(db.Float, nullable=True)

    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("expense_history", lazy=True))
    expense = db.relationship("Expense", backref=db.backref("history", lazy=True))

# ===================================================================
# SAVINGS ALLOCATION MODEL
# ===================================================================
class SavingsAllocation(db.Model):
    """
    Represents ONE "savings" row for a specific user, month, and year.

    This table is intentionally designed to mirror the Expenses table
    behavior, but with one important difference:

        - Expenses store a *dollar* cost.
        - Savings store a *percent* allocation.

    We do NOT permanently store the dollar amount, because the dollar
    amount depends on "money_left" which can change if income/expenses
    change. Instead, we store the percent and compute dollars live:

        row_amount = money_left * (percent / 100)

    Fields:
      - bucket:  the dropdown category (e.g., "Retirement", "Emergency Fund")
      - name:    the specific item inside that bucket (typed by the user)
      - percent: the allocation percent for this row (0-100)

    Like Expense, we support soft-delete so rows can be removed from the
    spreadsheet UI without permanently losing history.
    """

    # Primary key (unique row id)
    id = db.Column(db.Integer, primary_key=True)

    # Who this row belongs to
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Which month/year this row belongs to
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # "Bucket" = the dropdown grouping/category
    bucket = db.Column(db.String(64), nullable=True)

    # "Name" = the specific item inside the bucket
    # (We intentionally allow free-text so the user can create new names)
    name = db.Column(db.String(255), nullable=True)

    # Percent allocation for this row.
    # Stored as a float so you can do decimals like 12.5%
    percent = db.Column(db.Float, nullable=False, default=0.0)

    # Timestamps + soft-delete controls
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationship back to the User
    user = db.relationship("User", backref=db.backref("savings_allocations", lazy=True))

# ===================================================================
# EXPENSES: Custom dropdown options (Bucket + Merchant)
# ===================================================================

class ExpenseBucketOption(db.Model):
    """
    A user-defined BUCKET/GROUP option for expenses (dropdown #1).

    Examples:
      - Subscriptions
      - Utilities
      - Pet Care
      - (custom user bucket)

    We soft-delete so the user can remove options without breaking history.
    """
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # The text shown in the dropdown (the actual bucket name)
    label = db.Column(db.String(64), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("expense_bucket_options", lazy=True))


class ExpenseMerchantOption(db.Model):
    """
    A user-defined MERCHANT/NAME option for expenses (dropdown #2),
    scoped to a specific bucket label.

    Examples:
      bucket_label="Subscriptions" -> "Netflix", "Spotify"
      bucket_label="Utilities"     -> "Entergy", "City Water"
    """
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Which bucket this name belongs to (store bucket text to keep it simple)
    bucket_label = db.Column(db.String(64), nullable=False)

    # The merchant/name
    name = db.Column(db.String(255), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("expense_merchant_options", lazy=True))


# ===================================================================
# SAVINGS: Custom dropdown options (Bucket + Name)
# ===================================================================

class SavingsBucketOption(db.Model):
    """
    A user-defined BUCKET option for savings (dropdown #1).

    Examples:
      - Investments
      - Emergency Fund
      - Travel Fund
      - (custom user bucket)
    """
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    label = db.Column(db.String(64), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("savings_bucket_options", lazy=True))


class SavingsNameOption(db.Model):
    """
    A user-defined NAME option for savings (dropdown #2),
    scoped to a specific bucket label.

    Examples:
      bucket_label="Investments" -> "Rental Property", "VOO"
      bucket_label="Debt Payoff" -> "Car Loan"
    """
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    bucket_label = db.Column(db.String(64), nullable=False)

    name = db.Column(db.String(255), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("savings_name_options", lazy=True))
