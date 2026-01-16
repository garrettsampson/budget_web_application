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
from models import (
    db,
    User,
    IncomeWeek,
    Expense,
    SavingsAllocation,
    ExpenseBucketOption,
    ExpenseMerchantOption,
    SavingsBucketOption,
    SavingsNameOption,
)


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
    
    # ===================================================================
    # API: Delete custom dropdown options (soft-delete)
    # ===================================================================

    @app.post("/api/expenses/bucket/delete/<int:opt_id>")
    def api_delete_expense_bucket(opt_id):
        user = get_current_user()

        opt = ExpenseBucketOption.query.filter_by(
            id=opt_id, user_id=user.id, is_active=True
        ).first()

        if not opt:
            return {"ok": False, "error": "Bucket option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}


    @app.post("/api/expenses/merchant/delete/<int:opt_id>")
    def api_delete_expense_merchant(opt_id):
        user = get_current_user()

        opt = ExpenseMerchantOption.query.filter_by(
            id=opt_id, user_id=user.id, is_active=True
        ).first()

        if not opt:
            return {"ok": False, "error": "Merchant option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}


    @app.post("/api/savings/bucket/delete/<int:opt_id>")
    def api_delete_savings_bucket(opt_id):
        user = get_current_user()

        opt = SavingsBucketOption.query.filter_by(
            id=opt_id, user_id=user.id, is_active=True
        ).first()

        if not opt:
            return {"ok": False, "error": "Bucket option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}


    @app.post("/api/savings/name/delete/<int:opt_id>")
    def api_delete_savings_name(opt_id):
        user = get_current_user()

        opt = SavingsNameOption.query.filter_by(
            id=opt_id, user_id=user.id, is_active=True
        ).first()

        if not opt:
            return {"ok": False, "error": "Name option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}


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

        # ------------------------------------------------------------------
        # 1) Compute totals (same as before)
        # ------------------------------------------------------------------
        income_entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .all()
        )
        total_gross = sum(e.gross for e in income_entries)
        total_net = sum(e.net for e in income_entries)

        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .order_by(Expense.id)
            .all()
        )
        total_spent = sum(x.cost for x in expenses)
        money_left = total_net - total_spent

        # ------------------------------------------------------------------
        # 2) Built-in bucket list (your default dropdown options)
        #     - Keep this list as your "base" categories.
        #     - Custom buckets get appended from DB.
        # ------------------------------------------------------------------
        builtin_expense_buckets = [
            "Subscriptions",
            "Utilities",
            "Groceries",
            "Eating Out",
            "Gas",
            "Car",
            "Rent / Mortgage",
            "Insurance",
            "Pet Care",
            "Health",
            "Shopping",
            "Entertainment",
            "Other",
        ]

        # ------------------------------------------------------------------
        # 3) Load custom options from DB (for dropdown reuse)
        # ------------------------------------------------------------------
        custom_expense_buckets = (
            ExpenseBucketOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(ExpenseBucketOption.label.asc())
            .all()
        )

        custom_bucket_id_to_label = {str(o.id): o.label for o in custom_expense_buckets}

        custom_merchants = (
            ExpenseMerchantOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(ExpenseMerchantOption.bucket_label.asc(), ExpenseMerchantOption.name.asc())
            .all()
        )

        # Build dict: bucket_label -> [{id, name}, ...]
        expense_merchants_by_bucket = {}
        for m in custom_merchants:
            expense_merchants_by_bucket.setdefault(m.bucket_label, []).append(
                {"id": m.id, "name": m.name}
            )

        # ------------------------------------------------------------------
        # 4) POST: Save expenses + auto-create new options when "Other…" used
        # ------------------------------------------------------------------
        if request.method == "POST":
            expense_ids = request.form.getlist("expense_id[]")
            bucket_selects = request.form.getlist("bucket_select[]")
            bucket_other_texts = request.form.getlist("bucket_other_text[]")
            merchant_selects = request.form.getlist("merchant_select[]")
            merchant_other_texts = request.form.getlist("merchant_other_text[]")
            costs = request.form.getlist("cost[]")

            existing_active = (
                Expense.query
                .filter_by(user_id=user.id, year=year, month=month, is_active=True)
                .order_by(Expense.id)
                .all()
            )
            existing_by_id = {str(e.id): e for e in existing_active}

            submitted_ids = set()
            now = datetime.utcnow()

            warnings = 0
            saved_count = 0

            for (eid, bsel, bother, msel, mother, cost_str) in zip(
                expense_ids, bucket_selects, bucket_other_texts, merchant_selects, merchant_other_texts, costs
            ):
                eid = (eid or "").strip()
                if eid:
                    submitted_ids.add(eid)

                bsel = (bsel or "").strip()
                bother = (bother or "").strip()
                msel = (msel or "").strip()
                mother = (mother or "").strip()
                cost_str = (cost_str or "").strip()

                # Skip fully blank row
                if (not eid) and (not bsel) and (not bother) and (not msel) and (not mother) and (cost_str == ""):
                    continue

                # Cost is required for a meaningful expense row
                if cost_str == "":
                    warnings += 1
                    continue

                try:
                    cost_val = float(cost_str)
                except ValueError:
                    warnings += 1
                    continue

                if cost_val < 0:
                    warnings += 1
                    continue

                cost_val = round(cost_val, 2)

                # ----------------------------------------------------------
                # Resolve BUCKET LABEL
                # ----------------------------------------------------------
                bucket_label = None

                if bsel == "__other__":
                    # User typed a new bucket label
                    if not bother:
                        warnings += 1
                        continue
                    bucket_label = bother

                    # Create reusable bucket option if it doesn't already exist
                    exists = ExpenseBucketOption.query.filter_by(
                        user_id=user.id, label=bucket_label, is_active=True
                    ).first()
                    if not exists:
                        db.session.add(ExpenseBucketOption(user_id=user.id, label=bucket_label))

                elif bsel.startswith("opt:"):
                    # Custom bucket selected
                    opt_id = bsel.split(":", 1)[1]
                    bucket_label = custom_bucket_id_to_label.get(opt_id)

                    if not bucket_label:
                        warnings += 1
                        continue

                else:
                    # Built-in bucket (or blank)
                    bucket_label = bsel or None

                # ----------------------------------------------------------
                # Resolve MERCHANT NAME (stored in Expense.description)
                # ----------------------------------------------------------
                merchant_name = None

                if msel == "__other__":
                    if not mother:
                        warnings += 1
                        continue
                    merchant_name = mother

                    # Create reusable merchant option if not exists, scoped to bucket_label
                    # NOTE: If bucket_label is None, we still allow it, but it won't be very useful.
                    scope_label = bucket_label or "Uncategorized"
                    exists = ExpenseMerchantOption.query.filter_by(
                        user_id=user.id, bucket_label=scope_label, name=merchant_name, is_active=True
                    ).first()
                    if not exists:
                        db.session.add(
                            ExpenseMerchantOption(
                                user_id=user.id,
                                bucket_label=scope_label,
                                name=merchant_name,
                            )
                        )

                elif msel.startswith("opt:"):
                    opt_id = msel.split(":", 1)[1]
                    opt = ExpenseMerchantOption.query.filter_by(
                        id=int(opt_id), user_id=user.id, is_active=True
                    ).first()
                    if not opt:
                        warnings += 1
                        continue
                    merchant_name = opt.name

                else:
                    # If merchant select is blank, allow merchant_other_text if user typed anyway (rare).
                    # Otherwise merchant stays None.
                    merchant_name = mother or None

                # If both bucket and merchant are missing, skip row (nothing to save)
                if bucket_label is None and (merchant_name is None or merchant_name.strip() == ""):
                    warnings += 1
                    continue

                # ----------------------------------------------------------
                # UPDATE or CREATE expense
                # ----------------------------------------------------------
                if eid and eid in existing_by_id:
                    exp = existing_by_id[eid]
                    exp.category = bucket_label
                    exp.description = merchant_name
                    exp.cost = cost_val
                    exp.updated_at = now
                    exp.is_active = True
                    exp.deleted_at = None
                    saved_count += 1
                else:
                    new_exp = Expense(
                        user_id=user.id,
                        year=year,
                        month=month,
                        category=bucket_label,
                        description=merchant_name,
                        cost=cost_val,
                        is_active=True,
                        deleted_at=None,
                    )
                    new_exp.created_at = now
                    new_exp.updated_at = now
                    db.session.add(new_exp)
                    saved_count += 1

            # Soft-delete anything that existed but wasn't submitted this time
            for exp in existing_active:
                if str(exp.id) not in submitted_ids:
                    exp.is_active = False
                    exp.deleted_at = now
                    exp.updated_at = now

            db.session.commit()

            if saved_count > 0:
                flash(f"Saved {saved_count} expense row(s).", "success")
            else:
                flash("No valid expense rows found. Nothing saved.", "warning")

            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")

            return redirect(url_for("expenses_month_view", year=year, month=month))

        # ------------------------------------------------------------------
        # 5) GET: Render template
        # ------------------------------------------------------------------
        return render_template(
            "expenses/month_view.html",
            year=year,
            month=month,
            total_gross=total_gross,
            total_net=total_net,
            expenses=expenses,
            total_spent=total_spent,
            money_left=money_left,
            builtin_expense_buckets=builtin_expense_buckets,
            custom_expense_buckets=custom_expense_buckets,
            expense_merchant_options_by_bucket_json=expense_merchants_by_bucket,
            expense_custom_bucket_id_to_label_json=custom_bucket_id_to_label,
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
        user = get_current_user()

        # --------------------------------------------------------------
        # Compute money_left (same as before)
        # --------------------------------------------------------------
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

        money_left = total_net - total_spent

        # --------------------------------------------------------------
        # Built-in savings buckets
        # --------------------------------------------------------------
        builtin_savings_buckets = [
            "Emergency Fund",
            "Retirement",
            "Investments",
            "Debt Payoff",
            "Big Purchase Fund",
            "Travel Fund",
            "Other",
        ]

        # --------------------------------------------------------------
        # Load custom bucket + name options
        # --------------------------------------------------------------
        custom_savings_buckets = (
            SavingsBucketOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(SavingsBucketOption.label.asc())
            .all()
        )
        custom_bucket_id_to_label = {str(o.id): o.label for o in custom_savings_buckets}

        custom_names = (
            SavingsNameOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(SavingsNameOption.bucket_label.asc(), SavingsNameOption.name.asc())
            .all()
        )
        names_by_bucket = {}
        for n in custom_names:
            names_by_bucket.setdefault(n.bucket_label, []).append({"id": n.id, "name": n.name})

        # --------------------------------------------------------------
        # POST save
        # --------------------------------------------------------------
        if request.method == "POST":
            allocation_ids = request.form.getlist("allocation_id[]")
            bucket_selects = request.form.getlist("bucket_select[]")
            bucket_other_texts = request.form.getlist("bucket_other_text[]")
            name_selects = request.form.getlist("name_select[]")
            name_other_texts = request.form.getlist("name_other_text[]")
            percents = request.form.getlist("percent[]")

            existing_active = (
                SavingsAllocation.query
                .filter_by(user_id=user.id, year=year, month=month, is_active=True)
                .order_by(SavingsAllocation.id)
                .all()
            )
            existing_by_id = {str(a.id): a for a in existing_active}

            submitted_ids = set()
            now = datetime.utcnow()

            warnings = 0
            saved_count = 0

            total_percent_submitted = 0.0

            for (aid, bsel, bother, nsel, nother, pstr) in zip(
                allocation_ids, bucket_selects, bucket_other_texts, name_selects, name_other_texts, percents
            ):
                aid = (aid or "").strip()
                if aid:
                    submitted_ids.add(aid)

                bsel = (bsel or "").strip()
                bother = (bother or "").strip()
                nsel = (nsel or "").strip()
                nother = (nother or "").strip()
                pstr = (pstr or "").strip()

                # Skip blank row
                if (not aid) and (not bsel) and (not bother) and (not nsel) and (not nother) and (pstr == ""):
                    continue

                if pstr == "":
                    warnings += 1
                    continue

                try:
                    pval = float(pstr)
                except ValueError:
                    warnings += 1
                    continue

                if pval < 0 or pval > 100:
                    warnings += 1
                    continue

                pval = round(pval, 2)
                total_percent_submitted += pval

                # HARD RULE: cannot exceed 100%
                if total_percent_submitted > 100:
                    flash("Savings allocations cannot exceed 100%. Please lower your percentages.", "error")
                    return redirect(url_for("savings_month_view", year=year, month=month))

                # Resolve bucket label
                bucket_label = None

                if bsel == "__other__":
                    if not bother:
                        warnings += 1
                        continue
                    bucket_label = bother

                    exists = SavingsBucketOption.query.filter_by(
                        user_id=user.id, label=bucket_label, is_active=True
                    ).first()
                    if not exists:
                        db.session.add(SavingsBucketOption(user_id=user.id, label=bucket_label))

                elif bsel.startswith("opt:"):
                    opt_id = bsel.split(":", 1)[1]
                    bucket_label = custom_bucket_id_to_label.get(opt_id)
                    if not bucket_label:
                        warnings += 1
                        continue
                else:
                    bucket_label = bsel or None

                # Resolve name
                name_value = None

                if nsel == "__other__":
                    if not nother:
                        warnings += 1
                        continue
                    name_value = nother

                    scope = bucket_label or "Uncategorized"
                    exists = SavingsNameOption.query.filter_by(
                        user_id=user.id, bucket_label=scope, name=name_value, is_active=True
                    ).first()
                    if not exists:
                        db.session.add(SavingsNameOption(user_id=user.id, bucket_label=scope, name=name_value))

                elif nsel.startswith("opt:"):
                    opt_id = nsel.split(":", 1)[1]
                    opt = SavingsNameOption.query.filter_by(
                        id=int(opt_id), user_id=user.id, is_active=True
                    ).first()
                    if not opt:
                        warnings += 1
                        continue
                    name_value = opt.name
                else:
                    name_value = nother or None

                if bucket_label is None and (name_value is None or name_value.strip() == ""):
                    warnings += 1
                    continue

                # Update or create allocation
                if aid and aid in existing_by_id:
                    alloc = existing_by_id[aid]
                    alloc.bucket = bucket_label
                    alloc.name = name_value
                    alloc.percent = pval
                    alloc.is_active = True
                    alloc.deleted_at = None
                    alloc.updated_at = now
                    saved_count += 1
                else:
                    new_alloc = SavingsAllocation(
                        user_id=user.id,
                        year=year,
                        month=month,
                        bucket=bucket_label,
                        name=name_value,
                        percent=pval,
                        is_active=True,
                        deleted_at=None,
                    )
                    new_alloc.created_at = now
                    new_alloc.updated_at = now
                    db.session.add(new_alloc)
                    saved_count += 1

            # Soft-delete removed rows
            for alloc in existing_active:
                if str(alloc.id) not in submitted_ids:
                    alloc.is_active = False
                    alloc.deleted_at = now
                    alloc.updated_at = now

            db.session.commit()

            if saved_count > 0:
                flash(f"Saved {saved_count} savings row(s).", "success")
            else:
                flash("No valid savings rows found. Nothing saved.", "warning")

            if warnings > 0:
                flash(f"Skipped {warnings} row(s) because they were incomplete or invalid.", "warning")

            return redirect(url_for("savings_month_view", year=year, month=month))

        # --------------------------------------------------------------
        # GET render
        # --------------------------------------------------------------
        allocations = (
            SavingsAllocation.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .order_by(SavingsAllocation.id)
            .all()
        )

        total_percent = sum(a.percent for a in allocations)
        total_saved = money_left * (total_percent / 100.0)
        savings_leftover = money_left - total_saved

        return render_template(
            "savings/month_view.html",
            year=year,
            month=month,
            money_left=money_left,
            allocations=allocations,
            builtin_savings_buckets=builtin_savings_buckets,
            custom_savings_buckets=custom_savings_buckets,
            savings_name_options_by_bucket_json=names_by_bucket,
            savings_custom_bucket_id_to_label_json=custom_bucket_id_to_label,
            total_percent=total_percent,
            total_saved=total_saved,
            savings_leftover=savings_leftover,
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
    

    # ===================================================================
    # API: Delete custom dropdown options (soft-delete)
    # ===================================================================

    @app.post("/api/expenses/bucket/delete/<int:opt_id>")
    def delete_expense_bucket(opt_id):
        user = get_current_user()
        opt = ExpenseBucketOption.query.filter_by(id=opt_id, user_id=user.id, is_active=True).first()
        if not opt:
            return {"ok": False, "error": "Not found"}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()
        return {"ok": True}


    @app.post("/api/expenses/merchant/delete/<int:opt_id>")
    def delete_expense_merchant(opt_id):
        user = get_current_user()
        opt = ExpenseMerchantOption.query.filter_by(id=opt_id, user_id=user.id, is_active=True).first()
        if not opt:
            return {"ok": False, "error": "Not found"}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()
        return {"ok": True}


    @app.post("/api/savings/bucket/delete/<int:opt_id>")
    def delete_savings_bucket(opt_id):
        user = get_current_user()
        opt = SavingsBucketOption.query.filter_by(id=opt_id, user_id=user.id, is_active=True).first()
        if not opt:
            return {"ok": False, "error": "Not found"}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()
        return {"ok": True}


    @app.post("/api/savings/name/delete/<int:opt_id>")
    def delete_savings_name(opt_id):
        user = get_current_user()
        opt = SavingsNameOption.query.filter_by(id=opt_id, user_id=user.id, is_active=True).first()
        if not opt:
            return {"ok": False, "error": "Not found"}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()
        return {"ok": True}


    return app


# ======================================================================
# Run the app directly
# ======================================================================
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
