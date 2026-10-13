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


AIVEN_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIERDCCAqygAwIBAgIUJ/Tn3aGRzFxacDd0oTihL40RTrswDQYJKoZIhvcNAQEM
BQAwOjE4MDYGA1UEAwwvMDMyMzVjMTktMDk3My00NmVmLTlkMjQtMzVkODU2MjJl
YjVhIFByb2plY3QgQ0EwHhcNMjYxMDEyMTY1MDE4WhcNMzYxMDA5MTY1MDE4WjA6
MTgwNgYDVQQDDC8wMzIzNWMxOS0wOTczLTQ2ZWYtOWQyNC0zNWQ4NTYyMmViNWEg
UHJvamVjdCBDQTCCAaIwDQYJKoZIhvcNAQEBBQADggGPADCCAYoCggGBAJ+9noBX
UYvgLuFLX9G19ljwDzGr4FWzPT+SSy97/MfJXtKcdE9BhzPFg9tIrD0ECibMoV7Z
j7o7Qx1SJeJa7n4iEmIy+QL2B5M33b/ciFN06w9H4LFesv5HfQ+k8no7Ebdq8oMA
FXUAgFGYYJmvrH/s914qUnV3uRQESQfbc4b+BnI+9nUhcH7OUDU18XusAR49QpI1
qU/8rhl0Oheoud/2QYMUTUtdWjaMeGap9CjOkXN4wD4JofvQJQilLxW3R+Ttj/Qe
XX4UWs+CWIpq4GLqlt+6KCEs/o7lQc79qaXV0n41vEPFhVAyv5bcXJ7l1Yh7UP/L
mqZGJeytYTh4+sUtnW5de1NUxOsRCQwhVuREVKW5KSZtXUnFiKENDn1KQer4sg39
bQEe1thBiYxWFhK+DmfO/DX2uTl/Oq2gVg8Amk+TnITENF+OLM03OfAyZKE+CGsd
yqCuzfU6+MILEggm6DxpwI6RVGiKZEkHEDDyqI5qpHrA7Xl74uwjd2q0bwIDAQAB
o0IwQDAdBgNVHQ4EFgQUtubSjWknbsM1AjdkKa7Q/ezb8cYwEgYDVR0TAQH/BAgw
BgEB/wIBADALBgNVHQ8EBAMCAQYwDQYJKoZIhvcNAQEMBQADggGBAIErLI/4BsZZ
cNntqypUm13L8eYsa61pQnYStzPcw+J5kG1peg20ZPvRYsJ3MHhiTbg281G0y+bL
P/KSS4Un0280/oVakonjXDR8eYdH7DxjmNnveHccsZVxtSEWcWAZ66kZ4rXx5WHn
T6gaJFgY+o59n3coPDEAj3crdB5AgtCVi/ebYWJdyZVbP9S5qye4HgR7gjHQQ5mE
652O7X1su+s3oCFo/6SyZ4oygkedgz3XiSjuP2j+H0GjZWcPWGOajSYEbq+Q3YlP
NGmbgKtXJHfhB0bIs5/fj9lE4wi9bDDsQwJNWqy7v5SqRDzhlpMmANqin+0d/m6o
Qxe10oT2bQihls08aQTAZOyxoaJaJ9UkdxRcLavW+05dKvNiqtozrK4Jm6dI4EYh
2zJED5YI32aaoyWL5tvYI5hvc8MMAHYUMujZ2PYsAy2EOLppDCOOEFtDw6nOV6WX
a6lrXKMrVeqJhCu2Nr3UGZQEYIIAk8ySSoYbkFvocE8PKBwCE2aEmA==
-----END CERTIFICATE-----
"""


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
    # Aiven signs its servers with a private project CA that is NOT in the system
    # trust store, so a default verifying context fails with
    # "certificate verify failed" and every DB query becomes a 500.
    #   DB_SSL_CA_PEM = full text of Aiven's CA certificate (best on Vercel)
    #   DB_SSL_CA     = path to a CA file (local use)
    #   neither       = encrypted connection WITHOUT certificate verification
    if _env_bool("DB_SSL"):
        _ca_pem  = os.environ.get("DB_SSL_CA_PEM", "").replace("\\n", "\n").strip()
        _ca_file = os.environ.get("DB_SSL_CA", "").strip()
        if _ca_pem:
            _ssl_ctx = ssl.create_default_context(cadata=_ca_pem)
            _ssl_ctx.check_hostname = False   # Aiven CA cert is not issued per-hostname
        elif _ca_file:
            _ssl_ctx = ssl.create_default_context(cafile=_ca_file)
            _ssl_ctx.check_hostname = False
        else:
            # Built-in Aiven project CA (public certificate, not a secret)
            _ssl_ctx = ssl.create_default_context(cadata=AIVEN_CA_PEM)
            _ssl_ctx.check_hostname = False
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
