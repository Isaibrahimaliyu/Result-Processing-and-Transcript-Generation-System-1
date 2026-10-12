"""
ARPS — Configuration

HOW TO FIX "Access denied" MySQL errors
─────────────────────────────────────────
Your MySQL root account has a password but DB_PASSWORD is empty.
Fix it ONE of these ways (easiest first):

  WAY 1 — Edit this file directly:
      Change the DB_PASSWORD line below to your actual password:
      DB_PASSWORD = os.environ.get("DB_PASSWORD", "YOUR_PASSWORD_HERE")

  WAY 2 — Create a .env file next to this file containing:
      DB_PASSWORD=your_mysql_password
      DB_USER=root
      DB_NAME=arps_db

  WAY 3 — Set a Windows environment variable:
      In Command Prompt (before running): set DB_PASSWORD=your_password
"""
import os
from datetime import timedelta

# Load .env file automatically if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY    = os.environ.get("SECRET_KEY",    "arps-secret-key-2026")
    ADMIN_PASSKEY = os.environ.get("ADMIN_PASSKEY", "DEPT-CS-ADMIN-2026")

    # ── Database ───────────────────────────────────────────────────────────
    # ⚠️  Set DB_PASSWORD to your MySQL root password to fix Access Denied errors
    DB_HOST     = os.environ.get("DB_HOST",     "localhost")
    DB_PORT     = int(os.environ.get("DB_PORT", "3306"))
    DB_USER     = os.environ.get("DB_USER",     "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "123456789")   # ← YOUR MYSQL PASSWORD HERE
    DB_NAME     = os.environ.get("DB_NAME",     "arps_db")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,   # auto-reconnect if MySQL drops the connection
    }

    # ── Sessions ──────────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # ── File Uploads ──────────────────────────────────────────────────────
    UPLOAD_FOLDER       = os.path.join(os.path.dirname(__file__), "uploads")
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
    SERVER_URL = os.environ.get("SERVER_URL", "http://172.16.5.32:5000")

    # ── Email / SMTP ──────────────────────────────────────────────────────
    # Set these in your .env file — see .env.example for instructions.
    # Gmail:  MAIL_SERVER=smtp.gmail.com | MAIL_PORT=587 | MAIL_USE_TLS=true
    # Yahoo:  MAIL_SERVER=smtp.mail.yahoo.com | MAIL_PORT=587
    # Uni:    MAIL_SERVER=smtp.ibbul.edu.ng | ask IT for credentials
    MAIL_SERVER         = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT           = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS        = os.environ.get("MAIL_USE_TLS",  "true").lower()  == "true"
    MAIL_USE_SSL        = os.environ.get("MAIL_USE_SSL",  "false").lower() == "true"
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME", "arps.ibbul@gmail.com")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD", "czoajexaicecpzxd")
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
