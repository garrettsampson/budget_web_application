"""
app.py

This file defines the *main Flask application* that runs your entire program.

High-Level Flow of This File:
--------------------------------------------------------------------
1. We create a Flask app instance.
2. We load configuration values (database path, secret key, etc.).
3. We initialize the SQLAlchemy database object (`db`) so it connects
   to the Flask app and knows where the database is stored.
4. We create database tables (if they don't already exist).
5. We define helper functions (such as get_current_user).
6. We define ROUTES — these are URLs that users can visit.

Current Routes in This App:
--------------------------------------------------------------------
"/"                     → The home dashboard page.
"/income"               → Form for entering weekly income.
"/income/<year>/<month>" → Monthly summary for a selected month.

This file will grow as we add:
- Savings section
- Yearly breakdown
- Goals section
- Delete/reset features
- Google login
- Partner split
- More tools and pages
"""

# --------------------------
# Import Flask and helpers
# --------------------------
from flask import Flask, render_template, request, redirect, url_for

# Import your database models
from models import db, User, IncomeWeek

# Import configuration settings (DB path, secret key, etc.)
from config import Config

# Used for automatically filling the form with today's year/month
from datetime import datetime


# ======================================================================
# APPLICATION FACTORY FUNCTION
# ======================================================================
def create_app():
    """
    Creates and configures the Flask application.

    Flask recommends the “Application Factory Pattern” because:
      ● It cleanly separates setup logic.
      ● It makes unit testing easier.
      ● It makes it easier to create multiple app instances if needed.
      ● It improves organization for large projects.

    Anytime we want a working Flask app, we call create_app().
    """

    # Create the Flask app instance
    app = Flask(__name__)

    # Load all configuration settings (SECRET_KEY, DB URI, etc.)
    app.config.from_object(Config)

    # Connect the SQLAlchemy 'db' engine (from models.py) to this app.
    # Without this, the database wouldn't know which Flask app it's tied to.
    db.init_app(app)

    # --------------------------------------------------------------
    # Ensure that the database tables exist.
    #
    # This block runs ONCE when you start the app.
    # "app.app_context()" gives SQLAlchemy permission to create tables.
    # --------------------------------------------------------------
    with app.app_context():

        # Creates the database tables based on your models IF they don't exist yet.
        # If the tables already exist, SQLAlchemy does nothing.
        db.create_all()

        # Create a default user if none exist.
        # This makes your app easy to test before Google login is added.
        if not User.query.first():
            dummy_user = User(email="you@example.com")
            db.session.add(dummy_user)
            db.session.commit()

    # --------------------------------------------------------------
    # Helper Function: get_current_user()
    # --------------------------------------------------------------
    def get_current_user():
        """
        Returns the currently logged-in user.

        Right now this just returns the dummy user, because authentication
        has not yet been implemented. Later this will return:

            User.query.filter_by(email=google_email).first()

        after you log in with Google OAuth.
        """
        return User.query.first()


    # ==================================================================
    # ROUTE: Home Dashboard
    # URL: "/"
    # ==================================================================
    @app.route("/")
    def home():
        """
        This function runs when the user visits your website root (/).

        It simply loads the dashboard.html file, located in:
            templates/dashboard.html

        In the future, the dashboard might show:
        - Monthly summaries
        - Recent activity
        - Quick stats
        - Buttons linking to savings, yearly view, etc.
        """
        return render_template("dashboard.html")


    # ==================================================================
    # ROUTE: Weekly Income Form
    # URL: "/income"
    # METHODS:
    #   GET  → Show the form
    #   POST → Process the submitted form
    # ==================================================================
    @app.route("/income", methods=["GET", "POST"])
    def income_form():
        # Get the current user object (the dummy user for now)
        user = get_current_user()

        # --------------------------------------------------------------
        # POST Request: the user has submitted the form.
        # --------------------------------------------------------------
        if request.method == "POST":

            # All values from <input> fields come in as strings.
            # We must convert them to numbers before doing math.

            hourly = float(request.form["hourly_pay"])       # Hourly wage
            hours = float(request.form["hours_worked"])      # Hours worked this week
            tax_percent = float(request.form["tax_percent"]) # Percent (e.g., 8%)

            # Month and year the user selected
            year = int(request.form["year"])
            month = int(request.form["month"])
            week_index = int(request.form["week_index"])

                        # ================================================================
            # DUPLICATE PREVENTION CHECK
            # ---------------------------------------------------------------
            # Before saving a new week, check if one already exists for:
            #   - current user
            #   - same year
            #   - same month
            #   - same week_index
            #
            # If a duplicate is found:
            #   → Show an error flash message
            #   → Redirect back to monthly summary
            #   → DO NOT save the duplicate
            # ================================================================

            existing_entry = IncomeWeek.query.filter_by(
                user_id=user.id,
                year=year,
                month=month,
                week_index=week_index
            ).first()

            if existing_entry:
                # Show an unobtrusive pastel toast (from Step 1)
                from flask import flash
                flash(f"Week {week_index} for {month}/{year} already exists.", "error")

                # Redirect to that month’s summary so the user can see the existing entries
                return redirect(url_for("income_month_view", year=year, month=month))


            # ----------------------------------------------------------
            # Calculate the weekly income:
            # - gross income (before taxes)
            # - net income (after taxes)
            # ----------------------------------------------------------
            gross = hourly * hours
            net = gross * (1 - tax_percent / 100.0)

            # ----------------------------------------------------------
            # Create a new IncomeWeek row in Python.
            # This does NOT save it to the database yet.
            # ----------------------------------------------------------
            entry = IncomeWeek(
                user_id=user.id,
                year=year,
                month=month,
                week_index=week_index,
                hourly_pay=hourly,
                hours=hours,
                tax_percent=tax_percent,
                gross=gross,
                net=net,
            )

            # Stage this new row for saving
            db.session.add(entry)

            # Commit = permanently write the staged changes to the DB
            db.session.commit()

            # After saving, redirect to the monthly summary for the chosen month
            return redirect(url_for("income_month_view", year=year, month=month))

        # --------------------------------------------------------------
        # GET Request: user is visiting /income normally (no form submit)
        # --------------------------------------------------------------
        today = datetime.today()

        # Pass today's year and month as defaults to the form.
        # Example: If today is 2025-11-18, defaults are:
        #   current_year=2025, current_month=11
        return render_template(
            "income/form.html",
            current_year=today.year,
            current_month=today.month,
        )


    # ==================================================================
    # ROUTE: Monthly Income Summary
    # URL: /income/<year>/<month>
    # Example: /income/2025/11
    # ==================================================================
    @app.route("/income/<int:year>/<int:month>")
    def income_month_view(year, month):
        """
        This route displays ALL weekly income entries for a given month.

        The logic is:
        1. Query the IncomeWeek table to get all entries for:
                - the current user
                - the selected year
                - the selected month

        2. Sort them by week_index (Week 1, Week 2, etc.).

        3. Calculate:
                - total gross income
                - total net income
                - total taxes paid

        4. Pass everything into a template so it can display
           a clean summary table.
        """

        user = get_current_user()

        # Query all weekly rows for this user/month/year.
        entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .order_by(IncomeWeek.week_index)  # sort by week number
            .all()
        )

        # Calculate monthly totals
        total_gross = sum(e.gross for e in entries)
        total_net = sum(e.net for e in entries)
        total_tax = total_gross - total_net

        # Render the summary template and pass all data to it
        return render_template(
            "income/month_view.html",
            year=year,
            month=month,
            entries=entries,
            total_gross=total_gross,
            total_net=total_net,
            total_tax=total_tax,
        )

    # Must return the app instance
    return app


# ======================================================================
# RUNNING THE APP DIRECTLY
# ======================================================================
# The code below allows you to run:
#       python app.py
# and start the development server automatically.
#
# If this file is imported instead, this block will NOT run.
app = create_app()

if __name__ == "__main__":
    # debug=True means:
    #   - Live reload when you save changes
    #   - Detailed error pages (very helpful during development)
    app.run(debug=True)
