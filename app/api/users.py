"""
API — User management (admin only, except viewing own profile).
"""

from flask import jsonify, request

from app.models import User
from app.api import api_bp
from app.api.auth import token_required, admin_token_required
from app.api.schemas import serialize_user
from app.utils.helpers import generate_worker_id


# --------------------------------------------------------------------------
# List all users (admin)
# --------------------------------------------------------------------------
@api_bp.route("/users", methods=["GET"])
@admin_token_required
def list_users(current_user: User):
    role = request.args.get("role")  # optional filter: admin | worker
    query = User.objects()
    if role in ("admin", "worker"):
        query = query.filter(role=role)
    users = query.order_by('full_name')
    return jsonify([serialize_user(u) for u in users])


# --------------------------------------------------------------------------
# Get single user (admin, or own profile)
# --------------------------------------------------------------------------
@api_bp.route("/users/<user_id>", methods=["GET"])
@token_required
def get_user(current_user: User, user_id):
    if current_user.role != "admin" and str(current_user.id) != user_id:
        return jsonify({"error": "Access denied"}), 403

    try:
        user = User.objects(id=user_id).first()
    except Exception:
        user = None
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(serialize_user(user))


# --------------------------------------------------------------------------
# Create user (admin)
# --------------------------------------------------------------------------
@api_bp.route("/users", methods=["POST"])
@admin_token_required
def create_user(current_user: User):
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        return jsonify({"error": "full_name is required"}), 400

    new_user = User(
        full_name=full_name,
        worker_id=generate_worker_id(),
        position=(data.get("position") or "").strip() or None,
        nationality=(data.get("nationality") or "").strip() or None,
        location=(data.get("location") or "").strip() or None,
        address=(data.get("address") or "").strip() or None,
        role=data.get("role", "worker") if data.get("role") in ("admin", "worker") else "worker",
    )

    new_user.save()

    return jsonify(serialize_user(new_user)), 201


# --------------------------------------------------------------------------
# Update user (admin)
# --------------------------------------------------------------------------
@api_bp.route("/users/<user_id>", methods=["PUT", "PATCH"])
@admin_token_required
def update_user(current_user: User, user_id):
    try:
        user = User.objects(id=user_id).first()
    except Exception:
        user = None
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}

    if "full_name" in data:
        user.full_name = (data["full_name"] or "").strip() or user.full_name
    if "position" in data:
        user.position = (data["position"] or "").strip() or None
    if "nationality" in data:
        user.nationality = (data["nationality"] or "").strip() or None
    if "location" in data:
        user.location = (data["location"] or "").strip() or None
    if "address" in data:
        user.address = (data["address"] or "").strip() or None
    if "role" in data and data["role"] in ("admin", "worker"):
        user.role = data["role"]

    user.save()
    return jsonify(serialize_user(user))


# --------------------------------------------------------------------------
# Delete user (admin)
# --------------------------------------------------------------------------
@api_bp.route("/users/<user_id>", methods=["DELETE"])
@admin_token_required
def delete_user(current_user: User, user_id):
    try:
        user = User.objects(id=user_id).first()
    except Exception:
        user = None
    if not user:
        return jsonify({"error": "User not found"}), 404

    if str(user.id) == str(current_user.id):
        return jsonify({"error": "Cannot delete yourself"}), 400

    user.delete()
    return jsonify({"message": "User deleted"}), 200
