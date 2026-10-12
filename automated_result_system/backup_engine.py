"""
ARPS — Automatic Backup Engine
Handles scheduled database backups automatically:
  • On app startup via background thread (30s delay)
  • Daily while the app is running (checks every hour)
  • Automatically creates a safety backup BEFORE any restore
  • Keeps only the last 30 backups (auto-cleans old ones)
"""
from __future__ import annotations
import os, glob, subprocess, threading, time, logging
from datetime import datetime

logger = logging.getLogger("arps.backup")
MAX_BACKUPS    = 30
_scheduler_started = False


def get_backup_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    bdir = os.path.join(base, "backups")
    os.makedirs(bdir, exist_ok=True)
    return bdir


def _env():
    e = os.environ.copy()
    e["MYSQL_PWD"] = os.environ.get("DB_PASSWORD", "")
    return e


def _params():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "3306"),
        "user": os.environ.get("DB_USER", "root"),
        "name": os.environ.get("DB_NAME", "arps_db"),
    }


def run_backup(label: str = "auto") -> dict:
    """Run mysqldump. Returns {success, filename, size_kb, error}."""
    p    = _params()
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"arps_{label}_{ts}.sql"
    fpath = os.path.join(get_backup_dir(), fname)

    cmd = ["mysqldump",
           f"--host={p['host']}", f"--port={p['port']}",
           f"--user={p['user']}", "--single-transaction",
           "--routines", "--triggers", "--add-drop-table", p["name"]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                env=_env(), timeout=180)
        if result.returncode != 0:
            logger.error(f"Backup failed: {result.stderr[:200]}")
            return {"success": False, "filename": None, "size_kb": 0,
                    "error": result.stderr[:200]}
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(result.stdout)
        size_kb = os.path.getsize(fpath) / 1024
        logger.info(f"Backup created: {fname} ({size_kb:.1f} KB)")
        _cleanup()
        return {"success": True, "filename": fname, "size_kb": size_kb, "error": None}
    except FileNotFoundError:
        msg = "mysqldump not found. MySQL must be installed and in PATH."
        logger.warning(msg)
        return {"success": False, "filename": None, "size_kb": 0, "error": msg}
    except subprocess.TimeoutExpired:
        return {"success": False, "filename": None, "size_kb": 0, "error": "Backup timed out."}
    except Exception as e:
        return {"success": False, "filename": None, "size_kb": 0, "error": str(e)[:200]}


def run_restore(filename: str) -> dict:
    """Restore DB. Auto-creates a safety backup first. Returns {success, error, safety_backup}."""
    backup_dir = get_backup_dir()
    if not filename.endswith(".sql") or "/" in filename or ".." in filename:
        return {"success": False, "error": "Invalid filename.", "safety_backup": None}
    filepath = os.path.join(backup_dir, filename)
    if not os.path.exists(filepath):
        return {"success": False, "error": "File not found.", "safety_backup": None}

    # Safety backup before restore
    safety = run_backup(label="pre-restore")
    safety_name = safety.get("filename")

    p = _params()
    cmd = ["mysql", f"--host={p['host']}", f"--port={p['port']}",
           f"--user={p['user']}", p["name"]]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            result = subprocess.run(cmd, stdin=f, capture_output=True,
                                    text=True, env=_env(), timeout=300)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr[:300], "safety_backup": safety_name}
        logger.info(f"Restored from {filename}")
        return {"success": True, "error": None, "safety_backup": safety_name}
    except FileNotFoundError:
        return {"success": False, "error": "mysql client not found.", "safety_backup": safety_name}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Restore timed out.", "safety_backup": safety_name}
    except Exception as e:
        return {"success": False, "error": str(e)[:200], "safety_backup": safety_name}


def _cleanup():
    """Keep only MAX_BACKUPS most recent .sql files."""
    files = sorted(glob.glob(os.path.join(get_backup_dir(), "*.sql")),
                   key=os.path.getmtime, reverse=True)
    for old in files[MAX_BACKUPS:]:
        try: os.remove(old)
        except OSError: pass


def backup_needed_today() -> bool:
    today = datetime.utcnow().strftime("%Y%m%d")
    return not any(today in os.path.basename(f)
                   for f in glob.glob(os.path.join(get_backup_dir(), "*.sql")))


def get_backup_list() -> list:
    files = []
    for fpath in sorted(glob.glob(os.path.join(get_backup_dir(), "*.sql")),
                        key=os.path.getmtime, reverse=True):
        stat = os.stat(fpath)
        files.append({
            "name": os.path.basename(fpath),
            "size": stat.st_size,
            "size_kb": f"{stat.st_size/1024:.1f} KB",
            "modified": datetime.fromtimestamp(stat.st_mtime),
        })
    return files


def start_scheduler():
    """Start background daily backup thread. Safe to call multiple times."""
    global _scheduler_started
    if _scheduler_started: return
    _scheduler_started = True

    def _loop():
        time.sleep(30)   # Short delay after startup
        while True:
            try:
                if backup_needed_today():
                    logger.info("Running scheduled daily backup...")
                    r = run_backup(label="scheduled")
                    if r["success"]:
                        logger.info(f"Scheduled backup: {r['filename']} ({r['size_kb']:.1f} KB)")
                    else:
                        logger.warning(f"Scheduled backup failed: {r['error']}")
            except Exception as e:
                logger.exception(f"Backup scheduler error: {e}")
            time.sleep(3600)   # Check every hour

    t = threading.Thread(target=_loop, daemon=True, name="arps-backup")
    t.start()
    logger.info("✅ Auto-backup scheduler started — daily backups enabled.")
