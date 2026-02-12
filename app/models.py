"""
MongoEngine document models.

All collections are defined here. Connect to MongoDB via
``mongoengine.connect()`` in the application factory.
"""

from datetime import datetime

import mongoengine as me
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(UserMixin, me.Document):
    """Application user — admin or worker."""

    meta = {"collection": "users", "indexes": ["worker_id"]}

    full_name = me.StringField(required=True, max_length=100)
    worker_id = me.StringField(required=True, unique=True, max_length=50)
    position = me.StringField(max_length=50)
    nationality = me.StringField(max_length=80)
    location = me.StringField(max_length=150)
    address = me.StringField(max_length=255)
    image_path = me.StringField(max_length=255)
    role = me.StringField(default="worker", required=True, max_length=20)
    password_hash = me.StringField(max_length=256)

    # -- Authentication helpers ------------------------------------------------

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False

    def __repr__(self) -> str:
        return f"<User {self.worker_id}>"


# ---------------------------------------------------------------------------
# InvoiceItem (embedded inside Invoice)
# ---------------------------------------------------------------------------
class InvoiceItem(me.EmbeddedDocument):
    """A single line item on an invoice."""

    description = me.StringField(required=True, max_length=200)
    quantity = me.IntField(required=True)
    unit_price = me.FloatField(required=True)
    total = me.FloatField(required=True)

    def __repr__(self) -> str:
        return f"<InvoiceItem {self.description[:30]}>"


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------
class Invoice(me.Document):
    """Client invoice with embedded line items."""

    meta = {"collection": "invoices", "indexes": ["invoice_number", "user_id"]}

    invoice_number = me.StringField(unique=True, max_length=30)
    client_name = me.StringField(required=True, max_length=100)
    client_email = me.StringField(max_length=120)
    client_phone = me.StringField(max_length=30)
    client_address = me.StringField(max_length=255)
    amount = me.FloatField(required=True)
    tax_rate = me.FloatField(default=0.0)
    tax_amount = me.FloatField(default=0.0)
    status = me.StringField(default="Pending", required=True, max_length=20)
    date_created = me.DateTimeField(default=datetime.utcnow)
    due_date = me.DateTimeField()
    user_id = me.ObjectIdField(required=True)

    items = me.EmbeddedDocumentListField(InvoiceItem)

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number}>"


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------
class Receipt(me.Document):
    """Payment receipt linked to an invoice."""

    meta = {"collection": "receipts", "indexes": ["invoice_id", "receipt_number"]}

    invoice_id = me.ObjectIdField(required=True)
    payment_date = me.DateTimeField(default=datetime.utcnow)
    amount_paid = me.FloatField(required=True)
    receipt_number = me.StringField(unique=True, required=True, max_length=50)

    def __repr__(self) -> str:
        return f"<Receipt {self.receipt_number}>"
