"""
ARPS — Vercel serverless entrypoint.

Vercel routes every request here (see vercel.json). Locally, keep using:  python run.py
"""
import os
import sys
import logging

# Make the project root importable (app.py, models.py, routes/, ...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
import models  # noqa: F401  — registers all tables with SQLAlchemy

logger = logging.getLogger("arps")

app = create_app("production")

if not os.environ.get("SECRET_KEY"):
    logger.warning("SECRET_KEY is not set — set it in Vercel → Settings → Environment Variables.")

# Create any missing tables on cold start (no-op when they already exist),
# so a fresh hosted MySQL database works without a manual setup step.
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        logger.error(f"Database not reachable / table creation failed: {e}")
