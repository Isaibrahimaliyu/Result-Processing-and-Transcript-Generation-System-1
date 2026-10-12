"""
ARPS — Configuration

HOW TO FIX "Access denied" MySQL errors
─────────────────────────────────────────
Your MySQL root account has a password but DB_PASSWORD is empty.
Fix it ONE of these ways (easiest first):

  WAY 1 — Create a .env file next to this file containing:
      DB_PASSWORD=your_mysql_password
      DB_USER=root
      DB_NAME=arps_db

  WAY 2 — Set a Windows environment variable:
      In Command Prompt (before running): set DB_PASSWORD=your_password
"""
import os
import ssl
from datetime import timedelta
from urllib.parse import quote_plus

# Load .env file automatically if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# True when running on Vercel (or any read-only serverless host).
# Only /tmp is writable there, and background threads / mysqldump are unavailable.
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("SERVERLESS"))
WRITABLE_DIR  = "/tmp" if IS_SERVERLESS else os.path.dirname(os.path.abspath(__file__))


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


class Config:
    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY    = os.environ.get("SECRET_KEY",    "arps-secret-key-2026")
    ADMIN_PASSKEY = os.environ.get("ADMIN_PASSKEY", "DEPT-CS-ADMIN-2026")

    # ── Database ───────────────────────────────────────────────────────────
    # Set DB_PASSWORD in .env (never hard-code passwords here — this repo is public)
    DB_HOST     = os.environ.get("DB_HOST",     "localhost")
    DB_PORT     = int(os.environ.get("DB_PORT", "3306"))
    DB_USER     = os.environ.get("DB_USER",     "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME     = os.environ.get("DB_NAME",     "arps_db")

    # DATABASE_URL (e.g. from Aiven / TiDB Cloud / Railway) takes priority over DB_* vars.
    _db_url = os.environ.get("DATABASE_URL", "").strip()
    if _db_url.startswith("mysql://"):
        _db_url = "mysql+pymysql://" + _db_url[len("mysql://"):]
    SQLALCHEMY_DATABASE_URI = _db_url or (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,   # auto-reconnect if MySQL drops the connection
    }
    # Hosted MySQL providers require TLS. Set DB_SSL=true (and optionally DB_SSL_CA
    # to a CA certificate path) to enable it.
    if _env_bool("DB_SSL"):
        _ssl_ctx = ssl.create_default_context(cafile=os.environ.get("DB_SSL_CA") or None)
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"ssl": _ssl_ctx}

    # ── Sessions ──────────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # ── File Uploads ──────────────────────────────────────────────────────
    UPLOAD_FOLDER       = os.path.join(WRITABLE_DIR, "uploads")
    MAX_CONTENT_LENGTH  = 5 * 1024 * 1024   # 5 MB
    ALLOWED_EXTENSIONS  = {"csv", "xlsx"}

    # ── University branding ───────────────────────────────────────────────
    UNIVERSITY_NAME = "Ibrahim Badamasi Babangida University"
    DEPARTMENT_NAME = "Department of Computer Science"
    FACULTY_NAME    = "Faculty of Science"

    # ── QR Verification URL ───────────────────────────────────────────────
    # Set this to your server's IP or domain so QR codes scan correctly.
    # Examples:
    #   Local network:   SERVER_URL=http://192.168.1.100:5000
    #   Public domain:   SERVER_URL=https://arps.ibbul.edu.ng
    # If empty, the server auto-detects from the HTTP request (recommended).
    SERVER_URL = os.environ.get("SERVER_URL", "")

    # ── Email / SMTP ──────────────────────────────────────────────────────
    # Set these in your .env file — see .env.example for instructions.
    # Gmail:  MAIL_SERVER=smtp.gmail.com | MAIL_PORT=587 | MAIL_USE_TLS=true
    # Yahoo:  MAIL_SERVER=smtp.mail.yahoo.com | MAIL_PORT=587
    # Uni:    MAIL_SERVER=smtp.ibbul.edu.ng | ask IT for credentials
    MAIL_SERVER         = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT           = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS        = os.environ.get("MAIL_USE_TLS",  "true").lower()  == "true"
    MAIL_USE_SSL        = os.environ.get("MAIL_USE_SSL",  "false").lower() == "true"
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER",
        "IBB University ARPS <noreply@ibbul.edu.ng>"
    )
    # True = log emails to console without sending (safe for testing)
    MAIL_SUPPRESS_SEND  = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() == "true"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG   = False
    TESTING = False


config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
