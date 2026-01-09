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
from datetime import datetime   # Needed for timestamp defaults

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
# EXPENSE MODEL
# ===================================================================
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)

    # What the user types (like "Groceries")
    item = db.Column(db.String(255), nullable=False)

    # What the user types (like 50.00)
    cost = db.Column(db.Float, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('expenses', lazy=True))

