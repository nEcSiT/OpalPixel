from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from typing import Optional

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    worker_id = db.Column(db.String(50), unique=True, nullable=False)
    position = db.Column(db.String(50))
    nationality = db.Column(db.String(80))
    location = db.Column(db.String(150))
    address = db.Column(db.String(255))
    image_path = db.Column(db.String(255))
    role = db.Column(db.String(20), default='worker') # 'admin' or 'worker'
    password_hash = db.Column(db.String(128))

    def __init__(self, full_name: str, worker_id: str, position: Optional[str] = None,
                 nationality: Optional[str] = None, location: Optional[str] = None,
                 address: Optional[str] = None, image_path: Optional[str] = None,
                 role: str = 'worker', password_hash: Optional[str] = None):
        self.full_name = full_name
        self.worker_id = worker_id
        self.position = position
        self.nationality = nationality
        self.location = location
        self.address = address
        self.image_path = image_path
        self.role = role
        self.password_hash = password_hash

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(30), unique=True)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120))
    client_phone = db.Column(db.String(30))
    client_address = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Pending') # Pending, Paid
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='invoices', lazy=True)
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True)
    receipt = db.relationship('Receipt', backref='invoice', uselist=False, lazy=True)

    def __init__(self, client_name: str, amount: float, user_id: int,
                 invoice_number: Optional[str] = None, client_email: Optional[str] = None,
                 client_phone: Optional[str] = None, client_address: Optional[str] = None,
                 tax_rate: float = 0.0, tax_amount: float = 0.0, status: str = 'Pending',
                 due_date: Optional[datetime] = None):
        self.invoice_number = invoice_number
        self.client_name = client_name
        self.client_email = client_email
        self.client_phone = client_phone
        self.client_address = client_address
        self.amount = amount
        self.tax_rate = tax_rate
        self.tax_amount = tax_amount
        self.status = status
        self.due_date = due_date
        self.user_id = user_id

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)

    def __init__(self, invoice_id: int, description: str, quantity: int,
                 unit_price: float, total: float):
        self.invoice_id = invoice_id
        self.description = description
        self.quantity = quantity
        self.unit_price = unit_price
        self.total = total

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount_paid = db.Column(db.Float, nullable=False)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)

    def __init__(self, invoice_id: int, amount_paid: float, receipt_number: str):
        self.invoice_id = invoice_id
        self.amount_paid = amount_paid
        self.receipt_number = receipt_number
