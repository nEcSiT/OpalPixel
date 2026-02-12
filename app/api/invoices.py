"""
API — Invoice CRUD and payment.
"""

import uuid
from datetime import datetime

from flask import jsonify, request

from app.models import User, Invoice, InvoiceItem, Receipt
from app.api import api_bp
from app.api.auth import token_required, admin_token_required
from app.api.schemas import serialize_invoice, serialize_receipt
from app.services.invoice_service import generate_invoice_number


def _get_invoice(invoice_id):
    try:
        return Invoice.objects(id=invoice_id).first()
    except Exception:
        return None


# --------------------------------------------------------------------------
# List invoices
# --------------------------------------------------------------------------
@api_bp.route("/invoices", methods=["GET"])
@token_required
def list_invoices(current_user: User):
    """
    Admins see all invoices; workers see only their own.
    Optional query params: status, client_name, page, per_page.
    """
    query = Invoice.objects()

    if current_user.role != "admin":
        query = query.filter(user_id=current_user.id)

    status = request.args.get("status")
    if status:
        query = query.filter(status=status)

    client = request.args.get("client_name")
    if client:
        query = query.filter(client_name__icontains=client)

    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("per_page", 25)), 100)

    query = query.order_by('-date_created')
    total = query.count()
    items = list(query.skip((page - 1) * per_page).limit(per_page))
    pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        "invoices": [serialize_invoice(i) for i in items],
        "total": total,
        "page": page,
        "pages": pages,
    })


# --------------------------------------------------------------------------
# Get single invoice
# --------------------------------------------------------------------------
@api_bp.route("/invoices/<invoice_id>", methods=["GET"])
@token_required
def get_invoice(current_user: User, invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    return jsonify(serialize_invoice(invoice, include_items=True))


# --------------------------------------------------------------------------
# Create invoice
# --------------------------------------------------------------------------
@api_bp.route("/invoices", methods=["POST"])
@token_required
def create_invoice(current_user: User):
    """
    JSON body:
    {
      "client_name": "...",
      "client_email": "...",
      "client_phone": "...",
      "client_address": "...",
      "due_date": "2026-03-01",
      "tax_rate": 0,
      "items": [
        { "description": "...", "quantity": 1, "unit_price": 100.0 }
      ]
    }
    """
    data = request.get_json(silent=True) or {}

    client_name = (data.get("client_name") or "").strip()
    if not client_name:
        return jsonify({"error": "client_name is required"}), 400

    items_data = data.get("items") or []
    if not items_data:
        return jsonify({"error": "At least one item is required"}), 400

    due_date_str = data.get("due_date")
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d") if due_date_str else datetime.utcnow()
    except (ValueError, TypeError):
        return jsonify({"error": "due_date must be YYYY-MM-DD format"}), 400

    tax_rate = float(data.get("tax_rate", 0))

    # Build line items
    subtotal = 0.0
    items: list[InvoiceItem] = []
    for entry in items_data:
        desc = (entry.get("description") or "").strip()
        qty = int(entry.get("quantity", 0))
        price = float(entry.get("unit_price", 0))
        if not desc or qty <= 0 or price <= 0:
            continue
        line_total = qty * price
        subtotal += line_total
        items.append(InvoiceItem(description=desc, quantity=qty, unit_price=price, total=line_total))

    if not items:
        return jsonify({"error": "No valid items provided"}), 400

    tax_amount = subtotal * (tax_rate / 100.0)
    total_amount = subtotal + tax_amount

    invoice = Invoice(
        client_name=client_name,
        client_email=(data.get("client_email") or "").strip() or None,
        client_phone=(data.get("client_phone") or "").strip() or None,
        client_address=(data.get("client_address") or "").strip() or None,
        amount=total_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        due_date=due_date,
        user_id=current_user.id,
        status="Pending",
        invoice_number=generate_invoice_number(due_date),
        items=items,
    )
    invoice.save()

    return jsonify(serialize_invoice(invoice, include_items=True)), 201


# --------------------------------------------------------------------------
# Update invoice
# --------------------------------------------------------------------------
@api_bp.route("/invoices/<invoice_id>", methods=["PUT", "PATCH"])
@token_required
def update_invoice(current_user: User, invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    if invoice.status == "Paid":
        return jsonify({"error": "Cannot edit a paid invoice"}), 400

    data = request.get_json(silent=True) or {}

    if "client_name" in data:
        invoice.client_name = (data["client_name"] or "").strip() or invoice.client_name
    if "client_email" in data:
        invoice.client_email = (data["client_email"] or "").strip() or None
    if "client_phone" in data:
        invoice.client_phone = (data["client_phone"] or "").strip() or None
    if "client_address" in data:
        invoice.client_address = (data["client_address"] or "").strip() or None
    if "due_date" in data:
        try:
            invoice.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            return jsonify({"error": "due_date must be YYYY-MM-DD format"}), 400

    # Replace items if provided
    if "items" in data:
        items_data = data["items"] or []
        new_items: list[InvoiceItem] = []
        subtotal = 0.0
        tax_rate = float(data.get("tax_rate", invoice.tax_rate))
        for entry in items_data:
            desc = (entry.get("description") or "").strip()
            qty = int(entry.get("quantity", 0))
            price = float(entry.get("unit_price", 0))
            if not desc or qty <= 0 or price <= 0:
                continue
            line_total = qty * price
            subtotal += line_total
            new_items.append(InvoiceItem(
                description=desc, quantity=qty, unit_price=price, total=line_total,
            ))

        invoice.items = new_items
        invoice.tax_rate = tax_rate
        invoice.tax_amount = subtotal * (tax_rate / 100.0)
        invoice.amount = subtotal + invoice.tax_amount
    elif "tax_rate" in data:
        # Recalculate with existing items
        subtotal = sum(item.total for item in invoice.items)
        invoice.tax_rate = float(data["tax_rate"])
        invoice.tax_amount = subtotal * (invoice.tax_rate / 100.0)
        invoice.amount = subtotal + invoice.tax_amount

    invoice.save()
    return jsonify(serialize_invoice(invoice, include_items=True))


# --------------------------------------------------------------------------
# Delete invoice
# --------------------------------------------------------------------------
@api_bp.route("/invoices/<invoice_id>", methods=["DELETE"])
@token_required
def delete_invoice(current_user: User, invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    if invoice.status == "Paid":
        return jsonify({"error": "Cannot delete a paid invoice"}), 400

    # Also remove linked receipts
    Receipt.objects(invoice_id=invoice.id).delete()
    invoice.delete()
    return jsonify({"message": "Invoice deleted"}), 200


# --------------------------------------------------------------------------
# Pay invoice → generate receipt
# --------------------------------------------------------------------------
@api_bp.route("/invoices/<invoice_id>/pay", methods=["POST"])
@token_required
def pay_invoice(current_user: User, invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    if invoice.status == "Paid":
        return jsonify({"error": "Invoice is already paid"}), 400

    invoice.status = "Paid"
    invoice.save()

    receipt = Receipt(
        invoice_id=invoice.id,
        amount_paid=invoice.amount,
        receipt_number=f"REC-{uuid.uuid4().hex[:8].upper()}",
    )
    receipt.save()

    return jsonify({
        "message": "Invoice paid",
        "invoice": serialize_invoice(invoice),
        "receipt": serialize_receipt(receipt),
    }), 200
