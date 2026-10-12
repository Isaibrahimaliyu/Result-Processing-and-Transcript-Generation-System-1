-- ARPTGS Migration: add email column to lecturers table
-- Required for password-recovery (OTP) emails to reach lecturers and admins,
-- who previously had nowhere on file to receive a reset code.
-- Safe to run on the live MySQL database — additive only, no data loss.

SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name   = 'lecturers'
      AND column_name  = 'email'
);

SET @ddl = IF(@col_exists = 0,
    'ALTER TABLE lecturers ADD COLUMN email VARCHAR(150) NULL AFTER department',
    'SELECT 1'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
