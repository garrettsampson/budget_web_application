import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-later")

    database_url = os.environ.get("DATABASE_URL", "sqlite:///budget.db")

    # Render/Postgres URLs sometimes start with postgres://.
    # SQLAlchemy expects postgresql://.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False