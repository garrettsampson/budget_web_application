"""
app.py

Main Flask application for your budgeting app.

Now includes:
- Real user registration
- Login/logout
- Session-based current user
- Route protection so users only access their own budget data
"""

from datetime import datetime, date
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from models import (
    db,
    User,
    IncomeWeek,
    Paycheck,
    Expense,
    SavingsAllocation,
    ExpenseBucketOption,
    ExpenseMerchantOption,
    SavingsBucketOption,
    SavingsNameOption,
)


def create_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    Migrate(app, db)

    # IMPORTANT:
    # We are NOT using db.create_all() anymore.
    # Database structure should now be handled with:
    #   flask db migrate
    #   flask db upgrade

    # --------------------------------------------------------------
    # Helper: current logged-in user
    # --------------------------------------------------------------
    def get_current_user():
        """
        Returns the logged-in user based on session["user_id"].

        If nobody is logged in, returns None.

        This replaces the old dummy behavior:
            return User.query.first()

        Why this matters:
        - Every user's income/expenses/savings are tied to user_id.
        - If we always returned the first user, everyone would share data.
        """
        user_id = session.get("user_id")

        if not user_id:
            return None

        return User.query.get(user_id)

    # --------------------------------------------------------------
    # Decorator: require login before accessing a route
    # --------------------------------------------------------------
    def login_required(view_func):
        """
        Protects routes that should only be available after login.

        If the user is not logged in:
        - show a message
        - redirect them to /login
        """

        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if get_current_user() is None:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))

            return view_func(*args, **kwargs)

        return wrapped_view

    # ==================================================================
    # ROUTE: Register
    # ==================================================================
    @app.route("/register", methods=["GET", "POST"])
    def register():
        """
        Creates a new user account.

        Form fields expected:
        - email
        - password
        - confirm_password
        """

        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            confirm_password = request.form.get("confirm_password") or ""

            if not email:
                flash("Email is required.", "error")
                return redirect(url_for("register"))

            if not password:
                flash("Password is required.", "error")
                return redirect(url_for("register"))

            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return redirect(url_for("register"))

            existing_user = User.query.filter_by(email=email).first()

            if existing_user:
                flash("An account with that email already exists. Please log in.", "error")
                return redirect(url_for("login"))

            new_user = User(
                email=email,
                password_hash=generate_password_hash(password),
            )

            db.session.add(new_user)
            db.session.commit()

            session["user_id"] = new_user.id
            flash("Account created successfully.", "success")

            return redirect(url_for("home"))

        return render_template("auth/register.html")

    # ==================================================================
    # ROUTE: Login
    # ==================================================================
    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        Logs in an existing user.

        Form fields expected:
        - email
        - password
        """

        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""

            user = User.query.filter_by(email=email).first()

            if not user or not user.password_hash:
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            if not check_password_hash(user.password_hash, password):
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            session["user_id"] = user.id
            flash("Logged in successfully.", "success")

            return redirect(url_for("home"))

        return render_template("auth/login.html")

    # ==================================================================
    # ROUTE: Logout
    # ==================================================================
    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out successfully.", "success")
        return redirect(url_for("login"))

    # ==================================================================
    # ROUTE: Home Dashboard
    # ==================================================================
    @app.route("/")
    @login_required
    def home():
        return render_template("dashboard.html")

    # ==================================================================
    # ROUTE: Weekly Income Form
    # ==================================================================
# ==================================================================
    # ROUTE: Paycheck Income Form
    # ==================================================================
    @app.route("/income", methods=["GET", "POST"])
    @login_required
    def income_form():
        user = get_current_user()

        def parse_optional_float(value):
            value = (value or "").strip()
            if value == "":
                return None
            return float(value)

        def parse_optional_date(value):
            value = (value or "").strip()
            if value == "":
                return None
            return date.fromisoformat(value)

        if request.method == "POST":
            pay_date = date.fromisoformat(request.form["pay_date"])

            period_start = parse_optional_date(request.form.get("period_start"))
            period_end = parse_optional_date(request.form.get("period_end"))

            net_amount = float(request.form["net_amount"])

            gross_amount = parse_optional_float(request.form.get("gross_amount"))
            hours_worked = parse_optional_float(request.form.get("hours_worked"))
            hourly_rate = parse_optional_float(request.form.get("hourly_rate"))
            tax_withheld = parse_optional_float(request.form.get("tax_withheld"))

            pay_type = (request.form.get("pay_type") or "Paycheck").strip()
            notes = (request.form.get("notes") or "").strip() or None

            if net_amount < 0:
                flash("Net amount cannot be negative.", "error")
                return redirect(url_for("income_form"))

            paycheck = Paycheck(
                user_id=user.id,
                pay_date=pay_date,
                period_start=period_start,
                period_end=period_end,
                net_amount=round(net_amount, 2),
                gross_amount=round(gross_amount, 2) if gross_amount is not None else None,
                hours_worked=round(hours_worked, 2) if hours_worked is not None else None,
                hourly_rate=round(hourly_rate, 2) if hourly_rate is not None else None,
                tax_withheld=round(tax_withheld, 2) if tax_withheld is not None else None,
                pay_type=pay_type,
                notes=notes,
                updated_at=datetime.utcnow(),
            )

            db.session.add(paycheck)
            db.session.commit()

            return redirect(
                url_for(
                    "income_month_view",
                    year=pay_date.year,
                    month=pay_date.month,
                )
            )

        today = date.today()

        return render_template(
            "income/form.html",
            paycheck=None,
            today=today,
            current_year=today.year,
            current_month=today.month,
            form_mode="add",
        )
    # ===================================================================
    # API: Delete custom dropdown options
    # ===================================================================

    # ==================================================================
    # ROUTE: Edit a paycheck entry
    # ==================================================================
    @app.route("/income/edit/<int:paycheck_id>", methods=["GET", "POST"])
    @login_required
    def edit_paycheck(paycheck_id):
        """
        Allows the logged-in user to edit one paycheck.

        IMPORTANT:
        We filter by both:
          - paycheck id
          - current user id

        This prevents one user from editing another user's paycheck.
        """
        user = get_current_user()

        paycheck = Paycheck.query.filter_by(
            id=paycheck_id,
            user_id=user.id,
        ).first_or_404()

        def parse_optional_float(value):
            value = (value or "").strip()
            if value == "":
                return None
            return float(value)

        def parse_optional_date(value):
            value = (value or "").strip()
            if value == "":
                return None
            return date.fromisoformat(value)

        if request.method == "POST":
            pay_date = date.fromisoformat(request.form["pay_date"])

            period_start = parse_optional_date(request.form.get("period_start"))
            period_end = parse_optional_date(request.form.get("period_end"))

            net_amount = float(request.form["net_amount"])

            gross_amount = parse_optional_float(request.form.get("gross_amount"))
            hours_worked = parse_optional_float(request.form.get("hours_worked"))
            hourly_rate = parse_optional_float(request.form.get("hourly_rate"))
            tax_withheld = parse_optional_float(request.form.get("tax_withheld"))

            pay_type = (request.form.get("pay_type") or "Paycheck").strip()
            notes = (request.form.get("notes") or "").strip() or None

            if net_amount < 0:
                flash("Net amount cannot be negative.", "error")
                return redirect(url_for("edit_paycheck", paycheck_id=paycheck.id))

            paycheck.pay_date = pay_date
            paycheck.period_start = period_start
            paycheck.period_end = period_end
            paycheck.net_amount = round(net_amount, 2)
            paycheck.gross_amount = round(gross_amount, 2) if gross_amount is not None else None
            paycheck.hours_worked = round(hours_worked, 2) if hours_worked is not None else None
            paycheck.hourly_rate = round(hourly_rate, 2) if hourly_rate is not None else None
            paycheck.tax_withheld = round(tax_withheld, 2) if tax_withheld is not None else None
            paycheck.pay_type = pay_type
            paycheck.notes = notes
            paycheck.updated_at = datetime.utcnow()

            db.session.commit()

            flash("Paycheck updated successfully.", "success")

            return redirect(
                url_for(
                    "income_month_view",
                    year=paycheck.pay_date.year,
                    month=paycheck.pay_date.month,
                )
            )

        return render_template(
            "income/form.html",
            paycheck=paycheck,
            today=paycheck.pay_date,
            current_year=paycheck.pay_date.year,
            current_month=paycheck.pay_date.month,
            form_mode="edit",
        )

    @app.post("/api/expenses/bucket/delete/<int:opt_id>")
    @login_required
    def api_delete_expense_bucket(opt_id):
        user = get_current_user()

        opt = ExpenseBucketOption.query.filter_by(
            id=opt_id,
            user_id=user.id,
            is_active=True,
        ).first()

        if not opt:
            return {"ok": False, "error": "Bucket option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}

    @app.post("/api/expenses/merchant/delete/<int:opt_id>")
    @login_required
    def api_delete_expense_merchant(opt_id):
        user = get_current_user()

        opt = ExpenseMerchantOption.query.filter_by(
            id=opt_id,
            user_id=user.id,
            is_active=True,
        ).first()

        if not opt:
            return {"ok": False, "error": "Merchant option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}

    @app.post("/api/savings/bucket/delete/<int:opt_id>")
    @login_required
    def api_delete_savings_bucket(opt_id):
        user = get_current_user()

        opt = SavingsBucketOption.query.filter_by(
            id=opt_id,
            user_id=user.id,
            is_active=True,
        ).first()

        if not opt:
            return {"ok": False, "error": "Bucket option not found."}, 404

        opt.is_active = False
        opt.deleted_at = datetime.utcnow()
        db.session.commit()

        return {"ok": True}

    @app.post("/api/savings/name/delete/<int:opt_id>")
    @login_required
    def api_delete_savings_name(opt_id):
        user = get_current_user()

        opt = SavingsNameOption.query.filter_by(
            id=opt_id,
            user_id=user.id,
            is_active=True,
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
    @login_required
    def income_month_view(year, month):
        user = get_current_user()

        # Start/end date range for the selected month.
        # We count income by pay_date because that is when money is received.
        month_start = date(year, month, 1)

        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        paychecks = (
            Paycheck.query
            .filter(
                Paycheck.user_id == user.id,
                Paycheck.pay_date >= month_start,
                Paycheck.pay_date < next_month_start,
            )
            .order_by(Paycheck.pay_date.asc(), Paycheck.id.asc())
            .all()
        )

        total_gross = sum(p.gross_amount or 0 for p in paychecks)
        total_net = sum(p.net_amount for p in paychecks)
        total_tax = sum(p.tax_withheld or 0 for p in paychecks)
        total_hours = sum(p.hours_worked or 0 for p in paychecks)

        return render_template(
            "income/month_view.html",
            year=year,
            month=month,
            paychecks=paychecks,
            total_gross=total_gross,
            total_net=total_net,
            total_tax=total_tax,
            total_hours=total_hours,
        )

    # ==================================================================
    # ROUTE: EXPENSES - Select Month
    # ==================================================================
    @app.route("/expenses/select")
    @login_required
    def expenses_select_month():
        today = datetime.today()
        return render_template(
            "expenses/select_month.html",
            current_year=today.year,
            current_month=today.month,
        )

    # ==================================================================
    # ROUTE: EXPENSES - Redirect after selecting Month/Year
    # ==================================================================
    @app.route("/expenses/view")
    @login_required
    def expenses_view_redirect():
        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("expenses_select_month"))

        return redirect(url_for("expenses_month_view", year=int(year), month=int(month)))

    # ==================================================================
    # ROUTE: EXPENSES - Month View
    # ==================================================================
    @app.route("/expenses/<int:year>/<int:month>", methods=["GET", "POST"])
    @login_required
    def expenses_month_view(year, month):
        user = get_current_user()

        month_start = date(year, month, 1)

        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        paychecks = (
            Paycheck.query
            .filter(
                Paycheck.user_id == user.id,
                Paycheck.pay_date >= month_start,
                Paycheck.pay_date < next_month_start,
            )
            .all()
        )

        total_gross = sum(p.gross_amount or 0 for p in paychecks)
        total_net = sum(p.net_amount for p in paychecks)

        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .order_by(Expense.id)
            .all()
        )
        total_spent = sum(x.cost for x in expenses)
        money_left = total_net - total_spent

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
        ]

        custom_expense_buckets = (
            ExpenseBucketOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(ExpenseBucketOption.label.asc())
            .all()
        )

        custom_bucket_id_to_label = {
            str(o.id): o.label for o in custom_expense_buckets
        }

        custom_merchants = (
            ExpenseMerchantOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(
                ExpenseMerchantOption.bucket_label.asc(),
                ExpenseMerchantOption.name.asc(),
            )
            .all()
        )

        expense_merchants_by_bucket = {}
        for merchant in custom_merchants:
            expense_merchants_by_bucket.setdefault(
                merchant.bucket_label,
                [],
            ).append(
                {
                    "id": merchant.id,
                    "name": merchant.name,
                }
            )

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

            for eid, bsel, bother, msel, mother, cost_str in zip(
                expense_ids,
                bucket_selects,
                bucket_other_texts,
                merchant_selects,
                merchant_other_texts,
                costs,
            ):
                eid = (eid or "").strip()
                if eid:
                    submitted_ids.add(eid)

                bsel = (bsel or "").strip()
                bother = (bother or "").strip()
                msel = (msel or "").strip()
                mother = (mother or "").strip()
                cost_str = (cost_str or "").strip()

                if (
                    not eid
                    and not bsel
                    and not bother
                    and not msel
                    and not mother
                    and cost_str == ""
                ):
                    continue

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

                bucket_label = None

                if bsel == "__other__":
                    if not bother:
                        warnings += 1
                        continue

                    bucket_label = bother

                    exists = ExpenseBucketOption.query.filter_by(
                        user_id=user.id,
                        label=bucket_label,
                        is_active=True,
                    ).first()

                    if not exists:
                        db.session.add(
                            ExpenseBucketOption(
                                user_id=user.id,
                                label=bucket_label,
                            )
                        )

                elif bsel.startswith("opt:"):
                    opt_id = bsel.split(":", 1)[1]
                    bucket_label = custom_bucket_id_to_label.get(opt_id)

                    if not bucket_label:
                        warnings += 1
                        continue

                else:
                    bucket_label = bsel or None

                merchant_name = None

                if msel == "__other__":
                    if not mother:
                        warnings += 1
                        continue

                    merchant_name = mother
                    scope_label = bucket_label or "Uncategorized"

                    exists = ExpenseMerchantOption.query.filter_by(
                        user_id=user.id,
                        bucket_label=scope_label,
                        name=merchant_name,
                        is_active=True,
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
                        id=int(opt_id),
                        user_id=user.id,
                        is_active=True,
                    ).first()

                    if not opt:
                        warnings += 1
                        continue

                    merchant_name = opt.name

                else:
                    merchant_name = mother or None

                if bucket_label is None and (
                    merchant_name is None or merchant_name.strip() == ""
                ):
                    warnings += 1
                    continue

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
                flash(
                    f"Skipped {warnings} row(s) because they were incomplete or invalid.",
                    "warning",
                )

            return redirect(url_for("expenses_month_view", year=year, month=month))

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
    @login_required
    def savings_select_month():
        today = datetime.today()
        return render_template(
            "savings/select_month.html",
            current_year=today.year,
            current_month=today.month,
        )

    # ==================================================================
    # ROUTE: SAVINGS - Redirect after selecting Month/Year
    # ==================================================================
    @app.route("/savings/view")
    @login_required
    def savings_view_redirect():
        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("savings_select_month"))

        return redirect(url_for("savings_month_view", year=int(year), month=int(month)))

    # ==================================================================
    # ROUTE: SAVINGS - Month View
    # ==================================================================
    @app.route("/savings/<int:year>/<int:month>", methods=["GET", "POST"])
    @login_required
    def savings_month_view(year, month):
        user = get_current_user()

        month_start = date(year, month, 1)

        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        paychecks = (
            Paycheck.query
            .filter(
                Paycheck.user_id == user.id,
                Paycheck.pay_date >= month_start,
                Paycheck.pay_date < next_month_start,
            )
            .all()
        )

        total_net = sum(p.net_amount for p in paychecks)

        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .all()
        )
        total_spent = sum(x.cost for x in expenses)

        money_left = total_net - total_spent

        builtin_savings_buckets = [
            "Emergency Fund",
            "Retirement",
            "Investments",
            "Debt Payoff",
            "Big Purchase Fund",
            "Travel Fund",
        ]

        custom_savings_buckets = (
            SavingsBucketOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(SavingsBucketOption.label.asc())
            .all()
        )

        custom_bucket_id_to_label = {
            str(o.id): o.label for o in custom_savings_buckets
        }

        custom_names = (
            SavingsNameOption.query
            .filter_by(user_id=user.id, is_active=True)
            .order_by(
                SavingsNameOption.bucket_label.asc(),
                SavingsNameOption.name.asc(),
            )
            .all()
        )

        names_by_bucket = {}
        for name_option in custom_names:
            names_by_bucket.setdefault(
                name_option.bucket_label,
                [],
            ).append(
                {
                    "id": name_option.id,
                    "name": name_option.name,
                }
            )

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

            for aid, bsel, bother, nsel, nother, pstr in zip(
                allocation_ids,
                bucket_selects,
                bucket_other_texts,
                name_selects,
                name_other_texts,
                percents,
            ):
                aid = (aid or "").strip()
                if aid:
                    submitted_ids.add(aid)

                bsel = (bsel or "").strip()
                bother = (bother or "").strip()
                nsel = (nsel or "").strip()
                nother = (nother or "").strip()
                pstr = (pstr or "").strip()

                if (
                    not aid
                    and not bsel
                    and not bother
                    and not nsel
                    and not nother
                    and pstr == ""
                ):
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

                if total_percent_submitted > 100:
                    flash(
                        "Savings allocations cannot exceed 100%. Please lower your percentages.",
                        "error",
                    )
                    return redirect(url_for("savings_month_view", year=year, month=month))

                bucket_label = None

                if bsel == "__other__":
                    if not bother:
                        warnings += 1
                        continue

                    bucket_label = bother

                    exists = SavingsBucketOption.query.filter_by(
                        user_id=user.id,
                        label=bucket_label,
                        is_active=True,
                    ).first()

                    if not exists:
                        db.session.add(
                            SavingsBucketOption(
                                user_id=user.id,
                                label=bucket_label,
                            )
                        )

                elif bsel.startswith("opt:"):
                    opt_id = bsel.split(":", 1)[1]
                    bucket_label = custom_bucket_id_to_label.get(opt_id)

                    if not bucket_label:
                        warnings += 1
                        continue

                else:
                    bucket_label = bsel or None

                name_value = None

                if nsel == "__other__":
                    if not nother:
                        warnings += 1
                        continue

                    name_value = nother
                    scope = bucket_label or "Uncategorized"

                    exists = SavingsNameOption.query.filter_by(
                        user_id=user.id,
                        bucket_label=scope,
                        name=name_value,
                        is_active=True,
                    ).first()

                    if not exists:
                        db.session.add(
                            SavingsNameOption(
                                user_id=user.id,
                                bucket_label=scope,
                                name=name_value,
                            )
                        )

                elif nsel.startswith("opt:"):
                    opt_id = nsel.split(":", 1)[1]

                    opt = SavingsNameOption.query.filter_by(
                        id=int(opt_id),
                        user_id=user.id,
                        is_active=True,
                    ).first()

                    if not opt:
                        warnings += 1
                        continue

                    name_value = opt.name

                else:
                    name_value = nother or None

                if bucket_label is None and (
                    name_value is None or name_value.strip() == ""
                ):
                    warnings += 1
                    continue

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
                flash(
                    f"Skipped {warnings} row(s) because they were incomplete or invalid.",
                    "warning",
                )

            return redirect(url_for("savings_month_view", year=year, month=month))

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
    @login_required
    def settings():
        return render_template("settings.html")

    # ==================================================================
    # ROUTE: Delete a single week's entry
    # ==================================================================
    @app.route("/income/delete/<int:paycheck_id>", methods=["POST"])
    @login_required
    def delete_paycheck(paycheck_id):
        user = get_current_user()

        paycheck = Paycheck.query.filter_by(
            id=paycheck_id,
            user_id=user.id,
        ).first_or_404()

        year = paycheck.pay_date.year
        month = paycheck.pay_date.month

        db.session.delete(paycheck)
        db.session.commit()

        flash("Paycheck deleted successfully.", "success")
        return redirect(url_for("income_month_view", year=year, month=month))

    # ==================================================================
    # ROUTE: Reset ALL income data
    # ==================================================================
    @app.route("/income/reset", methods=["POST"])
    @login_required
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
    @login_required
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
    @login_required
    def income_view_redirect():
        year = request.args.get("year")
        month = request.args.get("month")

        if not year or not month:
            flash("Please select both a year and month.", "error")
            return redirect(url_for("income_select_month"))

        return redirect(url_for("income_month_view", year=int(year), month=int(month)))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)