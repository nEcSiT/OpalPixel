import random
import string
from models import User

def generate_worker_id():
    while True:
        # Format: OPL-12345678 (8 digits)
        random_digits = ''.join(random.choices(string.digits, k=8))
        worker_id = f"OPL-{random_digits}"
        if not User.query.filter_by(worker_id=worker_id).first():
            return worker_id
