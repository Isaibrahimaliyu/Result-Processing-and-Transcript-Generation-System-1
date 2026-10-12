-- ============================================================
-- AUTOMATED RESULT PROCESSING & TRANSCRIPT GENERATION SYSTEM
-- Database Schema — NUC 5.0 CGPA Scale
-- ============================================================

CREATE DATABASE IF NOT EXISTS arps_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE arps_db;

-- ──────────────────────────────────────────
-- 1. USERS  (authentication & role control)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,   -- matric_no OR staff_id
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('student','lecturer','admin') NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ──────────────────────────────────────────
-- 2. STUDENTS
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL UNIQUE,
    matric_no     VARCHAR(30)  NOT NULL UNIQUE,
    first_name    VARCHAR(50)  NOT NULL,
    middle_name   VARCHAR(50),
    last_name     VARCHAR(50)  NOT NULL,
    date_of_birth DATE,
    department    VARCHAR(100) DEFAULT 'Computer Science',
    level         ENUM('100','200','300','400') DEFAULT '100',
    entry_year    YEAR,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ──────────────────────────────────────────
-- 3. LECTURERS
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lecturers (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL UNIQUE,
    staff_id   VARCHAR(30)  NOT NULL UNIQUE,
    first_name VARCHAR(50)  NOT NULL,
    last_name  VARCHAR(50)  NOT NULL,
    department VARCHAR(100) DEFAULT 'Computer Science',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ──────────────────────────────────────────
-- 4. COURSES
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS courses (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    course_code  VARCHAR(15)  NOT NULL UNIQUE,
    course_title VARCHAR(150) NOT NULL,
    credit_unit  TINYINT      NOT NULL CHECK (credit_unit BETWEEN 1 AND 6),
    semester     ENUM('First','Second') NOT NULL,
    level        ENUM('100','200','300','400') NOT NULL,
    lecturer_id  INT,
    is_active    BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (lecturer_id) REFERENCES lecturers(id) ON SET NULL
);

-- ──────────────────────────────────────────
-- 5. COURSE REGISTRATIONS
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_registrations (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    course_id    INT NOT NULL,
    session_year VARCHAR(9)  NOT NULL,   -- e.g. "2023/2024"
    semester     ENUM('First','Second') NOT NULL,
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_reg (student_id, course_id, session_year, semester),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE CASCADE
);

-- ──────────────────────────────────────────
-- 6. SCORES  (the core result table)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scores (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    course_id    INT NOT NULL,
    lecturer_id  INT,
    session_year VARCHAR(9)  NOT NULL,
    semester     ENUM('First','Second') NOT NULL,
    ca_score     DECIMAL(5,2) DEFAULT 0.00,   -- max 30
    exam_score   DECIMAL(5,2) DEFAULT 0.00,   -- max 70
    total_score  DECIMAL(5,2) GENERATED ALWAYS AS (ca_score + exam_score) STORED,
    grade        CHAR(1)      GENERATED ALWAYS AS (
        CASE
            WHEN (ca_score + exam_score) >= 70 THEN 'A'
            WHEN (ca_score + exam_score) >= 60 THEN 'B'
            WHEN (ca_score + exam_score) >= 50 THEN 'C'
            WHEN (ca_score + exam_score) >= 45 THEN 'D'
            WHEN (ca_score + exam_score) >= 40 THEN 'E'
            ELSE 'F'
        END
    ) STORED,
    grade_point  DECIMAL(3,1) GENERATED ALWAYS AS (
        CASE
            WHEN (ca_score + exam_score) >= 70 THEN 5.0
            WHEN (ca_score + exam_score) >= 60 THEN 4.0
            WHEN (ca_score + exam_score) >= 50 THEN 3.0
            WHEN (ca_score + exam_score) >= 45 THEN 2.0
            WHEN (ca_score + exam_score) >= 40 THEN 1.0
            ELSE 0.0
        END
    ) STORED,
    entered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_score (student_id, course_id, session_year, semester),
    FOREIGN KEY (student_id)  REFERENCES students(id)  ON DELETE CASCADE,
    FOREIGN KEY (course_id)   REFERENCES courses(id)   ON DELETE CASCADE,
    FOREIGN KEY (lecturer_id) REFERENCES lecturers(id) ON DELETE SET NULL
);

-- ──────────────────────────────────────────
-- 7. AUDIT LOG  (tamper trail)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT,
    action     VARCHAR(100) NOT NULL,
    table_name VARCHAR(50),
    record_id  INT,
    old_value  TEXT,
    new_value  TEXT,
    ip_address VARCHAR(45),
    logged_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ──────────────────────────────────────────
-- GPA/CGPA VIEW  (computed on the fly)
-- ──────────────────────────────────────────
CREATE OR REPLACE VIEW semester_gpa AS
SELECT
    sc.student_id,
    sc.session_year,
    sc.semester,
    ROUND(SUM(sc.grade_point * c.credit_unit) / SUM(c.credit_unit), 2) AS gpa,
    SUM(c.credit_unit)                                                  AS total_units,
    SUM(sc.grade_point * c.credit_unit)                                 AS quality_points
FROM scores sc
JOIN courses c ON c.id = sc.course_id
GROUP BY sc.student_id, sc.session_year, sc.semester;

CREATE OR REPLACE VIEW cumulative_cgpa AS
SELECT
    student_id,
    ROUND(SUM(quality_points) / SUM(total_units), 2) AS cgpa,
    SUM(total_units)                                  AS total_units_accumulated
FROM semester_gpa
GROUP BY student_id;
