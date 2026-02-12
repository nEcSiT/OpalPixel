"""
Entry point for running the OpalPixel application.

Usage:
    python3 run.py                   # development (default)
    FLASK_ENV=production python3 run.py
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
