"""
Application configuration.

Environment-based config classes following the 12-factor app methodology.
Sensitive values are read exclusively from environment variables.
"""

import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # MongoDB
    MONGODB_URI = os.environ.get(
        "MONGODB_URI", "mongodb://localhost:27017/opalpixel"
    )

    # File uploads
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB upload limit

    # Cloudinary (image CDN)
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")


class DevelopmentConfig(Config):
    """Local development — debug on."""

    DEBUG = True


class ProductionConfig(Config):
    """Production — expects MONGODB_URI and SECRET_KEY in env."""

    DEBUG = False


class TestingConfig(Config):
    """Automated tests — separate test database."""

    TESTING = True
    MONGODB_URI = os.environ.get(
        "MONGODB_URI", "mongodb://localhost:27017/opalpixel_test"
    )


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
