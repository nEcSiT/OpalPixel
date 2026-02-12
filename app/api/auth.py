"""
API authentication — token generation and verification.

Tokens are signed with the app's SECRET_KEY using itsdangerous
(bundled with Flask) and expire after 24 hours by default.
"""

from __future__ import annotations

from functools import wraps

from flask import current_app, jsonify, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.models import User
from app.api import api_bp
from app.api.schemas import serialize_user

# Token lifetime in seconds (24 hours)
TOKEN_MAX_AGE = 86400


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(user: User) -> str:
    """Create a signed token encoding the user id."""
    s = _get_serializer()
    return s.dumps({"uid": str(user.id)})


def verify_token(token: str) -> User | None:
    """Return the User for a valid token, or None."""
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    try:
        return User.objects(id=data.get("uid")).first()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Decorator — require a valid Bearer token
# ---------------------------------------------------------------------------
def token_required(f):
    """Decorator that enforces a valid ``Authorization: Bearer <token>`` header."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        user = verify_token(token)
        if user is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Inject the authenticated user into kwargs
        kwargs["current_user"] = user
        return f(*args, **kwargs)

    return decorated


def admin_token_required(f):
    """Like token_required, but also enforces admin role."""

    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        user: User = kwargs["current_user"]
        if user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    """
    Authenticate and receive a Bearer token.

    JSON body: { "full_name": "...", "worker_id": "..." }
    """
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    worker_id = (data.get("worker_id") or "").strip()

    if not full_name or not worker_id:
        return jsonify({"error": "full_name and worker_id are required"}), 400

    user = User.objects(worker_id=worker_id.upper()).first()

    if not user or user.full_name.strip().casefold() != full_name.casefold():
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user)
    return jsonify({
        "token": token,
        "user": serialize_user(user),
    }), 200


@api_bp.route("/auth/me")
@token_required
def api_me(current_user: User):
    """Return the profile of the currently authenticated user."""
    return jsonify(serialize_user(current_user))
