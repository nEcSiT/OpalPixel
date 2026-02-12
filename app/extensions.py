"""
Flask extension instances.

Extensions are instantiated here (without an app) and bound to the
application inside the factory function ``create_app``.
"""

import mongoengine
from flask_login import LoginManager


def init_db(app):
    """Connect MongoEngine to the MongoDB instance configured in the app."""
    mongodb_uri = app.config.get(
        "MONGODB_URI", "mongodb://localhost:27017/opalpixel"
    )
    mongoengine.connect(host=mongodb_uri)


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
