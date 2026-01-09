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
from flask_migrate import Migrate

# Import your database models
from models import db, User, IncomeWeek, Expense

# Import configuration settings (DB path, secret key, etc.)
from config import Config

# Used for automatically filling the form with today's year/month
from datetime import datetime





# ======================================================================
# APPLICATION FACTORY FUNCTION
# ======================================================================
def create_app():
    """Creates and configures the Flask application."""

    app = Flask(__name__)
    app.config.from_object(Config)

    # Connect SQLAlchemy "db" to this Flask app
    db.init_app(app)
    # Hook Alembic migrations to this Flask app + db
    migrate = Migrate(app, db)

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

            IMPORTANT:
            We now submit 3 parallel lists:
              - category[]     (dropdown choice)
              - description[]  (free-text details)
              - cost[]         (money)

            Our save strategy (for now) is still:
              1) Delete this month’s existing rows
              2) Insert rows based on the current form submission

            Later (when you add migrations and IDs per row), we can do true updates
            without a delete/reinsert — but this is fine early-stage.
            """

            from flask import flash

            # Pull the three lists (same row index across lists)
            categories = request.form.getlist("category[]")
            descriptions = request.form.getlist("description[]")
            costs = request.form.getlist("cost[]")

            cleaned_rows = []
            warnings = 0

            # Zip all three together so row 1 stays row 1 across category/description/cost
            for idx, (category, description, cost) in enumerate(zip(categories, descriptions, costs), start=1):
                category = (category or "").strip()
                description = (description or "").strip()
                cost = (cost or "").strip()

                # Normalize "Pick…" / blank dropdown → treat as empty
                # (Your HTML uses value="" for Pick…)
                if category == "":
                    category = None

                # Normalize blank description → empty
                if description == "":
                    description = None

                # Completely blank row → skip silently
                if category is None and description is None and cost == "":
                    continue

                # If they typed something but forgot cost → warning, skip
                if cost == "":
                    warnings += 1
                    continue

                # Validate cost
                try:
                    cost_value = float(cost)
                except ValueError:
                    warnings += 1
                    continue

                if cost_value < 0:
                    warnings += 1
                    continue

                cost_value = round(cost_value, 2)

                # If they provided cost but BOTH category and description are empty,
                # we consider that invalid (otherwise analytics later is messy).
                if category is None and description is None:
                    warnings += 1
                    continue

                cleaned_rows.append((category, description, cost_value))

            # Feedback messages
            if not cleaned_rows:
                flash("No valid expense rows found. Month cleared (if it had any saved rows).", "warning")
            else:
                flash("Expenses saved successfully.", "success")

            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")

            # Persist
            Expense.query.filter_by(user_id=user.id, year=year, month=month).delete()

            for category, description, cost_value in cleaned_rows:
                db.session.add(Expense(
                    user_id=user.id,
                    year=year,
                    month=month,
                    category=category,
                    description=description,
                    cost=cost_value
                ))

            db.session.commit()

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

        # ------------------------------------------------------------
        # Expense category dropdown choices (for the UI)
        # ------------------------------------------------------------
        # We are keeping this as a simple Python list for now.
        # Later, we can move it into the database so each user can customize it.
        expense_categories = [

            # ----------------------------
            # Housing & Utilities
            # ----------------------------
            "Electricity Bill",
            "Homeowners/Renters Insurance",
            "Internet",
            "Rent/Mortgage",
            "Utilities",
            "Water Bill",

            # ----------------------------
            # Food & Dining
            # ----------------------------
            "Eating Out",
            "Groceries",

            # ----------------------------
            # Transportation (Vehicles & Fuel)
            # ----------------------------
            "Car Insurance",
            "Car Payment",
            "Gas",
            "Motorcycle Insurance",
            "Motorcycle Payment",
            "Transportation",

            # ----------------------------
            # Health & Medical
            # ----------------------------
            "Dental Insurance",
            "Disability Insurance",
            "Health Insurance",
            "Long-term Care Insurance",
            "Medical",
            "Vision Insurance",

            # ----------------------------
            # Insurance (Non-Health)
            # ----------------------------
            "Liability Insurance",
            "Life Insurance",

            # ----------------------------
            # Pets
            # ----------------------------
            "Pet Care",
            "Pet Food",
            "Pet Insurance",
            "Pet Surgery",

            # ----------------------------
            # Personal & Lifestyle
            # ----------------------------
            "Clothing",
            "Entertainment",
            "Gym Membership",
            "Subscriptions",

            # ----------------------------
            # Education & Childcare
            # ----------------------------
            "Childcare",
            "School",
            "Student Loans",

            # ----------------------------
            # Debt & Financial Obligations
            # ----------------------------
            "Credit Card Debt",
            "Credit Card Payments",
            "Debt",
            "Loans",

            # ----------------------------
            # Miscellaneous
            # ----------------------------
            "Other",
        ]



        return render_template(
            "expenses/month_view.html",
            year=year,
            month=month,
            total_gross=total_gross,
            total_net=total_net,
            expenses=expenses,
            total_spent=total_spent,
            money_left=money_left,
            expense_categories=expense_categories,
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
