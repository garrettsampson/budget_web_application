import os

class Config:
    SECRET_KEY = "devkey"  # replace later
    SQLALCHEMY_DATABASE_URI = "sqlite:///budget.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
