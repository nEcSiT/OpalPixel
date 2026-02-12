"""
API — Receipt endpoints.
"""

from flask import jsonify, request

from app.models import User, Invoice, Receipt
from app.api import api_bp
from app.api.auth import token_required
from app.api.schemas import serialize_receipt


# --------------------------------------------------------------------------
# List receipts
# --------------------------------------------------------------------------
@api_bp.route("/receipts", methods=["GET"])
@token_required
def list_receipts(current_user: User):
    """Admins see all receipts; workers see only their own."""
    if current_user.role == "admin":
        query = Receipt.objects()
    else:
        my_inv_ids = [
            i.id for i in Invoice.objects(user_id=current_user.id).only('id')
        ]
        query = Receipt.objects(invoice_id__in=my_inv_ids)

    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("per_page", 25)), 100)

    query = query.order_by('-payment_date')
    total = query.count()
    items = list(query.skip((page - 1) * per_page).limit(per_page))
    pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        "receipts": [serialize_receipt(r) for r in items],
        "total": total,
        "page": page,
        "pages": pages,
    })


# --------------------------------------------------------------------------
# Get single receipt
# --------------------------------------------------------------------------
@api_bp.route("/receipts/<receipt_id>", methods=["GET"])
@token_required
def get_receipt(current_user: User, receipt_id):
    try:
        receipt = Receipt.objects(id=receipt_id).first()
    except Exception:
        receipt = None
    if not receipt:
        return jsonify({"error": "Receipt not found"}), 404

    if current_user.role != "admin":
        try:
            invoice = Invoice.objects(id=receipt.invoice_id).first()
        except Exception:
            invoice = None
        if not invoice or invoice.user_id != current_user.id:
            return jsonify({"error": "Access denied"}), 403

    return jsonify(serialize_receipt(receipt))
