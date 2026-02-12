"""
RESTful API v1 — JSON endpoints for OpalPixel.

All routes are prefixed with ``/api/v1``.
"""

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

from app.api import auth, users, invoices, receipts, dashboard  # noqa: E402, F401
