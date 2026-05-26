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
import math

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
    Goal,
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
    

    def calculate_goal_progress(goal, user):
        """
        Calculates automatic progress for a goal.

        A goal is connected to savings data by matching:
        - goal.bucket == SavingsAllocation.bucket
        - goal.name == SavingsAllocation.name

        This function now also returns:
        - status label
        - estimated completion month/year
        - better user-facing progress messages
        """

        today = date.today()

        current_year = today.year
        current_month = today.month

        month_names = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

        def add_months(year, month, months_to_add):
            """
            Adds a number of months to a year/month pair.

            Example:
            May 2026 + 5 months = October 2026
            """

            month_index = (year * 12) + (month - 1)
            new_month_index = month_index + months_to_add

            new_year = new_month_index // 12
            new_month = (new_month_index % 12) + 1

            return new_year, new_month

        total_contributed_from_app = 0.0
        months_checked = 0
        months_with_contribution = 0

        current_month_contribution = 0.0
        most_recent_contribution_amount = 0.0
        most_recent_contribution_month = None
        most_recent_contribution_year = None

        # Start checking from the goal's start year and month.
        year = goal.start_year
        month = goal.start_month

        # Loop from the goal start month up through the current month.
        while (year < current_year) or (year == current_year and month <= current_month):
            months_checked += 1

            month_start = date(year, month, 1)

            if month == 12:
                next_month_start = date(year + 1, 1, 1)
            else:
                next_month_start = date(year, month + 1, 1)

            # ----------------------------------------------------------
            # Get monthly net income from paychecks.
            # ----------------------------------------------------------
            paychecks = (
                Paycheck.query
                .filter(
                    Paycheck.user_id == user.id,
                    Paycheck.pay_date >= month_start,
                    Paycheck.pay_date < next_month_start,
                )
                .all()
            )

            monthly_net_income = sum(
                paycheck.net_amount or 0.0
                for paycheck in paychecks
            )

            # ----------------------------------------------------------
            # Get monthly expenses.
            # ----------------------------------------------------------
            expenses = (
                Expense.query
                .filter_by(
                    user_id=user.id,
                    year=year,
                    month=month,
                    is_active=True,
                )
                .all()
            )

            monthly_expenses = sum(
                expense.cost or 0.0
                for expense in expenses
            )

            money_left_after_expenses = monthly_net_income - monthly_expenses

            # ----------------------------------------------------------
            # Get matching savings allocations for this goal.
            #
            # Exact matching rule:
            # goal.bucket must equal allocation.bucket
            # goal.name must equal allocation.name
            # ----------------------------------------------------------
            matching_allocations = (
                SavingsAllocation.query
                .filter_by(
                    user_id=user.id,
                    year=year,
                    month=month,
                    bucket=goal.bucket,
                    name=goal.name,
                    is_active=True,
                )
                .all()
            )

            monthly_goal_contribution = 0.0

            for allocation in matching_allocations:
                percent = allocation.percent or 0.0
                amount = money_left_after_expenses * (percent / 100.0)
                monthly_goal_contribution += amount

            # If the calculated contribution is negative, do not subtract from
            # the goal. This can happen if expenses are higher than income.
            if monthly_goal_contribution < 0:
                monthly_goal_contribution = 0.0

            if monthly_goal_contribution > 0:
                months_with_contribution += 1
                most_recent_contribution_amount = monthly_goal_contribution
                most_recent_contribution_month = month
                most_recent_contribution_year = year

            if year == current_year and month == current_month:
                current_month_contribution = monthly_goal_contribution

            total_contributed_from_app += monthly_goal_contribution

            # Move to the next month.
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1

        # --------------------------------------------------------------
        # Final progress calculations.
        # --------------------------------------------------------------
        current_amount = (goal.starting_amount or 0.0) + total_contributed_from_app

        remaining_amount = goal.target_amount - current_amount

        if remaining_amount < 0:
            remaining_amount = 0.0

        if goal.target_amount > 0:
            percent_complete = (current_amount / goal.target_amount) * 100
        else:
            percent_complete = 0.0

        if percent_complete > 100:
            percent_complete = 100.0

        if months_with_contribution > 0:
            average_monthly_contribution = (
                total_contributed_from_app / months_with_contribution
            )
        else:
            average_monthly_contribution = 0.0

        if average_monthly_contribution > 0 and remaining_amount > 0:
            estimated_months_remaining = math.ceil(
                remaining_amount / average_monthly_contribution
            )

            estimated_completion_year, estimated_completion_month = add_months(
                current_year,
                current_month,
                estimated_months_remaining,
            )

            estimated_completion_label = (
                f"{month_names[estimated_completion_month]} {estimated_completion_year}"
            )

        elif remaining_amount == 0:
            estimated_months_remaining = 0
            estimated_completion_year = current_year
            estimated_completion_month = current_month
            estimated_completion_label = f"{month_names[current_month]} {current_year}"

        else:
            estimated_months_remaining = None
            estimated_completion_year = None
            estimated_completion_month = None
            estimated_completion_label = None

        # --------------------------------------------------------------
        # Status label and message.
        # --------------------------------------------------------------
        if remaining_amount == 0:
            status = "completed"
            status_label = "Completed"
            status_message = "Goal reached. Great job."

        elif current_amount > 0:
            status = "in_progress"
            status_label = "In Progress"

            if estimated_completion_label:
                status_message = (
                    f"At your current pace, you should reach this goal around "
                    f"{estimated_completion_label}."
                )
            else:
                status_message = (
                    "You have started this goal, but there are not enough recurring "
                    "matching contributions yet to estimate a completion date."
                )

        else:
            status = "not_started"
            status_label = "Not Started"
            status_message = (
                "No matching savings contributions yet. Add a savings allocation "
                "with this same bucket and name to begin automatic tracking."
            )

        if most_recent_contribution_month:
            most_recent_contribution_label = (
                f"{month_names[most_recent_contribution_month]} "
                f"{most_recent_contribution_year}"
            )
        else:
            most_recent_contribution_label = None

        return {
            "current_amount": current_amount,
            "remaining_amount": remaining_amount,
            "percent_complete": percent_complete,
            "average_monthly_contribution": average_monthly_contribution,
            "estimated_months_remaining": estimated_months_remaining,
            "estimated_completion_year": estimated_completion_year,
            "estimated_completion_month": estimated_completion_month,
            "estimated_completion_label": estimated_completion_label,
            "months_checked": months_checked,
            "months_with_contribution": months_with_contribution,
            "current_month_contribution": current_month_contribution,
            "most_recent_contribution_amount": most_recent_contribution_amount,
            "most_recent_contribution_month": most_recent_contribution_month,
            "most_recent_contribution_year": most_recent_contribution_year,
            "most_recent_contribution_label": most_recent_contribution_label,
            "status": status,
            "status_label": status_label,
            "status_message": status_message,
        }
    
    def get_goal_form_options(user):
        """
        Builds bucket/name suggestion lists for the Goals form.

        This pulls from:
        - Existing savings allocations
        - Custom savings bucket options
        - Custom savings name options

        It also creates a dictionary of names grouped by bucket.

        Example:
        {
            "Pet Care": ["Emergency Fund", "Vet Fund"],
            "Investments": ["Roth IRA", "Brokerage"]
        }

        This lets the Goals form show only the names that belong
        to the selected bucket.
        """

        bucket_options = set()
        name_options = set()

        # Used to avoid duplicate bucket/name pair chips.
        bucket_name_pair_keys = set()
        bucket_name_pairs = []

        # Main mapping for Phase 4D:
        # bucket -> set of names
        names_by_bucket = {}

        def add_bucket_name_pair(bucket, name):
            """
            Adds a bucket/name pair to all of the correct suggestion lists.
            """

            bucket = (bucket or "").strip()
            name = (name or "").strip()

            if bucket:
                bucket_options.add(bucket)

            if name:
                name_options.add(name)

            if bucket and name:
                if bucket not in names_by_bucket:
                    names_by_bucket[bucket] = set()

                names_by_bucket[bucket].add(name)

                pair_key = (bucket, name)

                if pair_key not in bucket_name_pair_keys:
                    bucket_name_pair_keys.add(pair_key)

                    bucket_name_pairs.append(
                        {
                            "bucket": bucket,
                            "name": name,
                            "label": f"{bucket} / {name}",
                        }
                    )

        # ----------------------------------------------------------
        # Pull bucket/name pairs from actual savings allocations.
        # These are the most important because they represent real
        # data the goal can match against.
        # ----------------------------------------------------------
        allocations = (
            SavingsAllocation.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .all()
        )

        for allocation in allocations:
            add_bucket_name_pair(
                allocation.bucket,
                allocation.name,
            )

        # ----------------------------------------------------------
        # Pull custom bucket options.
        # ----------------------------------------------------------
        custom_buckets = (
            SavingsBucketOption.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .all()
        )

        for option in custom_buckets:
            label = (option.label or "").strip()

            if label:
                bucket_options.add(label)

                if label not in names_by_bucket:
                    names_by_bucket[label] = set()

        # ----------------------------------------------------------
        # Pull custom name options.
        # ----------------------------------------------------------
        custom_names = (
            SavingsNameOption.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .all()
        )

        for option in custom_names:
            add_bucket_name_pair(
                option.bucket_label,
                option.name,
            )

        # Convert sets to sorted lists so the template/JavaScript
        # can use the data cleanly.
        names_by_bucket_for_template = {}

        for bucket, names in names_by_bucket.items():
            names_by_bucket_for_template[bucket] = sorted(names)

        return {
            "bucket_options": sorted(bucket_options),
            "name_options": sorted(name_options),
            "bucket_name_pairs": sorted(
                bucket_name_pairs,
                key=lambda item: item["label"].lower(),
            ),
            "names_by_bucket": names_by_bucket_for_template,
        }

    # ==================================================================
    # ROUTE: Register
    # ==================================================================
    @app.route("/register", methods=["GET", "POST"])
    def register():
        """
        Creates a new user account.

        Form fields expected:
        - display_name
        - email
        - password
        - confirm_password
        """

        if request.method == "POST":
            display_name = (request.form.get("display_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            confirm_password = request.form.get("confirm_password") or ""

            if not display_name:
                flash("Account name is required.", "error")
                return redirect(url_for("register"))

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
                display_name=display_name,
                password_hash=generate_password_hash(password),
            )

            db.session.add(new_user)
            db.session.commit()

            session["user_id"] = new_user.id
            session["display_name"] = new_user.display_name
            session["user_email"] = new_user.email

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
            session["display_name"] = user.display_name or user.email
            session["user_email"] = user.email
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
    # ROUTE: Account Settings
    # ==================================================================
    @app.route("/account")
    @login_required
    def account():
        user = get_current_user()
        return render_template("auth/account.html", user=user)

    # ==================================================================
    # ROUTE: Update Account Name / Email
    # ==================================================================
    @app.route("/account/update-profile", methods=["POST"])
    @login_required
    def update_profile():
        user = get_current_user()

        display_name = (request.form.get("display_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()

        if not display_name:
            flash("Account name is required.", "error")
            return redirect(url_for("account"))

        if not email:
            flash("Email is required.", "error")
            return redirect(url_for("account"))

        existing_user = User.query.filter(
            User.email == email,
            User.id != user.id
        ).first()

        if existing_user:
            flash("That email is already being used by another account.", "error")
            return redirect(url_for("account"))

        user.display_name = display_name
        user.email = email

        db.session.commit()

        session["display_name"] = user.display_name
        session["user_email"] = user.email

        flash("Account profile updated successfully.", "success")
        return redirect(url_for("account"))

    # ==================================================================
    # ROUTE: Change Password
    # ==================================================================
    @app.route("/account/change-password", methods=["POST"])
    @login_required
    def change_password():
        user = get_current_user()

        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not check_password_hash(user.password_hash, current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("account"))

        if not new_password:
            flash("New password is required.", "error")
            return redirect(url_for("account"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("account"))

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()

        flash("Password changed successfully.", "success")
        return redirect(url_for("account"))

    # ==================================================================
    # ROUTE: Delete Account
    # ==================================================================
    @app.route("/account/delete", methods=["POST"])
    @login_required
    def delete_account():
        user = get_current_user()

        password = request.form.get("password") or ""
        confirm_text = (request.form.get("confirm_text") or "").strip()

        if not check_password_hash(user.password_hash, password):
            flash("Password is incorrect. Account was not deleted.", "error")
            return redirect(url_for("account"))

        if confirm_text != "DELETE":
            flash("You must type DELETE exactly to confirm account deletion.", "error")
            return redirect(url_for("account"))

        user_id = user.id

        Paycheck.query.filter_by(user_id=user_id).delete()
        IncomeWeek.query.filter_by(user_id=user_id).delete()
        Expense.query.filter_by(user_id=user_id).delete()
        SavingsAllocation.query.filter_by(user_id=user_id).delete()
        Goal.query.filter_by(user_id=user_id).delete()

        ExpenseBucketOption.query.filter_by(user_id=user_id).delete()
        ExpenseMerchantOption.query.filter_by(user_id=user_id).delete()
        SavingsBucketOption.query.filter_by(user_id=user_id).delete()
        SavingsNameOption.query.filter_by(user_id=user_id).delete()

        User.query.filter_by(id=user_id).delete()

        db.session.commit()
        session.clear()

        flash("Your account and all related data were deleted.", "success")
        return redirect(url_for("register"))

    # ==================================================================
    # ROUTE: Home Dashboard
    # ==================================================================
    @app.route("/")
    @login_required
    def home():
        user = get_current_user()
        today = date.today()

        year = today.year
        month = today.month

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

        total_income = sum(p.net_amount for p in paychecks)

        expenses = (
            Expense.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .all()
        )

        total_expenses = sum(e.cost for e in expenses)

        money_left_after_expenses = total_income - total_expenses

        savings_allocations = (
            SavingsAllocation.query
            .filter_by(user_id=user.id, year=year, month=month, is_active=True)
            .all()
        )

        total_savings_percent = sum(s.percent for s in savings_allocations)
        total_savings_amount = money_left_after_expenses * (total_savings_percent / 100.0)

        final_leftover = money_left_after_expenses - total_savings_amount


        # --------------------------------------------------------------
        # Goals close to completion
        #
        # Shows goals on the home dashboard if they are:
        # - already completed
        # - estimated to be completed within the next 3 months
        #
        # This keeps important goals visible without cluttering the page.
        # --------------------------------------------------------------
        active_goals = (
            Goal.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .order_by(Goal.created_at.desc())
            .all()
        )

        goals_close_to_completion = []

        for goal in active_goals:
            progress = calculate_goal_progress(goal, user)

            estimated_months = progress.get("estimated_months_remaining")

            is_completed = progress.get("status") == "completed"

            is_close = (
                estimated_months is not None
                and estimated_months <= 3
            )

            if is_completed or is_close:
                goals_close_to_completion.append(
                    {
                        "goal": goal,
                        "progress": progress,
                    }
                )

        # Sort so the closest/completed goals appear first.
        goals_close_to_completion.sort(
            key=lambda item: (
                item["progress"]["estimated_months_remaining"]
                if item["progress"]["estimated_months_remaining"] is not None
                else 999
            )
        )

        # Only show a few on the home page so it does not get cluttered.
        goals_close_to_completion = goals_close_to_completion[:3]

        return render_template(
            "dashboard.html",
            year=year,
            month=month,
            total_income=total_income,
            total_expenses=total_expenses,
            money_left_after_expenses=money_left_after_expenses,
            total_savings_percent=total_savings_percent,
            total_savings_amount=total_savings_amount,
            final_leftover=final_leftover,
            goals_close_to_completion=goals_close_to_completion,
        )

    # ==================================================================
    # ROUTE: Yearly Dashboard
    # ==================================================================
    @app.route("/yearly")
    @login_required
    def yearly():
        """
        Shows a full-year summary for the logged-in user.

        Phase 1 goals:
        - No new database tables
        - No charts yet
        - Summarize existing Paycheck, Expense, and SavingsAllocation data
        - Break information down month-by-month
        - Break expenses down by bucket
        - Break savings down by bucket/name
        """

        user = get_current_user()
        today = date.today()

        # --------------------------------------------------------------
        # Read selected year from the URL.
        #
        # Example:
        #   /yearly?year=2026
        #
        # If no year is provided, use the current year.
        # --------------------------------------------------------------
        selected_year = request.args.get("year", today.year, type=int)

        year_start = date(selected_year, 1, 1)
        next_year_start = date(selected_year + 1, 1, 1)

        # --------------------------------------------------------------
        # Month names for display
        # --------------------------------------------------------------
        month_names = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

        # --------------------------------------------------------------
        # Create a starting row for each month.
        #
        # We do this first so the page always shows all 12 months,
        # even if some months have no data yet.
        # --------------------------------------------------------------
        monthly_rows = []

        for month_number in range(1, 13):
            monthly_rows.append(
                {
                    "month": month_number,
                    "month_name": month_names[month_number],
                    "gross_income": 0.0,
                    "net_income": 0.0,
                    "tax_withheld": 0.0,
                    "hours_worked": 0.0,
                    "expenses": 0.0,
                    "money_left_after_expenses": 0.0,
                    "savings_percent": 0.0,
                    "savings_amount": 0.0,
                    "final_leftover": 0.0,
                }
            )

        # This lets us quickly access a month row by month number.
        # Example:
        #   rows_by_month[5] gives May's row.
        rows_by_month = {
            row["month"]: row for row in monthly_rows
        }

        # --------------------------------------------------------------
        # Pull all paychecks for the selected year.
        #
        # Income is counted by pay_date because that is when money
        # actually entered the account.
        # --------------------------------------------------------------
        paychecks = (
            Paycheck.query
            .filter(
                Paycheck.user_id == user.id,
                Paycheck.pay_date >= year_start,
                Paycheck.pay_date < next_year_start,
            )
            .all()
        )

        for paycheck in paychecks:
            month_number = paycheck.pay_date.month
            row = rows_by_month[month_number]

            row["net_income"] += paycheck.net_amount or 0.0
            row["gross_income"] += paycheck.gross_amount or 0.0
            row["tax_withheld"] += paycheck.tax_withheld or 0.0
            row["hours_worked"] += paycheck.hours_worked or 0.0

        # --------------------------------------------------------------
        # Pull all active expenses for the selected year.
        # --------------------------------------------------------------
        expenses = (
            Expense.query
            .filter_by(
                user_id=user.id,
                year=selected_year,
                is_active=True,
            )
            .all()
        )

        expense_bucket_totals = {}

        for expense in expenses:
            month_number = expense.month
            row = rows_by_month.get(month_number)

            if row:
                row["expenses"] += expense.cost or 0.0

            bucket = expense.category or "Uncategorized"

            if bucket not in expense_bucket_totals:
                expense_bucket_totals[bucket] = 0.0

            expense_bucket_totals[bucket] += expense.cost or 0.0

        # --------------------------------------------------------------
        # Pull all active savings allocations for the selected year.
        #
        # IMPORTANT:
        # SavingsAllocation stores a percent, not a dollar amount.
        # So we calculate the dollar value using:
        #
        #   monthly money left after expenses * allocation percent
        # --------------------------------------------------------------
        savings_allocations = (
            SavingsAllocation.query
            .filter_by(
                user_id=user.id,
                year=selected_year,
                is_active=True,
            )
            .all()
        )

        # First calculate money left after expenses for each month.
        for row in monthly_rows:
            row["money_left_after_expenses"] = (
                row["net_income"] - row["expenses"]
            )

        savings_breakdown_totals = {}

        for allocation in savings_allocations:
            month_number = allocation.month
            row = rows_by_month.get(month_number)

            if not row:
                continue

            percent = allocation.percent or 0.0
            amount = row["money_left_after_expenses"] * (percent / 100.0)

            row["savings_percent"] += percent
            row["savings_amount"] += amount

            bucket = allocation.bucket or "Uncategorized"
            name = allocation.name or "Unnamed"

            key = (bucket, name)

            if key not in savings_breakdown_totals:
                savings_breakdown_totals[key] = {
                    "bucket": bucket,
                    "name": name,
                    "amount": 0.0,
                    "percent_total": 0.0,
                }

            savings_breakdown_totals[key]["amount"] += amount
            savings_breakdown_totals[key]["percent_total"] += percent

        # --------------------------------------------------------------
        # Now calculate final leftover and extra per-month display stats.
        # --------------------------------------------------------------
        for row in monthly_rows:
            row["final_leftover"] = (
                row["money_left_after_expenses"] - row["savings_amount"]
            )

            # A month counts as having data if anything meaningful was entered.
            row["has_data"] = (
                row["net_income"] > 0
                or row["gross_income"] > 0
                or row["expenses"] > 0
                or row["savings_amount"] > 0
                or row["hours_worked"] > 0
            )

            # Expenses as a percent of that month's net income.
            if row["net_income"] > 0:
                row["expense_percent_of_income"] = (
                    row["expenses"] / row["net_income"]
                ) * 100

                row["savings_percent_of_income"] = (
                    row["savings_amount"] / row["net_income"]
                ) * 100
            else:
                row["expense_percent_of_income"] = 0.0
                row["savings_percent_of_income"] = 0.0

            # Simple status label for styling in the table.
            if row["final_leftover"] > 0:
                row["leftover_status"] = "positive"
            elif row["final_leftover"] < 0:
                row["leftover_status"] = "negative"
            else:
                row["leftover_status"] = "neutral"

        # --------------------------------------------------------------
        # Yearly totals
        # --------------------------------------------------------------
        total_gross_income = sum(row["gross_income"] for row in monthly_rows)
        total_net_income = sum(row["net_income"] for row in monthly_rows)
        total_tax_withheld = sum(row["tax_withheld"] for row in monthly_rows)
        total_hours_worked = sum(row["hours_worked"] for row in monthly_rows)

        total_expenses = sum(row["expenses"] for row in monthly_rows)
        total_money_left_after_expenses = sum(
            row["money_left_after_expenses"] for row in monthly_rows
        )
        total_savings_amount = sum(row["savings_amount"] for row in monthly_rows)
        total_final_leftover = sum(row["final_leftover"] for row in monthly_rows)


        # --------------------------------------------------------------
        # Averages
        #
        # Phase 1 averaged across all 12 months.
        # Phase 1.5 improves this by averaging only months with actual data.
        #
        # Example:
        # If you only have data for January through May, the average should
        # divide by 5 instead of 12.
        # --------------------------------------------------------------
        months_with_data = [
            row for row in monthly_rows
            if row["has_data"]
        ]

        months_with_data_count = len(months_with_data)

        if months_with_data_count > 0:
            average_monthly_net_income = (
                total_net_income / months_with_data_count
            )
            average_monthly_expenses = (
                total_expenses / months_with_data_count
            )
            average_monthly_savings = (
                total_savings_amount / months_with_data_count
            )
        else:
            average_monthly_net_income = 0.0
            average_monthly_expenses = 0.0
            average_monthly_savings = 0.0

        if total_hours_worked > 0:
            average_net_income_per_hour = (
                total_net_income / total_hours_worked
            )
        else:
            average_net_income_per_hour = 0.0


        # --------------------------------------------------------------
        # Quick yearly insights
        #
        # These make the yearly page more useful at a glance.
        # --------------------------------------------------------------
        if months_with_data:
            highest_income_month = max(
                months_with_data,
                key=lambda row: row["net_income"],
            )

            highest_expense_month = max(
                months_with_data,
                key=lambda row: row["expenses"],
            )

            best_leftover_month = max(
                months_with_data,
                key=lambda row: row["final_leftover"],
            )

            lowest_leftover_month = min(
                months_with_data,
                key=lambda row: row["final_leftover"],
            )
        else:
            highest_income_month = None
            highest_expense_month = None
            best_leftover_month = None
            lowest_leftover_month = None

        # --------------------------------------------------------------
        # Percent calculations
        # --------------------------------------------------------------
        if total_net_income > 0:
            expense_percent_of_income = (total_expenses / total_net_income) * 100
            savings_percent_of_income = (total_savings_amount / total_net_income) * 100
        else:
            expense_percent_of_income = 0.0
            savings_percent_of_income = 0.0

        # --------------------------------------------------------------
        # Prepare expense bucket breakdown for the template.
        # --------------------------------------------------------------
        expense_bucket_rows = []

        for bucket, amount in expense_bucket_totals.items():
            if total_expenses > 0:
                percent = (amount / total_expenses) * 100
            else:
                percent = 0.0

            expense_bucket_rows.append(
                {
                    "bucket": bucket,
                    "amount": amount,
                    "percent": percent,
                }
            )

        expense_bucket_rows.sort(
            key=lambda item: item["amount"],
            reverse=True,
        )

        # --------------------------------------------------------------
        # Prepare savings breakdown for the template.
        # --------------------------------------------------------------
        savings_breakdown_rows = []

        for item in savings_breakdown_totals.values():
            if total_savings_amount > 0:
                percent = (item["amount"] / total_savings_amount) * 100
            else:
                percent = 0.0

            savings_breakdown_rows.append(
                {
                    "bucket": item["bucket"],
                    "name": item["name"],
                    "amount": item["amount"],
                    "percent": percent,
                }
            )

        savings_breakdown_rows.sort(
            key=lambda item: item["amount"],
            reverse=True,
        )
        # --------------------------------------------------------------
        # Chart data for Phase 2A / 2B
        #
        # This prepares simple lists that JavaScript can use to build
        # charts on the yearly dashboard.
        #
        # Chart.js needs arrays like:
        #   labels: ["January", "February", ...]
        #   data:   [1200, 950, ...]
        # --------------------------------------------------------------
        chart_month_labels = [
            row["month_name"] for row in monthly_rows
        ]

        chart_net_income = [
            round(row["net_income"], 2) for row in monthly_rows
        ]

        chart_expenses = [
            round(row["expenses"], 2) for row in monthly_rows
        ]

        chart_savings = [
            round(row["savings_amount"], 2) for row in monthly_rows
        ]

        chart_final_leftover = [
            round(row["final_leftover"], 2) for row in monthly_rows
        ]

        chart_hours_worked = [
            round(row["hours_worked"], 2) for row in monthly_rows
        ]

        # --------------------------------------------------------------
        # Chart data for Phase 2C / 2D
        #
        # These power the yearly doughnut charts:
        # - Expense Buckets
        # - Savings Breakdown
        # --------------------------------------------------------------

        chart_expense_bucket_labels = [
            item["bucket"] for item in expense_bucket_rows
        ]

        chart_expense_bucket_data = [
            round(item["amount"], 2) for item in expense_bucket_rows
        ]

        chart_savings_breakdown_labels = [
            f'{item["bucket"]} - {item["name"]}'
            for item in savings_breakdown_rows
        ]

        chart_savings_breakdown_data = [
            round(item["amount"], 2) for item in savings_breakdown_rows
        ]

        # --------------------------------------------------------------
        # Available years for the dropdown.
        #
        # We include the selected/current year even if there is no data yet.
        # --------------------------------------------------------------
        available_years = {today.year, selected_year}

        all_paychecks = Paycheck.query.filter_by(user_id=user.id).all()
        all_expenses = Expense.query.filter_by(user_id=user.id).all()
        all_savings = SavingsAllocation.query.filter_by(user_id=user.id).all()

        for paycheck in all_paychecks:
            available_years.add(paycheck.pay_date.year)

        for expense in all_expenses:
            available_years.add(expense.year)

        for allocation in all_savings:
            available_years.add(allocation.year)

        available_years = sorted(available_years, reverse=True)

        return render_template(
            "yearly.html",
            selected_year=selected_year,
            available_years=available_years,
            monthly_rows=monthly_rows,
            expense_bucket_rows=expense_bucket_rows,
            savings_breakdown_rows=savings_breakdown_rows,
            total_gross_income=total_gross_income,
            total_net_income=total_net_income,
            total_tax_withheld=total_tax_withheld,
            total_hours_worked=total_hours_worked,
            total_expenses=total_expenses,
            total_money_left_after_expenses=total_money_left_after_expenses,
            total_savings_amount=total_savings_amount,
            total_final_leftover=total_final_leftover,
            average_monthly_net_income=average_monthly_net_income,
            average_monthly_expenses=average_monthly_expenses,
            average_monthly_savings=average_monthly_savings,
            expense_percent_of_income=expense_percent_of_income,
            savings_percent_of_income=savings_percent_of_income,
            months_with_data_count=months_with_data_count,
            average_net_income_per_hour=average_net_income_per_hour,
            highest_income_month=highest_income_month,
            highest_expense_month=highest_expense_month,
            best_leftover_month=best_leftover_month,
            lowest_leftover_month=lowest_leftover_month,



            # Chart data
            chart_month_labels=chart_month_labels,
            chart_net_income=chart_net_income,
            chart_expenses=chart_expenses,
            chart_savings=chart_savings,
            chart_final_leftover=chart_final_leftover,
            chart_expense_bucket_labels=chart_expense_bucket_labels,
            chart_expense_bucket_data=chart_expense_bucket_data,
            chart_savings_breakdown_labels=chart_savings_breakdown_labels,
            chart_savings_breakdown_data=chart_savings_breakdown_data,
            chart_hours_worked=chart_hours_worked,
        )
    

    # ==================================================================
    # ROUTE: Goals Page
    # ==================================================================
    @app.route("/goals", methods=["GET", "POST"])
    @login_required
    def goals():
        """
        Basic Goals page.

        Phase 3 features:
        - Create goals
        - List active goals
        - Calculate automatic progress from savings allocations
        - Show percent complete
        - Show estimated time remaining
        """

        user = get_current_user()
        today = date.today()

        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            bucket = (request.form.get("bucket") or "").strip()
            name = (request.form.get("name") or "").strip()

            target_amount = request.form.get("target_amount", type=float)
            starting_amount = request.form.get(
                "starting_amount",
                default=0.0,
                type=float,
            )

            start_year = request.form.get(
                "start_year",
                default=today.year,
                type=int,
            )

            start_month = request.form.get(
                "start_month",
                default=today.month,
                type=int,
            )

            if not title or not bucket or not name or target_amount is None:
                flash(
                    "Please fill out the goal title, bucket, name, and target amount.",
                    "error",
                )
                return redirect(url_for("goals"))

            if target_amount <= 0:
                flash("Goal target amount must be greater than $0.", "error")
                return redirect(url_for("goals"))

            if starting_amount is None:
                starting_amount = 0.0

            if starting_amount < 0:
                flash("Starting amount cannot be negative.", "error")
                return redirect(url_for("goals"))

            if start_month < 1 or start_month > 12:
                flash("Start month must be between 1 and 12.", "error")
                return redirect(url_for("goals"))

            new_goal = Goal(
                user_id=user.id,
                title=title,
                bucket=bucket,
                name=name,
                target_amount=round(target_amount, 2),
                starting_amount=round(starting_amount, 2),
                start_year=start_year,
                start_month=start_month,
                is_active=True,
            )

            db.session.add(new_goal)
            db.session.commit()

            flash("Goal created successfully.", "success")
            return redirect(url_for("goals"))

        active_goals = (
            Goal.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .order_by(Goal.created_at.desc())
            .all()
        )

        goal_cards = []

        for goal in active_goals:
            progress = calculate_goal_progress(goal, user)

            goal_cards.append(
                {
                    "goal": goal,
                    "progress": progress,
                }
            )

        active_goal_cards = [
            item for item in goal_cards
            if item["progress"]["status"] != "completed"
        ]

        completed_goal_cards = [
            item for item in goal_cards
            if item["progress"]["status"] == "completed"
        ]

        # --------------------------------------------------------------
        # Goal summary stats for the top of the Goals page.
        #
        # IMPORTANT:
        # "Active Goals" means goals that are NOT completed.
        # Completed goals are still shown, but they are not counted
        # as active goals.
        # --------------------------------------------------------------
        active_goal_count = len(active_goal_cards)
        completed_goal_count = len(completed_goal_cards)

        in_progress_goal_count = sum(
            1 for item in active_goal_cards
            if item["progress"]["status"] == "in_progress"
        )

        not_started_goal_count = sum(
            1 for item in active_goal_cards
            if item["progress"]["status"] == "not_started"
        )

        total_goal_target = sum(
            item["goal"].target_amount or 0.0
            for item in goal_cards
        )

        total_saved_toward_goals = sum(
            item["progress"]["current_amount"] or 0.0
            for item in goal_cards
        )

        total_remaining_for_goals = sum(
            item["progress"]["remaining_amount"] or 0.0
            for item in goal_cards
        )

        if total_goal_target > 0:
            overall_goal_percent = (
                total_saved_toward_goals / total_goal_target
            ) * 100
        else:
            overall_goal_percent = 0.0

        if overall_goal_percent > 100:
            overall_goal_percent = 100.0

        closest_goal_card = None

        goals_with_estimates = [
            item for item in goal_cards
            if item["progress"]["estimated_months_remaining"] is not None
            and item["progress"]["status"] != "completed"
        ]

        if goals_with_estimates:
            closest_goal_card = min(
                goals_with_estimates,
                key=lambda item: item["progress"]["estimated_months_remaining"],
            )
        elif goal_cards:
            completed_goals = [
                item for item in goal_cards
                if item["progress"]["status"] == "completed"
            ]

            if completed_goals:
                closest_goal_card = completed_goals[0]

        goal_summary = {
            "active_goal_count": active_goal_count,
            "completed_goal_count": completed_goal_count,
            "in_progress_goal_count": in_progress_goal_count,
            "not_started_goal_count": not_started_goal_count,
            "total_goal_target": total_goal_target,
            "total_saved_toward_goals": total_saved_toward_goals,
            "total_remaining_for_goals": total_remaining_for_goals,
            "overall_goal_percent": overall_goal_percent,
            "closest_goal_card": closest_goal_card,
        }

        goal_form_options = get_goal_form_options(user)

        return render_template(
            "goals.html",
            goal_cards=goal_cards,
            active_goal_cards=active_goal_cards,
            completed_goal_cards=completed_goal_cards,
            goal_summary=goal_summary,
            current_year=today.year,
            current_month=today.month,
            goal_bucket_options=goal_form_options["bucket_options"],
            goal_name_options=goal_form_options["name_options"],
            goal_bucket_name_pairs=goal_form_options["bucket_name_pairs"],
            goal_names_by_bucket=goal_form_options["names_by_bucket"],
        )
    


    # ==================================================================
    # ROUTE: Remove / Archive Goal
    # ==================================================================
    @app.route("/goals/<int:goal_id>/delete", methods=["POST"])
    @login_required
    def delete_goal(goal_id):
        """
        Archives a goal by setting is_active to False.

        This is safer than permanently deleting it because the goal
        can be hidden without destroying historical user data.
        """

        user = get_current_user()

        goal = (
            Goal.query
            .filter_by(
                id=goal_id,
                user_id=user.id,
            )
            .first_or_404()
        )

        goal.is_active = False
        db.session.commit()

        flash("Goal removed.", "success")
        return redirect(url_for("goals"))
    

    # ==================================================================
    # ROUTE: Edit Goal
    # ==================================================================
    @app.route("/goals/<int:goal_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_goal(goal_id):
        """
        Lets the logged-in user edit an existing goal.

        This is useful if the user typed the wrong bucket/name,
        wrong target amount, or wrong start month.
        """

        user = get_current_user()

        goal = (
            Goal.query
            .filter_by(
                id=goal_id,
                user_id=user.id,
                is_active=True,
            )
            .first_or_404()
        )

        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            bucket = (request.form.get("bucket") or "").strip()
            name = (request.form.get("name") or "").strip()

            target_amount = request.form.get("target_amount", type=float)
            starting_amount = request.form.get(
                "starting_amount",
                default=0.0,
                type=float,
            )

            start_year = request.form.get(
                "start_year",
                default=goal.start_year,
                type=int,
            )

            start_month = request.form.get(
                "start_month",
                default=goal.start_month,
                type=int,
            )

            if not title or not bucket or not name or target_amount is None:
                flash(
                    "Please fill out the goal title, bucket, name, and target amount.",
                    "error",
                )
                return redirect(url_for("edit_goal", goal_id=goal.id))

            if target_amount <= 0:
                flash("Goal target amount must be greater than $0.", "error")
                return redirect(url_for("edit_goal", goal_id=goal.id))

            if starting_amount is None:
                starting_amount = 0.0

            if starting_amount < 0:
                flash("Starting amount cannot be negative.", "error")
                return redirect(url_for("edit_goal", goal_id=goal.id))

            if start_month < 1 or start_month > 12:
                flash("Start month must be between 1 and 12.", "error")
                return redirect(url_for("edit_goal", goal_id=goal.id))

            goal.title = title
            goal.bucket = bucket
            goal.name = name
            goal.target_amount = round(target_amount, 2)
            goal.starting_amount = round(starting_amount, 2)
            goal.start_year = start_year
            goal.start_month = start_month

            db.session.commit()

            flash("Goal updated successfully.", "success")
            return redirect(url_for("goals"))

        goal_form_options = get_goal_form_options(user)

        return render_template(
            "goals/edit.html",
            goal=goal,
            current_year=date.today().year,
            current_month=date.today().month,
            goal_bucket_options=goal_form_options["bucket_options"],
            goal_name_options=goal_form_options["name_options"],
            goal_bucket_name_pairs=goal_form_options["bucket_name_pairs"],
            goal_names_by_bucket=goal_form_options["names_by_bucket"],
        )

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