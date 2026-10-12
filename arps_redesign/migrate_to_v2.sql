-- ============================================================
-- ARPS v2 — Database Migration Script
-- Run this against your existing arps_db to upgrade to v2.
-- All statements use IF NOT EXISTS / IF EXISTS so it is safe
-- to run multiple times without errors.
-- ============================================================

USE arps_db;

-- ── 1. ADD last_login TO users (the column causing the error) ──
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS last_login DATETIME NULL AFTER created_at;

-- ── 2. CREATE academic_sessions (new in v2) ──────────────────
CREATE TABLE IF NOT EXISTS academic_sessions (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    session_year      VARCHAR(9)              NOT NULL,
    semester          ENUM('First','Second')  NOT NULL,
    is_current        BOOLEAN DEFAULT FALSE,
    registration_open BOOLEAN DEFAULT TRUE,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_session (session_year, semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 3. CREATE result_publications (new in v2) ────────────────
CREATE TABLE IF NOT EXISTS result_publications (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    session_year VARCHAR(9)             NOT NULL,
    semester     ENUM('First','Second') NOT NULL,
    level        ENUM('100','200','300','400') NOT NULL,
    is_published BOOLEAN DEFAULT FALSE,
    published_at DATETIME NULL,
    published_by INT NULL,
    note         VARCHAR(255),
    UNIQUE KEY uq_pub (session_year, semester, level),
    FOREIGN KEY (published_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 4. VERIFY all existing tables still intact ───────────────
-- (No changes to students, lecturers, courses,
--  course_registrations, scores, audit_log)

SELECT 'Migration complete.' AS status;
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'arps_db'
ORDER BY table_name;

-- ── 5. CREATE transcript_tokens (QR verification — new in v2) ─
CREATE TABLE IF NOT EXISTS transcript_tokens (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    token          VARCHAR(64)  NOT NULL UNIQUE,
    student_id     INT          NOT NULL,
    generated_by   INT          NULL,
    generated_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    expires_at     DATETIME     NULL,
    is_revoked     BOOLEAN      DEFAULT FALSE,
    revoked_at     DATETIME     NULL,
    revoked_by     INT          NULL,
    scan_count     INT          DEFAULT 0,
    last_scanned   DATETIME     NULL,
    note           VARCHAR(255),
    INDEX idx_token (token),
    FOREIGN KEY (student_id)   REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (generated_by) REFERENCES users(id)    ON DELETE SET NULL,
    FOREIGN KEY (revoked_by)   REFERENCES users(id)    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 6. ADD email + phone columns to students ─────────────────
ALTER TABLE students
  ADD COLUMN IF NOT EXISTS email VARCHAR(150) NULL AFTER entry_year,
  ADD COLUMN IF NOT EXISTS phone VARCHAR(20)  NULL AFTER email;

-- ── 7. CREATE email_notifications log ────────────────────────
CREATE TABLE IF NOT EXISTS email_notifications (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    student_id        INT         NOT NULL,
    recipient_email   VARCHAR(150) NOT NULL,
    subject           VARCHAR(255) NOT NULL,
    notification_type ENUM('result_published','transcript_ready','custom') DEFAULT 'result_published',
    session_year      VARCHAR(9)   NULL,
    semester          ENUM('First','Second') NULL,
    sent_at           DATETIME     DEFAULT CURRENT_TIMESTAMP,
    sent_by           INT          NULL,
    status            ENUM('sent','failed','suppressed') DEFAULT 'sent',
    error_message     TEXT         NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (sent_by)    REFERENCES users(id)    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
