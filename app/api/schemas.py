"""
Model serialization helpers for API responses.
"""

from __future__ import annotations

from app.models import User, Invoice, InvoiceItem, Receipt


def serialize_user(user: User, *, brief: bool = False) -> dict:
    """Return a JSON-safe dict for a User."""
    data = {
        "id": str(user.id),
        "full_name": user.full_name,
        "worker_id": user.worker_id,
        "role": user.role,
    }
    if not brief:
        data.update({
            "position": user.position,
            "nationality": user.nationality,
            "location": user.location,
            "address": user.address,
            "image_path": user.image_path,
        })
    return data


def serialize_invoice_item(item: InvoiceItem) -> dict:
    return {
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "total": item.total,
    }


def serialize_invoice(invoice: Invoice, *, include_items: bool = False) -> dict:
    """Return a JSON-safe dict for an Invoice."""
    data = {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "client_name": invoice.client_name,
        "client_email": invoice.client_email,
        "client_phone": invoice.client_phone,
        "client_address": invoice.client_address,
        "amount": invoice.amount,
        "tax_rate": invoice.tax_rate,
        "tax_amount": invoice.tax_amount,
        "status": invoice.status,
        "date_created": invoice.date_created.isoformat() if invoice.date_created else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "user_id": str(invoice.user_id),
    }
    if include_items:
        data["items"] = [serialize_invoice_item(i) for i in invoice.items]
    return data


def serialize_receipt(receipt: Receipt) -> dict:
    return {
        "id": str(receipt.id),
        "invoice_id": str(receipt.invoice_id),
        "receipt_number": receipt.receipt_number,
        "amount_paid": receipt.amount_paid,
        "payment_date": receipt.payment_date.isoformat() if receipt.payment_date else None,
    }
