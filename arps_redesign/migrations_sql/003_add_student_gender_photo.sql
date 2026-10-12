-- ARPTGS Migration: add gender and passport_photo columns to students table
-- Supports the redesigned transcript layout (student photo top-right, Sex field
-- in the bio-data grid, matching the university's official CRF document style).
-- Safe to run on the live MySQL database — additive only, no data loss.

SET @col1_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'students' AND column_name = 'gender'
);
SET @ddl1 = IF(@col1_exists = 0,
    'ALTER TABLE students ADD COLUMN gender ENUM(''M'',''F'') NULL AFTER phone',
    'SELECT 1'
);
PREPARE stmt1 FROM @ddl1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

SET @col2_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'students' AND column_name = 'passport_photo'
);
SET @ddl2 = IF(@col2_exists = 0,
    'ALTER TABLE students ADD COLUMN passport_photo VARCHAR(255) NULL AFTER gender',
    'SELECT 1'
);
PREPARE stmt2 FROM @ddl2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
