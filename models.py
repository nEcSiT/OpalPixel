import mongoengine as me
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(UserMixin, me.Document):
    """User model for MongoDB"""
    meta = {'collection': 'users'}
    
    full_name = me.StringField(required=True, max_length=100)
    worker_id = me.StringField(required=True, unique=True, max_length=50)
    position = me.StringField(max_length=50)
    nationality = me.StringField(max_length=80)
    location = me.StringField(max_length=150)
    address = me.StringField(max_length=255)
    image_path = me.StringField(max_length=255)
    role = me.StringField(default='worker', max_length=20)  # 'admin' or 'worker'
    password_hash = me.StringField(max_length=256)

    def get_id(self):
        return str(self.id)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False


class InvoiceItem(me.EmbeddedDocument):
    """Embedded document for invoice line items"""
    description = me.StringField(required=True, max_length=200)
    quantity = me.IntField(required=True)
    unit_price = me.FloatField(required=True)
    total = me.FloatField(required=True)


class Invoice(me.Document):
    """Invoice model for MongoDB"""
    meta = {'collection': 'invoices'}
    
    invoice_number = me.StringField(unique=True, sparse=True, max_length=30)
    client_name = me.StringField(required=True, max_length=100)
    client_email = me.StringField(max_length=120)
    client_phone = me.StringField(max_length=30)
    client_address = me.StringField(max_length=255)
    amount = me.FloatField(required=True)
    tax_rate = me.FloatField(default=0.0)
    tax_amount = me.FloatField(default=0.0)
    status = me.StringField(default='Pending', max_length=20)  # Pending, Paid
    date_created = me.DateTimeField(default=datetime.utcnow)
    due_date = me.DateTimeField()
    user_id = me.ReferenceField('User', required=True)
    items = me.EmbeddedDocumentListField(InvoiceItem)


class Receipt(me.Document):
    """Receipt model for MongoDB"""
    meta = {'collection': 'receipts'}
    
    invoice_id = me.ReferenceField(Invoice, required=True)
    payment_date = me.DateTimeField(default=datetime.utcnow)
    amount_paid = me.FloatField(required=True)
    receipt_number = me.StringField(required=True, unique=True, max_length=50)
