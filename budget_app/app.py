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
"""

# --------------------------
# Import Flask and helpers
# --------------------------
from flask import Flask, render_template, request, redirect, url_for

# Import your database models
from models import db, User, IncomeWeek, Expense

# Import configuration settings (DB path, secret key, etc.)
from config import Config

# Used for automatically filling the form with today's year/month
from datetime import datetime

from models import db, Expense




# ======================================================================
# APPLICATION FACTORY FUNCTION
# ======================================================================
def create_app():
    """Creates and configures the Flask application."""

    app = Flask(__name__)
    app.config.from_object(Config)

    # Connect SQLAlchemy "db" to this Flask app
    db.init_app(app)

    # Create tables + default user if needed
    with app.app_context():
        db.create_all()
        if not User.query.first():
            dummy_user = User(email="you@example.com")
            db.session.add(dummy_user)
            db.session.commit()

    # Helper function
    def get_current_user():
        return User.query.first()

    # ==================================================================
    # ROUTE: Home Dashboard
    # ==================================================================
    @app.route("/")
    def home():
        return render_template("dashboard.html")

    # ==================================================================
    # ROUTE: Weekly Income Form
    # ==================================================================
    @app.route("/income", methods=["GET", "POST"])
    def income_form():
        user = get_current_user()

        if request.method == "POST":
            # Convert form values
            hourly = float(request.form["hourly_pay"])
            hours = float(request.form["hours_worked"])
            tax_percent = float(request.form["tax_percent"])
            year = int(request.form["year"])
            month = int(request.form["month"])
            week_index = int(request.form["week_index"])

            # Duplicate week prevention
            existing_entry = IncomeWeek.query.filter_by(
                user_id=user.id,
                year=year,
                month=month,
                week_index=week_index
            ).first()

            if existing_entry:
                from flask import flash
                flash(f"Week {week_index} for {month}/{year} already exists.", "error")
                return redirect(url_for("income_month_view", year=year, month=month))

            # Calculate gross + net
            gross = hourly * hours
            net = gross * (1 - tax_percent / 100.0)

            # Create entry
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

            db.session.add(entry)
            db.session.commit()

            return redirect(url_for("income_month_view", year=year, month=month))

        # GET Request: prefill form with today's year/month
        today = datetime.today()
        return render_template(
            "income/form.html",
            current_year=today.year,
            current_month=today.month,
        )

    # ==================================================================
    # ROUTE: Monthly Income Summary
    # ==================================================================
    @app.route("/income/<int:year>/<int:month>")
    def income_month_view(year, month):
        user = get_current_user()

        entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .order_by(IncomeWeek.week_index)
            .all()
        )

        total_gross = sum(e.gross for e in entries)
        total_net = sum(e.net for e in entries)
        total_tax = total_gross - total_net

        return render_template(
            "income/month_view.html",
            year=year,
            month=month,
            entries=entries,
            total_gross=total_gross,
            total_net=total_net,
            total_tax=total_tax,
        )
    
    # ==================================================================
    # ROUTE: EXPENSES
    # ==================================================================
    @app.route("/expenses/select")
    def expenses_select_month():
        today = datetime.today()
        return render_template(
            "expenses/select_month.html",
            current_year=today.year,
            current_month=today.month,
        )
    
    # ==================================================================
    # ROUTE: Expenses (Redirect after selecting Month/Year for EXPENSES)
    # ==================================================================
    @app.route("/expenses/view")
    def expenses_view_redirect():
        from flask import flash

        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("expenses_select_month"))

        return redirect(url_for("expenses_month_view", year=year, month=month))

    # ==================================================================
    # ROUTE: Expenses (Monthly Expenses Summary)
    # ==================================================================
    @app.route("/expenses/<int:year>/<int:month>", methods=["GET", "POST"])
    def expenses_month_view(year, month):
        user = get_current_user()

        # --------------------------
        # 1) Pull income totals FIRST
        # --------------------------
        income_entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .all()
        )
        total_gross = sum(e.gross for e in income_entries)
        total_net = sum(e.net for e in income_entries)

        # --------------------------
        # 2) If user submits expenses
        # --------------------------
        if request.method == "POST":
            """
            When the user clicks "Save Expenses", the browser submits ALL rows.

            Because your inputs are named item[] and cost[], Flask gives us two lists:
                items = ["Rent", "Groceries", "", ...]
                costs = ["1200", "250.40", "", ...]

            The saving strategy you’re using is:
            1) Delete the month’s existing rows
            2) Rebuild them from what the user submitted

            This is simple and predictable, and it matches a spreadsheet-style UI.
            """

            from flask import flash

            items = request.form.getlist("item[]")
            costs = request.form.getlist("cost[]")

            # -------------------------------
            # Validation rules we will enforce
            # -------------------------------
            # Rule 1: blank row = ignore
            # Rule 2: item but no cost = warning + ignore
            # Rule 3: cost but no item = warning + ignore
            # Rule 4: cost must be a valid number >= 0
            # Rule 5: we store costs rounded to 2 decimals

            cleaned_rows = []
            warnings = 0

            for idx, (item, cost) in enumerate(zip(items, costs), start=1):
                item = (item or "").strip()
                cost = (cost or "").strip()

                # Completely blank row → skip silently
                if not item and not cost:
                    continue

                # If user typed an item but forgot cost
                if item and not cost:
                    warnings += 1
                    continue

                # If user typed a cost but forgot item
                if cost and not item:
                    warnings += 1
                    continue

                # Now we have both fields → validate cost
                try:
                    cost_value = float(cost)
                except ValueError:
                    warnings += 1
                    continue

                if cost_value < 0:
                    warnings += 1
                    continue

                # Round to cents so you don’t get float garbage like 12.999999
                cost_value = round(cost_value, 2)

                cleaned_rows.append((item, cost_value))

            # If everything was empty, still allow saving (it just clears the month)
            # But we’ll give a helpful message.
            if not cleaned_rows:
                flash("No valid expense rows found. Month cleared (if it had any saved rows).", "warning")

            # Warn the user if we skipped rows due to invalid input
            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")
            else:
                flash("Expenses saved successfully.", "success")

            # -------------------------------
            # Now persist to the database
            # -------------------------------
            # Clear old expenses for that month
            Expense.query.filter_by(user_id=user.id, year=year, month=month).delete()

            # Insert cleaned rows
            for item, cost_value in cleaned_rows:
                db.session.add(Expense(
                    user_id=user.id,
                    year=year,
                    month=month,
                    item=item,
                    cost=cost_value
                ))

            db.session.commit()

            # Redirect after POST (prevents re-submission if user refreshes)
            return redirect(url_for("expenses_month_view", year=year, month=month))


        # --------------------------
        # 3) GET: show page
        # --------------------------
        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month)
            .order_by(Expense.id)
            .all()
        )

        total_spent = sum(x.cost for x in expenses)
        money_left = total_net - total_spent  # ✅ net is the base

        return render_template(
            "expenses/month_view.html",
            year=year,
            month=month,
            total_gross=total_gross,
            total_net=total_net,
            expenses=expenses,
            total_spent=total_spent,
            money_left=money_left
        )

                          

    
    # ==================================================================
    # ROUTE: Settings (Theme selection etc.)
    # ==================================================================
    @app.route("/settings")
    def settings():
        """
        Settings page.
        Right now it only contains theme selection UI, but later we can add:
        - account settings
        - partner mode
        - currency preferences
        - notification preferences
        """
        return render_template("settings.html")

    # ==================================================================
    # ROUTE: Delete a single week's entry
    # ==================================================================
    @app.route("/income/delete/<int:week_id>", methods=["POST"])
    def delete_week(week_id):
        from flask import flash

        entry = IncomeWeek.query.get_or_404(week_id)
        year = entry.year
        month = entry.month

        db.session.delete(entry)
        db.session.commit()

        flash(f"Week {entry.week_index} deleted successfully.", "success")
        return redirect(url_for("income_month_view", year=year, month=month))

    # ==================================================================
    # ROUTE: Reset ALL income data
    # ==================================================================
    @app.route("/income/reset", methods=["POST"])
    def reset_income():
        from flask import flash

        user = get_current_user()
        IncomeWeek.query.filter_by(user_id=user.id).delete()
        db.session.commit()

        flash("All income data has been reset.", "warning")
        return redirect(url_for("income_select_month"))

    # ==================================================================
    # ROUTE: Select a Month/Year
    # ==================================================================
    @app.route("/income/select")
    def income_select_month():
        today = datetime.today()
        return render_template(
            "income/select_month.html",
            current_year=today.year,
            current_month=today.month,
        )

    # ==================================================================
    # ROUTE: Redirect after selecting Month/Year
    # ==================================================================
    @app.route("/income/view")
    def income_view_redirect():
        from flask import flash

        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("income_select_month"))

        return redirect(url_for("income_month_view", year=year, month=month))

    return app


# ======================================================================
# Run the app directly
# ======================================================================
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
