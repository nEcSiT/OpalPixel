"""
Miscellaneous helper functions.
"""

import random
import string

from app.models import User


def generate_worker_id() -> str:
    """Return a unique worker ID in the format ``OPL-XXXXXXXX``."""
    while True:
        digits = "".join(random.choices(string.digits, k=8))
        wid = f"OPL-{digits}"
        if not User.objects(worker_id=wid).first():
            return wid
