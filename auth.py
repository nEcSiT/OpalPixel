import os
import uuid
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from extensions import db, login_manager
from models import User
from utils import generate_worker_id

auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        full_name = (request.form.get('full_name') or '').strip()
        worker_id = (request.form.get('worker_id') or '').strip()

        if not full_name or not worker_id:
            flash('Full name and Worker ID are required')
            return render_template('login.html')

        normalized_id = worker_id.upper()
        user = User.query.filter(func.upper(User.worker_id) == normalized_id).first()

        if user and user.full_name.strip().casefold() == full_name.casefold():
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('dashboard'))
            return redirect(url_for('worker_dashboard'))

        flash('Invalid Name or Worker ID')
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/create-worker', methods=['POST'])
@login_required
def create_worker():
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    full_name = request.form.get('full_name')
    position = request.form.get('position')
    nationality = request.form.get('nationality')
    location = request.form.get('location')
    address = request.form.get('address')
    image_path = None

    photo = request.files.get('photo')
    if photo and photo.filename:
        ext = photo.filename.rsplit('.', 1)[-1].lower()
        allowed = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', set())
        if ext in allowed:
            filename = f"{uuid.uuid4().hex}.{ext}"
            filename = secure_filename(filename)
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            photo.save(os.path.join(upload_folder, filename))
            image_path = f"uploads/{filename}"
    
    worker_id = generate_worker_id()
            
    new_worker = User(
        full_name=full_name,
        worker_id=worker_id,
        position=position,
        nationality=nationality,
        location=location,
        address=address,
        image_path=image_path,
        role='worker'
    )
    db.session.add(new_worker)
    db.session.commit()
    flash(f'New worker added successfully. ASSIGNED ID: {worker_id}')
        
    return redirect(url_for('dashboard'))
