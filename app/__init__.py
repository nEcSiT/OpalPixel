"""
OpalPixel — Application package.

Uses the *application factory* pattern so the app can be created with
different configurations (development, testing, production).
"""

import os

import cloudinary
from flask import Flask, render_template
from flask_login import current_user

from config import config_by_name


def create_app(config_name: str | None = None) -> Flask:
    """Build and return a fully configured Flask application."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # -- Cloudinary --------------------------------------------------------
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    # -- Extensions --------------------------------------------------------
    from app.extensions import init_db, login_manager

    init_db(app)
    login_manager.init_app(app)

    # -- Blueprints --------------------------------------------------------
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.worker import worker_bp
    from app.invoices import invoices_bp
    from app.exports import exports_bp
    from app.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(worker_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(exports_bp)
    app.register_blueprint(api_bp)

    # -- Root landing page ------------------------------------------------
    @app.route("/")
    def index():
        return render_template("landing.html")

    # -- Database bootstrap ------------------------------------------------
    # Only seed admin in the main process, not in the reloader subprocess
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            _seed_admin()

    return app


def _seed_admin() -> None:
    """Create the default admin account if none exists."""
    from app.models import User

    try:
        if not User.objects(role="admin").first():
            admin = User(
                full_name="OpalPixel",
                worker_id="OPL-0508748992",
                position="System Admin",
                role="admin",
            )
            admin.set_password("admin123")
            admin.save()
            print("Default admin created: OPL-0508748992")
    except Exception as e:
        print(f"Could not seed admin: {e}")

