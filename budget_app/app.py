"""
app.py

Main Flask application for your budgeting app.

High-Level Flow:
--------------------------------------------------------------------
1. Create Flask app instance
2. Load config (DB path, secret key, etc.)
3. Initialize SQLAlchemy (db) and Flask-Migrate (migrate)
4. Create tables (dev-only convenience)
5. Define helper functions (get_current_user)
6. Define routes
"""

# --------------------------
# Imports
# --------------------------
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate

from config import Config
from models import db, User, IncomeWeek, Expense, SavingsAllocation


# ======================================================================
# APPLICATION FACTORY FUNCTION
# ======================================================================
def create_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Connect SQLAlchemy to app
    db.init_app(app)

    # Hook Alembic migrations to this Flask app + db
    Migrate(app, db)

    # Create tables + default user if needed (OK for early dev; later remove)
    with app.app_context():
        db.create_all()
        if not User.query.first():
            dummy_user = User(email="you@example.com")
            db.session.add(dummy_user)
            db.session.commit()

    # --------------------------------------------------------------
    # Helper: current user (dummy for now)
    # --------------------------------------------------------------
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
                flash(f"Week {week_index} for {month}/{year} already exists.", "error")
                return redirect(url_for("income_month_view", year=year, month=month))

            gross = hourly * hours
            net = gross * (1 - tax_percent / 100.0)

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
    # ROUTE: EXPENSES - Select Month
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
    # ROUTE: EXPENSES - Redirect after selecting Month/Year
    # IMPORTANT: this endpoint name MUST match your templates:
    #   url_for("expenses_view_redirect")
    # ==================================================================
    @app.route("/expenses/view")
    def expenses_view_redirect():
        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("expenses_select_month"))

        return redirect(url_for("expenses_month_view", year=int(year), month=int(month)))

    # ==================================================================
    # ROUTE: EXPENSES - Month View (Spreadsheet-like)
    # ==================================================================
    @app.route("/expenses/<int:year>/<int:month>", methods=["GET", "POST"])
    def expenses_month_view(year, month):
        user = get_current_user()

        # --------------------------------------------------------------
        # 1) Pull income totals FIRST (for Money Left calculation)
        # --------------------------------------------------------------
        income_entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .all()
        )
        total_gross = sum(e.gross for e in income_entries)
        total_net = sum(e.net for e in income_entries)

        # --------------------------------------------------------------
        # 2) POST: Save Expenses (3B - "do NOT delete, soft-delete instead")
        # --------------------------------------------------------------
        if request.method == "POST":
            """
            The form submits 4 parallel lists (row index is the key):
              - expense_id[]   (hidden input; blank for new rows)
              - category[]     (dropdown)
              - description[]  (free text)
              - cost[]         (money)

            New behavior (3B):
              - If expense_id exists -> update that row
              - If expense_id blank  -> create new row
              - Any previously-active rows NOT included in the submission
                -> soft-delete (is_active=False, deleted_at timestamp)
            """

            expense_ids = request.form.getlist("expense_id[]")
            categories = request.form.getlist("category[]")
            descriptions = request.form.getlist("description[]")
            costs = request.form.getlist("cost[]")

            # Load all currently-active expenses for that month into a dict by id
            existing_active = (
                Expense.query
                .filter_by(user_id=user.id, year=year, month=month, is_active=True)
                .order_by(Expense.id)
                .all()
            )
            existing_by_id = {str(e.id): e for e in existing_active}

            now = datetime.utcnow()
            submitted_ids = set()     # expense IDs we updated/kept
            warnings = 0
            saved_count = 0

            # Loop row-by-row (keep row alignment using zip)
            for row_idx, (eid, category, description, cost) in enumerate(
                zip(expense_ids, categories, descriptions, costs),
                start=1
            ):
                eid = (eid or "").strip()
                if eid:
                    submitted_ids.add(eid)
                category = (category or "").strip() or None
                description = (description or "").strip() or None
                cost = (cost or "").strip()

                # Blank row: skip
                if (not eid) and (category is None) and (description is None) and (cost == ""):
                    continue

                # Must have a cost if anything else is filled
                if cost == "":
                    warnings += 1
                    continue

                try:
                    cost_value = float(cost)
                except ValueError:
                    warnings += 1
                    continue

                if cost_value < 0:
                    warnings += 1
                    continue

                cost_value = round(cost_value, 2)

                # Require at least category OR description so analytics isn't garbage
                if category is None and description is None:
                    warnings += 1
                    continue

                # --------------------------
                # UPDATE existing row
                # --------------------------
                if eid and eid in existing_by_id:
                    exp = existing_by_id[eid]
                    exp.category = category
                    exp.description = description
                    exp.cost = cost_value
                    exp.is_active = True
                    exp.deleted_at = None

                    # If your model has updated_at, keep this:
                    if hasattr(exp, "updated_at"):
                        exp.updated_at = now

                    
                    saved_count += 1
                    continue

                # --------------------------
                # CREATE new row
                # --------------------------
                new_exp = Expense(
                    user_id=user.id,
                    year=year,
                    month=month,
                    category=category,
                    description=description,
                    cost=cost_value,
                    is_active=True,
                    deleted_at=None,
                )

                # If your model has created_at/updated_at, keep these:
                if hasattr(new_exp, "created_at") and new_exp.created_at is None:
                    new_exp.created_at = now
                if hasattr(new_exp, "updated_at"):
                    new_exp.updated_at = now

                db.session.add(new_exp)
                saved_count += 1

            # --------------------------------------------------------------
            # Soft-delete anything that was previously active but NOT submitted
            # --------------------------------------------------------------
            for exp in existing_active:
                exp_id_str = str(exp.id)
                if exp_id_str not in submitted_ids:
                    exp.is_active = False
                    exp.deleted_at = now
                    if hasattr(exp, "updated_at"):
                        exp.updated_at = now

            db.session.commit()

            # UI messages
            if saved_count == 0:
                flash("No valid expense rows found. Nothing saved.", "warning")
            else:
                flash(f"Saved {saved_count} expense row(s).", "success")

            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")

            return redirect(url_for("expenses_month_view", year=year, month=month))

        # --------------------------------------------------------------
        # 3) GET: show page
        # --------------------------------------------------------------
        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .order_by(Expense.id)
            .all()
        )

        total_spent = sum(x.cost for x in expenses)
        money_left = total_net - total_spent

        # Category dropdown list
        expense_categories = [
            # Housing & Utilities
            "Electricity Bill",
            "Homeowners/Renters Insurance",
            "Internet",
            "Rent/Mortgage",
            "Utilities",
            "Water Bill",

            # Food & Dining
            "Eating Out",
            "Groceries",

            # Transportation
            "Car Insurance",
            "Car Payment",
            "Gas",
            "Motorcycle Insurance",
            "Motorcycle Payment",
            "Transportation",

            # Health & Medical
            "Dental Insurance",
            "Disability Insurance",
            "Health Insurance",
            "Long-term Care Insurance",
            "Medical",
            "Vision Insurance",

            # Insurance (Non-Health)
            "Liability Insurance",
            "Life Insurance",

            # Pets
            "Pet Care",
            "Pet Food",
            "Pet Insurance",
            "Pet Surgery",

            # Personal & Lifestyle
            "Clothing",
            "Entertainment",
            "Gym Membership",
            "Subscriptions",

            # Education & Childcare
            "Childcare",
            "School",
            "Student Loans",

            # Debt & Financial
            "Credit Card Debt",
            "Credit Card Payments",
            "Debt",
            "Loans",

            # Misc
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
    # ROUTE: SAVINGS - Select Month
    # ==================================================================
    @app.route("/savings/select")
    def savings_select_month():
        """Shows a simple form that lets the user pick a month + year."""

        today = datetime.today()
        return render_template(
            "savings/select_month.html",
            current_year=today.year,
            current_month=today.month,
        )

    # ==================================================================
    # ROUTE: SAVINGS - Redirect after selecting Month/Year
    # IMPORTANT: we mirror the exact pattern used by /expenses/view
    # so templates can do url_for("savings_view_redirect").
    # ==================================================================
    @app.route("/savings/view")
    def savings_view_redirect():
        """Takes ?year=YYYY&month=MM and redirects to the month view."""

        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("savings_select_month"))

        return redirect(url_for("savings_month_view", year=int(year), month=int(month)))

    # ==================================================================
    # ROUTE: SAVINGS - Month View (Spreadsheet-like)
    #
    # What this page does:
    #   1) Calculates money_left = (total net income) - (total active expenses)
    #   2) Lets the user allocate THAT money_left into savings buckets by percent
    #   3) Shows a live "$ amount" column for each percent
    #   4) Persists allocations to the database (just like expenses)
    # ==================================================================
    @app.route("/savings/<int:year>/<int:month>", methods=["GET", "POST"])
    def savings_month_view(year, month):
        """Savings page: allocate leftover money from expenses using percentages."""

        user = get_current_user()

        # --------------------------------------------------------------
        # 1) Calculate the "leftover" money for this month
        # --------------------------------------------------------------
        # We reuse the exact logic you already trust on the Expenses page:
        #   - sum monthly NET income
        #   - subtract all ACTIVE expenses
        # The result is the budget amount available for savings allocations.

        income_entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .all()
        )
        total_net = sum(e.net for e in income_entries)

        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .all()
        )
        total_spent = sum(x.cost for x in expenses)

        # This is the base amount that the Savings table allocates.
        money_left = total_net - total_spent

        # --------------------------------------------------------------
        # 2) POST: Save Savings Allocations (mirrors expenses save logic)
        # --------------------------------------------------------------
        if request.method == "POST":
            """
            The Savings form submits 4 parallel lists (row alignment matters):
              - allocation_id[]  (hidden input; blank for new rows)
              - bucket[]         (dropdown)
              - name[]           (free text w/ suggestions)
              - percent[]        (percent 0-100)

            Save behavior (copy of Expenses rules):
              - If allocation_id exists -> update that row
              - If allocation_id blank  -> create new row
              - Any previously-active rows NOT included in the submission
                -> soft-delete (is_active=False + deleted_at timestamp)

            NOTE: We store ONLY the percent.
                  The dollar amount is derived live from `money_left`.
            """

            allocation_ids = request.form.getlist("allocation_id[]")
            buckets = request.form.getlist("bucket[]")
            names = request.form.getlist("name[]")
            percents = request.form.getlist("percent[]")

            existing_active = (
                SavingsAllocation.query
                .filter_by(user_id=user.id, year=year, month=month, is_active=True)
                .order_by(SavingsAllocation.id)
                .all()
            )
            existing_by_id = {str(a.id): a for a in existing_active}

            now = datetime.utcnow()
            submitted_ids = set()
            warnings = 0
            saved_count = 0
            # NEW: track total percent for this submission
            total_percent_submitted = 0.0

            for row_idx, (aid, bucket, name, percent) in enumerate(
                zip(allocation_ids, buckets, names, percents),
                start=1
            ):
                # Normalize inputs (strip whitespace, convert blanks -> None)
                aid = (aid or "").strip()
                if aid:
                    submitted_ids.add(aid)

                bucket = (bucket or "").strip() or None
                name = (name or "").strip() or None
                percent = (percent or "").strip()

                # Completely blank row: skip
                if (not aid) and (bucket is None) and (name is None) and (percent == ""):
                    continue

                # If the user started a row, we REQUIRE a percent.
                if percent == "":
                    warnings += 1
                    continue

                try:
                    percent_value = float(percent)
                except ValueError:
                    warnings += 1
                    continue

                # Basic validation for sanity + UI consistency
                if percent_value < 0 or percent_value > 100:
                    warnings += 1
                    continue

                percent_value = round(percent_value, 2)

                # NEW: add to total percent as we accept rows
                total_percent_submitted += percent_value

                # NEW: if we exceed 100 at any point, stop and do NOT save anything
                if total_percent_submitted > 100:
                    flash("Savings allocations cannot exceed 100%. Please lower your percentages.", "error")
                    return redirect(url_for("savings_month_view", year=year, month=month))

                # Require at least bucket OR name so analytics isn't garbage
                if bucket is None and name is None:
                    warnings += 1
                    continue

                # --------------------------
                # UPDATE existing row
                # --------------------------
                if aid and aid in existing_by_id:
                    alloc = existing_by_id[aid]
                    alloc.bucket = bucket
                    alloc.name = name
                    alloc.percent = percent_value
                    alloc.is_active = True
                    alloc.deleted_at = None
                    alloc.updated_at = now
                    saved_count += 1
                    continue

                # --------------------------
                # CREATE new row
                # --------------------------
                new_alloc = SavingsAllocation(
                    user_id=user.id,
                    year=year,
                    month=month,
                    bucket=bucket,
                    name=name,
                    percent=percent_value,
                    is_active=True,
                    deleted_at=None,
                )
                new_alloc.created_at = now
                new_alloc.updated_at = now
                db.session.add(new_alloc)
                saved_count += 1

            # Soft-delete anything that used to be active but wasn't submitted
            for alloc in existing_active:
                alloc_id_str = str(alloc.id)
                if alloc_id_str not in submitted_ids:
                    alloc.is_active = False
                    alloc.deleted_at = now
                    alloc.updated_at = now

            db.session.commit()

            if saved_count == 0:
                flash("No valid savings rows found. Nothing saved.", "warning")
            else:
                flash(f"Saved {saved_count} savings row(s).", "success")

            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")

            return redirect(url_for("savings_month_view", year=year, month=month))

        # --------------------------------------------------------------
        # 3) GET: show page
        # --------------------------------------------------------------
        allocations = (
            SavingsAllocation.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .order_by(SavingsAllocation.id)
            .all()
        )

        # Total percent allocated (used to compute totals)
        total_percent = sum(a.percent for a in allocations)

        # Dollar totals are derived from the current money_left.
        # (If expenses change later, savings amounts update automatically.)
        total_saved = money_left * (total_percent / 100.0)
        savings_leftover = money_left - total_saved

        # Dropdown buckets (customize these anytime)
        savings_buckets = [
            "Emergency Fund",
            "Retirement",
            "Brokerage / Investing",
            "Debt Payoff",
            "Big Purchase Fund",
            "Travel Fund",
            "Other",
        ]

        # For the "name" field suggestions, we pull prior names by bucket.
        # We ship this to the template so it can populate <datalist> options.
        existing_names_by_bucket = {}
        for b in savings_buckets:
            names_for_bucket = (
                db.session.query(SavingsAllocation.name)
                .filter(
                    SavingsAllocation.user_id == user.id,
                    SavingsAllocation.bucket == b,
                    SavingsAllocation.name.isnot(None),
                )
                .distinct()
                .order_by(SavingsAllocation.name)
                .all()
            )
            existing_names_by_bucket[b] = [n[0] for n in names_for_bucket]

        return render_template(
            "savings/month_view.html",
            year=year,
            month=month,
            total_net=total_net,
            total_spent=total_spent,
            money_left=money_left,
            allocations=allocations,
            total_percent=total_percent,
            total_saved=total_saved,
            savings_leftover=savings_leftover,
            savings_buckets=savings_buckets,
            existing_names_by_bucket=existing_names_by_bucket,
        )


    # ==================================================================
    # ROUTE: Settings
    # ==================================================================
    @app.route("/settings")
    def settings():
        return render_template("settings.html")

    # ==================================================================
    # ROUTE: Delete a single week's entry
    # ==================================================================
    @app.route("/income/delete/<int:week_id>", methods=["POST"])
    def delete_week(week_id):
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
        user = get_current_user()
        IncomeWeek.query.filter_by(user_id=user.id).delete()
        db.session.commit()

        flash("All income data has been reset.", "warning")
        return redirect(url_for("income_select_month"))

    # ==================================================================
    # ROUTE: Select a Month/Year (Income)
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
    # ROUTE: Redirect after selecting Month/Year (Income)
    # ==================================================================
    @app.route("/income/view")
    def income_view_redirect():
        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("income_select_month"))

        return redirect(url_for("income_month_view", year=int(year), month=int(month)))

    return app


# ======================================================================
# Run the app directly
# ======================================================================
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
