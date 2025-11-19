"""
This file defines the main Flask Application.

High-Level flow:
- We create a Falsk app
- We configure it (database location, secret key, etc.)
- We initialize the database.
- We define routes (URLs) that the user can vsist.
    - "/" shows the home/dashboard page.
    - "/income" shows the form to enter weekly income
    - "income/<year>/<month>" shows the monnthly salary summary


"""

from flask import Flask, render_template, request, redirect, url_for
from models import db, User, IncomeWeek
from config import Config
from datetime import datetime # used for current year/month defaults

def create_app():
    """
    Factory function that creates and configures the Flask app.

    This pattern makes it easier to:
    - test the app
    - extend it later


    """

    app = Flask(__name__)

    # Load configyuation from Config class (SQLALCHEMY_DATABASE_URI, SECRET_KEY, etc.)
    app.config.from_object(Config)

    # Connect the SQLAlchemy 'db' object from models.py to this Flask app.
    db.init_app(app)

    # This 'app.app_context()' block i used for actions that need access to
    # the apps configuration and database, but run once at the startup
    with app.app_context():
        # Create tables in the database if they dont exist yet.
        db.create_all()

        # if no user exists, create a default dummy user.
        #This lets you build everything assuming there is a "current user"
        if not User.query.first():
            dummy_user = User(email="you@example.com")
            db.session.add(dummy_user)
            db.session.commit()
    
    # Helper function to get the "currently logged in" user.
    # Later when we do Google login this will return the actual logged in user.
    def get_current_user():
        return User.query.first()
    
    # ========================
    # ROUTE: Home / Dashboard
    # ========================

    @app.route("/")
    def home():
        """
        Home page.
        RIght now i just loads a simple dashboard template, 
        but later it can show some quick stats or shortcuts.
        """
        return render_template("dashboard.html")
    

    # ========================
    # ROUTE: Income Form
    # URL: /income
    # Methods: GET (show form), POST (handle form submission)
    # ========================
    @app.route("/income", methods=["GET", "POST"])
    def income_form():
        user = get_current_user() # for now, the dummy user

        # If the user submitted the form (clicked "Save Week")
        if request.method == "POST":
            # request.form is like a dictionary where keys are the "name" attributes
            # of the <input> fields in the HTML form.

            # Everything in request.form comes in as a string, so we convert:
            hourly = float(request.form["hourly_pay"])
            hours = float(request.form["hours_worked"])
            tax_percent = float(request.form["tax_percent"])
            year = int(request.form["year"])
            month = int(request.form["month"])
            week_index = int(request.form["week_index"])

            # Do the weekly calculations in Python:
            gross = hourly * hours
            net = gross * (1 - tax_percent / 100.0)

            # Create a new IncomeWeek row with these values
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

            # Add the new row to the session (like staging changes)
            db.Session.add(entry)

            # Commit the changes to permanently save them in the database
            db.session.commit()

            # After saving, redirect the user to the monthly summary page
            # for the same year and month they just saved.
            return redirect(url_for("income_month_view", year=year, month=month))
        
        # if the request method is GET, that means the user is just visiting
        # the page normally and has not submitted the form yet.

        # We will show an empty form, but pre fill the year/month with "today"
        today = datetime.today()

        # Pass the current_year and current_month into the template
        # The template uses these with {{ current_year }} and {{ current_month }}
        return render_template(
            "income/form.html",
            current_year = today.year,
            current_month = today.month,
        )
    
    # ========================
    # ROUTE: Income monthly summary
    # URL: /income/<year>/<month>
    # Example: /income/2025/11
    # ========================
    @app.route("/income/<int:year>/<int:month>")
    def income_month_view(year, month):
        user = get_current_user()

        # Query all IncomeWeek rows for this user and this month/year.
        # filter_by(...) is like writing:
        # WHERE user_id = ? AND year = ? AND month = ?

        # order_by(IncomeWeek.week_index) sorts them by week number

        entries = (
            IncomeWeek.query
            .filter_by(user_id=user.id, year=year, month=month)
            .order_by(IncomeWeek.week_index)
            .all()
        )

        # Compute totals across all weeks for this month
        total_gross = sum(e.gross for e in entries)
        total_net = sum(e.net for e in entries)
        total_tax = total_gross - total_net

        # Pass these values into the template so it can show the table and totals
        return render_template(
            "income/month_view.html",
            year=year,
            month=month,
            entries=entries,
            total_gross=total_gross,
            total_net=total_net,
            total_tax=total_tax,
        )
    
    return app
# When we run "python app.py" directly, this will execute.
# It creates the app using the factory function and starts the dev server.
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

