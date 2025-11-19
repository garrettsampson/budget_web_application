"""
config.py

This file holds configuration settings for the Flask application.
Keeping configuration in a separate file is good practice because:

- It keeps `app.py` less cluttered.
- It makes it easier to later switch between dev / test / production settings.
- Secrets (API keys, passwords) can live here or in environment variables.
"""

import os


class Config:
    """
    Config is a simple class whose attributes are used by Flask and
    Flask extensions (like SQLAlchemy) for configuration.

    Flask lets you load this class using:
        app.config.from_object(Config)

    Any UPPERCASE attributes are treated as config keys.
    """

    # SECRET_KEY:
    # -------------
    # Used by Flask to:
    #   - sign session cookies
    #   - protect against CSRF (cross-site request forgery) in some cases
    #
    # In development, a hard-coded string is fine.
    # In production, you’d want to load this from an environment variable.
    SECRET_KEY = "dev-secret-key-change-me-later"

    # SQLALCHEMY_DATABASE_URI:
    # ------------------------
    # This tells SQLAlchemy *where* the database lives and what type it is.
    #
    # "sqlite:///budget.db" means:
    #   - Use SQLite (a file-based database, great for small apps).
    #   - Store the file named "budget.db" in the project directory.
    #
    # You could later switch this to PostgreSQL, MySQL, etc.
    SQLALCHEMY_DATABASE_URI = "sqlite:///budget.db"

    # SQLALCHEMY_TRACK_MODIFICATIONS:
    # -------------------------------
    # When set to True, SQLAlchemy tracks every object change in memory,
    # which uses more resources and is usually unnecessary for small apps.
    #
    # Setting it to False is recommended and avoids a warning.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
