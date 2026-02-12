"""
Authentication routes — login, logout, worker creation.
"""

import os
import uuid

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

from app.extensions import login_manager
from app.models import User
from app.utils.helpers import generate_worker_id

auth_bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id: str):
    """Callback used by Flask-Login to reload the user from the session."""
    try:
        return User.objects(id=user_id).first()
    except Exception:
        return None


# --------------------------------------------------------------------------
# Login / Logout
# --------------------------------------------------------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.role == "admin" else "worker.dashboard"))

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        worker_id = (request.form.get("worker_id") or "").strip()

        if not full_name or not worker_id:
            flash("Full name and Worker ID are required")
            return render_template("login.html")

        user = User.objects(worker_id=worker_id.upper()).first()

        if user and user.full_name.strip().casefold() == full_name.casefold():
            login_user(user)
            if user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("worker.dashboard"))

        flash("Invalid Name or Worker ID")

    return render_template("login.html")


@auth_bp.route("/login-split")
def login_split():
    return render_template("login_split.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
# Worker creation (admin only)
# --------------------------------------------------------------------------
@auth_bp.route("/create-worker", methods=["POST"])
@login_required
def create_worker():
    if current_user.role != "admin":
        return redirect(url_for("worker.dashboard"))

    full_name = request.form.get("full_name")
    position = request.form.get("position")
    nationality = request.form.get("nationality")
    location = request.form.get("location")
    address = request.form.get("address")
    image_path = None

    photo = request.files.get("photo")
    if photo and photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1].lower()
        allowed = current_app.config.get("ALLOWED_IMAGE_EXTENSIONS", set())
        if ext in allowed:
            filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(upload_folder, exist_ok=True)
            photo.save(os.path.join(upload_folder, filename))
            image_path = f"uploads/{filename}"

    wid = generate_worker_id()

    new_worker = User(
        full_name=full_name,
        worker_id=wid,
        position=position,
        nationality=nationality,
        location=location,
        address=address,
        image_path=image_path,
        role="worker",
    )
    new_worker.save()
    flash(f"New worker added successfully. ASSIGNED ID: {wid}")

    return redirect(url_for("admin.dashboard"))
