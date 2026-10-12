"""ARPS — Application Factory  (v2)"""
import os
from datetime import datetime
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate

from flask_mail import Mail

db            = SQLAlchemy()
login_manager = LoginManager()
bcrypt        = Bcrypt()
migrate       = Migrate()
mail          = Mail()


# ── Auto-backup engine ────────────────────────────────────────
try:
    from backup_engine import start_scheduler as _start_backup_scheduler
    _backup_scheduler_registered = False
except ImportError:
    _start_backup_scheduler = None
    _backup_scheduler_registered = False


def create_app(config_name: str = "default") -> Flask:
    from config import config
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view            = "auth.login"
    login_manager.login_message         = "Please log in to access this page."
    login_manager.login_message_category= "warning"

    # Blueprints
    from routes.auth     import auth_bp
    from routes.student  import student_bp
    from routes.lecturer import lecturer_bp
    from routes.admin    import admin_bp
    from routes.verify   import verify_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp,  url_prefix="/student")
    app.register_blueprint(lecturer_bp, url_prefix="/lecturer")
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(verify_bp)

    # Global template context
    @app.context_processor
    def inject_globals():
        from datetime import datetime as _dt
        return {
            "now":    _dt.utcnow(),
            "config": app.config,   # lets templates read MAIL_SERVER etc.
        }

    # Error pages
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    # Start automatic daily backup scheduler (daemon thread)
    global _backup_scheduler_registered
    if _start_backup_scheduler and not _backup_scheduler_registered:
        _start_backup_scheduler()
        _backup_scheduler_registered = True

    return app
