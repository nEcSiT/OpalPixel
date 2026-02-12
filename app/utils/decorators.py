"""
Reusable route decorators.
"""

from functools import wraps

from flask import redirect, url_for
from flask_login import current_user


def admin_required(f):
    """Restrict a view to users with the *admin* role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return redirect(url_for("worker.dashboard"))
        return f(*args, **kwargs)
    return decorated_function
