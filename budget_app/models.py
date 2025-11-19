# models.py
"""
This file defines the DATABASE STRUCTURE for your app using SQLAlchemy.

Instead of writing raw SQL like:
    CREATE TABLE users (...);

You define Python CLASSES (User, IncomeWeek), and SQLAlchemy turns those
into actual database tables behind the scenes.

Each class that inherits from db.Model becomes a table.
Each db.Column(...) becomes a column in that table.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime  # <-- IMPORTANT: this fixes the underline on datetime.utcnow

# This "db" object is the main handle we use to talk to the database.
# Your Flask app (in app.py) will call db.init_app(app) to connect this
# to the actual SQLite database file.
db = SQLAlchemy()


class User(db.Model):
    """
    Represents ONE user of your app.

    Later, when we add Google login, each person who logs in with their
    Google account will have one row in this table.

    For now, we just create a single dummy user so you can build and test
    all features without worrying about authentication yet.
    """

    # 'id' is the PRIMARY KEY.
    # primary_key=True means:
    #   - This uniquely identifies each row.
    #   - The database will auto-generate a new integer for each new user.
    id = db.Column(db.Integer, primary_key=True)

    # 'email' is a string column up to 255 characters.
    # unique=True  -> no two users can have the same email.
    # nullable=False -> this field CANNOT be empty; database will reject a NULL here.
    #
    # "nullable" means "can this be NULL in the database?"
    # - nullable=False: must have a value.
    # - nullable=True: allowed to be empty / NULL.
    email = db.Column(db.String(255), unique=True, nullable=False)

    # 'created_at' stores when this user was created.
    # db.DateTime means the type is a datetime object (date + time).
    #
    # default=datetime.utcnow means:
    #   - If you don't specify created_at when creating a User,
    #     SQLAlchemy will call datetime.utcnow() and use that.
    #
    # NOTE: we imported datetime from datetime at the top:
    #   from datetime import datetime
    #
    # If you don't import that, VS Code underlines 'datetime' because it
    # doesn't know what that name refers to.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IncomeWeek(db.Model):
    """
    Stores income information for ONE WEEK of a specific month and year.

    Example row:
        user_id: 1
        year: 2025
        month: 11  (November)
        week_index: 1  (Week 1)
        hourly_pay: 20.00
        hours: 30.0
        tax_percent: 10.0
        gross: 600.00
        net: 540.00

    In your app, you'll have multiple IncomeWeek rows per month.
    """

    # Primary key for this table.
    id = db.Column(db.Integer, primary_key=True)

    # Link this income entry to the user it belongs to.
    #
    # ForeignKey("user.id") means this column references the 'id' column
    # in the 'user' table.
    #
    # nullable=False means you MUST provide a user_id for every IncomeWeek.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # YEAR and MONTH describe which month this income belongs to.
    # Example:
    #   year = 2025
    #   month = 11 (for November)
    #
    # We'll use these to pull all weeks for a given month and show your
    # monthly summary.
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)      # 1–12

    # week_index is your own label for "Week 1", "Week 2", etc.
    # It doesn't represent exact dates, just an index.
    #
    # We'll sort by this in the monthly view so that the weeks appear
    # in order.
    week_index = db.Column(db.Integer, nullable=False)  # e.g. 1..5

    # INPUT FIELDS:
    # These store what you typed into the form.
    #
    # Float means decimal numbers are allowed (not just integers).
    hourly_pay = db.Column(db.Float, nullable=False)
    hours = db.Column(db.Float, nullable=False)
    tax_percent = db.Column(db.Float, nullable=False)

    # COMPUTED FIELDS:
    # We calculate these in Python (gross = hourly * hours, net = gross * (1 - tax%))
    # and store them so they are easy to use later.
    gross = db.Column(db.Float, nullable=False)
    net = db.Column(db.Float, nullable=False)

    # Relationship: this creates a connection from IncomeWeek to User.
    #
    # After this, each IncomeWeek instance has a .user attribute that gives you
    # the User object it belongs to.
    #
    # backref='income_weeks' means the user object also gets a '.income_weeks'
    # attribute that lists all IncomeWeek rows for that user.
    user = db.relationship('User', backref=db.backref('income_weeks', lazy=True))
