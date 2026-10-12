-- ARPS Performance Migration: add indexes to frequently-searched/filtered columns
-- Safe to run on the live MySQL database — only adds indexes, no data is touched.
-- Uses a stored procedure guard so it can be re-run safely (skips indexes that already exist).

DELIMITER $$

DROP PROCEDURE IF EXISTS arps_add_index $$
CREATE PROCEDURE arps_add_index(
    IN p_table VARCHAR(64),
    IN p_index VARCHAR(64),
    IN p_ddl   VARCHAR(500)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = p_table
          AND index_name   = p_index
    ) THEN
        SET @ddl = p_ddl;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END $$

DELIMITER ;

-- users
CALL arps_add_index('users', 'ix_users_role', 'CREATE INDEX ix_users_role ON users (role)');

-- academic_sessions
CALL arps_add_index('academic_sessions', 'ix_sessions_is_current', 'CREATE INDEX ix_sessions_is_current ON academic_sessions (is_current)');

-- students
CALL arps_add_index('students', 'ix_students_matric_no',  'CREATE INDEX ix_students_matric_no ON students (matric_no)');
CALL arps_add_index('students', 'ix_students_first_name', 'CREATE INDEX ix_students_first_name ON students (first_name)');
CALL arps_add_index('students', 'ix_students_last_name',  'CREATE INDEX ix_students_last_name ON students (last_name)');
CALL arps_add_index('students', 'ix_students_department', 'CREATE INDEX ix_students_department ON students (department)');
CALL arps_add_index('students', 'ix_students_level',      'CREATE INDEX ix_students_level ON students (level)');

-- courses
CALL arps_add_index('courses', 'ix_courses_course_code', 'CREATE INDEX ix_courses_course_code ON courses (course_code)');
CALL arps_add_index('courses', 'ix_courses_semester',    'CREATE INDEX ix_courses_semester ON courses (semester)');
CALL arps_add_index('courses', 'ix_courses_level',       'CREATE INDEX ix_courses_level ON courses (level)');
CALL arps_add_index('courses', 'ix_courses_lecturer_id', 'CREATE INDEX ix_courses_lecturer_id ON courses (lecturer_id)');
CALL arps_add_index('courses', 'ix_courses_is_active',   'CREATE INDEX ix_courses_is_active ON courses (is_active)');

-- course_registrations (composite, covers the two most common lookup patterns)
CALL arps_add_index('course_registrations', 'ix_reg_student_session', 'CREATE INDEX ix_reg_student_session ON course_registrations (student_id, session_year, semester)');
CALL arps_add_index('course_registrations', 'ix_reg_course_session',  'CREATE INDEX ix_reg_course_session ON course_registrations (course_id, session_year, semester)');

-- scores (composite, covers transcript generation and course score-sheet views)
CALL arps_add_index('scores', 'ix_score_student_session', 'CREATE INDEX ix_score_student_session ON scores (student_id, session_year, semester)');
CALL arps_add_index('scores', 'ix_score_course_session',  'CREATE INDEX ix_score_course_session ON scores (course_id, session_year, semester)');

-- audit_log (grows unbounded — needed for the paginated/sorted audit trail page)
CALL arps_add_index('audit_log', 'ix_audit_log_user_id',    'CREATE INDEX ix_audit_log_user_id ON audit_log (user_id)');
CALL arps_add_index('audit_log', 'ix_audit_log_action',     'CREATE INDEX ix_audit_log_action ON audit_log (action)');
CALL arps_add_index('audit_log', 'ix_audit_log_logged_at',  'CREATE INDEX ix_audit_log_logged_at ON audit_log (logged_at)');

-- email_notifications
CALL arps_add_index('email_notifications', 'ix_email_student_id', 'CREATE INDEX ix_email_student_id ON email_notifications (student_id)');
CALL arps_add_index('email_notifications', 'ix_email_sent_at',    'CREATE INDEX ix_email_sent_at ON email_notifications (sent_at)');

-- transcript_tokens
CALL arps_add_index('transcript_tokens', 'ix_tokens_student_id', 'CREATE INDEX ix_tokens_student_id ON transcript_tokens (student_id)');

DROP PROCEDURE IF EXISTS arps_add_index;
