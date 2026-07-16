"""Application configuration.

Dev runs on SQLite with zero setup. For Sprint 2+ (OCR, analytics) set
DATABASE_URL to a PostgreSQL URL and uncomment psycopg2-binary in
requirements.txt -- nothing else needs to change.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)


class Config:
    # SECRET_KEY signs sessions, CSRF tokens, and email confirmation/reset
    # tokens. MUST be overridden in production via the environment.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    _db_url = os.environ.get("DATABASE_URL")
    if _db_url and _db_url.startswith("postgres://"):
        # SQLAlchemy needs the postgresql:// prefix
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url or f"sqlite:///{INSTANCE_DIR / 'we_owe.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True once the app is served over HTTPS in production
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    # Token lifetimes (seconds)
    CONFIRM_TOKEN_MAX_AGE = 60 * 60 * 24        # 24h to confirm email
    RESET_TOKEN_MAX_AGE = 60 * 60                # 1h to reset password

    # Email: if SMTP_* are unset, mail is written to instance/outbox/ instead
    # of being sent, so the register/reset/invite flows are fully testable
    # without a mail server.
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@weowe.app")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "1") == "1"

    # US-03 receipt uploads (images and PDF, maximum 5 MB).
    RECEIPT_UPLOAD_FOLDER = str(INSTANCE_DIR / "receipts")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False          # simplifies the pytest client
    MAIL_SUPPRESS_SEND = True
