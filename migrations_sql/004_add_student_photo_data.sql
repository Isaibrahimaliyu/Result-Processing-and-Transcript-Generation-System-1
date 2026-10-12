-- ARPS Migration: store passport photos in the database
-- Needed for serverless hosting (e.g. Vercel), where uploaded files are not kept on disk.
-- `python run.py` / `python run.py init` applies this automatically; run manually only if needed.
ALTER TABLE students ADD COLUMN passport_photo_data MEDIUMBLOB NULL;
