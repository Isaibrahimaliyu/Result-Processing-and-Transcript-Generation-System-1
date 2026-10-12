"""
ARPS v2 — Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usage:
  python run.py          → start the server (auto-migrates DB on every start)
  python run.py init     → create all tables then show setup instructions
  python run.py reset    → ⚠️  DROP all tables and recreate (wipes all data)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
First-time setup:
  1. Set DB_PASSWORD in .env
  2. python run.py init
  3. python run.py
  4. Visit http://localhost:5000/register
     → Register as Exam Officer using the ADMIN_PASSKEY from .env
"""
import sys

# ── Load .env file before anything else ─────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import create_app, db
from models import (User, Student, Lecturer, Course, CourseRegistration,
                    Score, AuditLog, AcademicSession, ResultPublication)

app = create_app("development")


@app.shell_context_processor
def make_shell_context():
    return dict(db=db, User=User, Student=Student, Lecturer=Lecturer,
                Course=Course, Score=Score,
                AcademicSession=AcademicSession,
                ResultPublication=ResultPublication)


def auto_migrate():
    """
    Safely add any columns / tables that exist in the models
    but are missing from the database.  Safe to run every startup.
    """
    from sqlalchemy import text, inspect
    with app.app_context():
        # Create any tables that don't exist yet (fresh database) — no-op otherwise
        db.create_all()

        engine   = db.engine
        inspector = inspect(engine)

        with engine.connect() as conn:

            # ── users.last_login ──────────────────────────────
            users_cols = [c["name"] for c in inspector.get_columns("users")]
            if "last_login" not in users_cols:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN last_login DATETIME NULL AFTER created_at"
                ))
                conn.commit()
                print("✅ Migration: added users.last_login")

            # ── academic_sessions table ───────────────────────
            tables = inspector.get_table_names()
            if "academic_sessions" not in tables:
                conn.execute(text("""
                    CREATE TABLE academic_sessions (
                        id                INT AUTO_INCREMENT PRIMARY KEY,
                        session_year      VARCHAR(9)             NOT NULL,
                        semester          ENUM('First','Second') NOT NULL,
                        is_current        BOOLEAN DEFAULT FALSE,
                        registration_open BOOLEAN DEFAULT TRUE,
                        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_session (session_year, semester)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created academic_sessions table")

            # ── result_publications table ─────────────────────
            if "result_publications" not in tables:
                conn.execute(text("""
                    CREATE TABLE result_publications (
                        id           INT AUTO_INCREMENT PRIMARY KEY,
                        session_year VARCHAR(9)             NOT NULL,
                        semester     ENUM('First','Second') NOT NULL,
                        level        ENUM('100','200','300','400') NOT NULL,
                        is_published BOOLEAN DEFAULT FALSE,
                        published_at DATETIME NULL,
                        published_by INT NULL,
                        note         VARCHAR(255),
                        UNIQUE KEY uq_pub (session_year, semester, level),
                        FOREIGN KEY (published_by)
                            REFERENCES users(id) ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created result_publications table")

            # ── transcript_tokens table ───────────────────────
            if "transcript_tokens" not in tables:
                conn.execute(text("""
                    CREATE TABLE transcript_tokens (
                        id           INT AUTO_INCREMENT PRIMARY KEY,
                        token        VARCHAR(64) NOT NULL,
                        student_id   INT         NOT NULL,
                        generated_by INT         NULL,
                        generated_at DATETIME    DEFAULT CURRENT_TIMESTAMP,
                        expires_at   DATETIME    NULL,
                        is_revoked   BOOLEAN     DEFAULT FALSE,
                        revoked_at   DATETIME    NULL,
                        revoked_by   INT         NULL,
                        scan_count   INT         DEFAULT 0,
                        last_scanned DATETIME    NULL,
                        note         VARCHAR(255),
                        UNIQUE KEY uq_tk (token),
                        FOREIGN KEY (student_id)   REFERENCES students(id) ON DELETE CASCADE,
                        FOREIGN KEY (generated_by) REFERENCES users(id)    ON DELETE SET NULL,
                        FOREIGN KEY (revoked_by)   REFERENCES users(id)    ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created transcript_tokens table")

            # ── students.email + phone columns ───────────────
            student_cols = [c["name"] for c in inspector.get_columns("students")]
            if "email" not in student_cols:
                conn.execute(text("ALTER TABLE students ADD COLUMN email VARCHAR(150) NULL"))
                conn.commit()
                print("✅ Migration: added students.email")
            if "phone" not in student_cols:
                conn.execute(text("ALTER TABLE students ADD COLUMN phone VARCHAR(20) NULL"))
                conn.commit()
                print("✅ Migration: added students.phone")
            if "gender" not in student_cols:
                conn.execute(text("ALTER TABLE students ADD COLUMN gender ENUM('M','F') NULL"))
                conn.commit()
                print("✅ Migration: added students.gender")
            if "passport_photo" not in student_cols:
                conn.execute(text("ALTER TABLE students ADD COLUMN passport_photo VARCHAR(255) NULL"))
                conn.commit()
                print("✅ Migration: added students.passport_photo")
            if "passport_photo_data" not in student_cols:
                conn.execute(text("ALTER TABLE students ADD COLUMN passport_photo_data MEDIUMBLOB NULL"))
                conn.commit()
                print("✅ Migration: added students.passport_photo_data")

            # ── lecturers.email ───────────────────────────────
            lecturer_cols = [c["name"] for c in inspector.get_columns("lecturers")]
            if "email" not in lecturer_cols:
                conn.execute(text("ALTER TABLE lecturers ADD COLUMN email VARCHAR(150) NULL"))
                conn.commit()
                print("✅ Migration: added lecturers.email")

            # ── email_notifications table ─────────────────────
            tables = inspector.get_table_names()
            if "email_notifications" not in tables:
                conn.execute(text("""
                    CREATE TABLE email_notifications (
                        id                INT AUTO_INCREMENT PRIMARY KEY,
                        student_id        INT          NOT NULL,
                        recipient_email   VARCHAR(150) NOT NULL,
                        subject           VARCHAR(255) NOT NULL,
                        notification_type ENUM('result_published','transcript_ready','custom')
                                          DEFAULT 'result_published',
                        session_year      VARCHAR(9)   NULL,
                        semester          ENUM('First','Second') NULL,
                        sent_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                        sent_by           INT NULL,
                        status            ENUM('sent','failed','suppressed') DEFAULT 'sent',
                        error_message     TEXT NULL,
                        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                        FOREIGN KEY (sent_by)    REFERENCES users(id)    ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created email_notifications table")

            # ── spillover_records table ──────────────────────
            tables = inspector.get_table_names()
            if "spillover_records" not in tables:
                conn.execute(text("""
                    CREATE TABLE spillover_records (
                        id                  INT AUTO_INCREMENT PRIMARY KEY,
                        student_id          INT         NOT NULL UNIQUE,
                        reason              TEXT        NULL,
                        outstanding_courses TEXT        NULL,
                        extra_sessions      SMALLINT    DEFAULT 1,
                        marked_at           DATETIME    DEFAULT CURRENT_TIMESTAMP,
                        marked_by           INT         NULL,
                        is_cleared          BOOLEAN     DEFAULT FALSE,
                        cleared_at          DATETIME    NULL,
                        cleared_by          INT         NULL,
                        note                VARCHAR(255) NULL,
                        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                        FOREIGN KEY (marked_by)  REFERENCES users(id)    ON DELETE SET NULL,
                        FOREIGN KEY (cleared_by) REFERENCES users(id)    ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created spillover_records table")

            # ── password_reset_otps table ─────────────────────────
            if "password_reset_otps" not in tables:
                conn.execute(text("""
                    CREATE TABLE password_reset_otps (
                        id            INT AUTO_INCREMENT PRIMARY KEY,
                        user_id       INT          NOT NULL,
                        otp_code      VARCHAR(6)   NOT NULL,
                        created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
                        expires_at    DATETIME     NOT NULL,
                        is_used       BOOLEAN      DEFAULT FALSE,
                        email_sent_to VARCHAR(150) NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """))
                conn.commit()
                print("✅ Migration: created password_reset_otps table")

        print("✅ Database schema is up to date.")


def seed_demo():
    """
    No demo data needed.
    Use the running app to register real accounts:
      - Register as Admin/Exam Officer (requires the ADMIN_PASSKEY from .env)
      - Register as Lecturer using Staff ID
      - Import students via Admin → Import Students (CSV upload)
    """
    with app.app_context():
        auto_migrate()
        print()
        print("=" * 54)
        print("  ✅ ARPS database is ready — all tables created.")
        print()
        print("  Next steps:")
        print("  1. Run:   python run.py")
        print("  2. Go to: http://localhost:5000/register")
        print("  3. Select 'Exam Officer' and enter the passkey")
        print(f"     from your .env:  ADMIN_PASSKEY=...")
        print("  4. Log in and start configuring the system.")
        print("=" * 54)


def check_db_connection():
    """Test MySQL connection before starting and give a clear error if it fails."""
    import os
    from sqlalchemy import text
    try:
        with app.app_context():
            db.engine.connect().close()
        return True
    except Exception as e:
        err = str(e)
        print()
        print("╔══════════════════════════════════════════════════════╗")
        print("║        ARPS — DATABASE CONNECTION FAILED             ║")
        print("╚══════════════════════════════════════════════════════╝")
        print()
        if "Access denied" in err or "1045" in err:
            pw = os.environ.get("DB_PASSWORD", "")
            print("  ❌ ERROR: MySQL password is wrong or missing.")
            print()
            print("  QUICK FIX:")
            print("  1. Open the file:  .env.example")
            print("  2. Copy it and rename to:  .env")
            print("  3. Set your MySQL password:")
            print("       DB_PASSWORD=your_actual_mysql_password")
            print("  4. Save and run again:  python run.py")
            print()
            print("  OR edit config.py directly and change:")
            print('       DB_PASSWORD = os.environ.get("DB_PASSWORD", "YOUR_PASSWORD")')
        elif "Unknown database" in err or "1049" in err:
            print("  ❌ ERROR: Database 'arps_db' does not exist.")
            print()
            print("  QUICK FIX — run this in MySQL Workbench or terminal:")
            print("       CREATE DATABASE arps_db;")
        elif "Can't connect" in err or "2003" in err:
            print("  ❌ ERROR: Cannot connect to MySQL server.")
            print()
            print("  QUICK FIX:")
            print("  • Make sure MySQL Server is running")
            print("  • Check DB_HOST and DB_PORT in config.py or .env")
        else:
            print(f"  ❌ ERROR: {err[:200]}")
        print()
        return False


def reset_database():
    """
    Drop ALL tables and recreate them from scratch.
    WARNING: This permanently deletes all data.
    """
    with app.app_context():
        print()
        print("⚠️  WARNING: This will permanently delete ALL data in arps_db.")
        confirm = input("   Type  YES  to confirm: ").strip()
        if confirm != "YES":
            print("   Cancelled — no changes made.")
            return

        print()
        print("🗑️  Dropping all tables...")
        db.drop_all()
        print("✅ All tables dropped.")

        print("🔨 Recreating tables from models...")
        db.create_all()
        print("✅ All tables recreated (empty).")

        print()
        print("   Run  python run.py seed  to load demo data,")
        print("   or start the app now with  python run.py")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        if not check_db_connection():
            sys.exit(1)
        reset_database()
    elif len(sys.argv) > 1 and sys.argv[1] in ("seed", "init"):
        if check_db_connection():
            seed_demo()
    else:
        if not check_db_connection():
            sys.exit(1)
        # Always auto-migrate on startup
        auto_migrate()
        app.run(debug=True, port=5000)
