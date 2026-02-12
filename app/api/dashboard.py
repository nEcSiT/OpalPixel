"""
API — Dashboard statistics.
"""

from datetime import datetime

from flask import jsonify

from app.models import User, Invoice, Receipt
from app.api import api_bp
from app.api.auth import token_required


@api_bp.route("/dashboard/stats", methods=["GET"])
@token_required
def dashboard_stats(current_user: User):
    """
    Summary statistics.

    Admins get global numbers; workers get their own.
    """
    today = datetime.utcnow().date()

    if current_user.role == "admin":
        invoices = list(Invoice.objects())
        receipts_count = Receipt.objects.count()
        workers_count = User.objects(role="worker").count()
    else:
        invoices = list(Invoice.objects(user_id=current_user.id))
        my_inv_ids = [i.id for i in invoices]
        receipts_count = Receipt.objects(invoice_id__in=my_inv_ids).count() if my_inv_ids else 0
        workers_count = None

    paid = [i for i in invoices if i.status == "Paid"]
    pending = [i for i in invoices if i.status == "Pending"]

    stats = {
        "total_invoices": len(invoices),
        "paid_invoices": len(paid),
        "pending_invoices": len(pending),
        "total_revenue": sum(i.amount for i in paid),
        "pending_amount": sum(i.amount for i in pending),
        "total_receipts": receipts_count,
        "invoices_today": sum(
            1 for i in invoices if i.date_created and i.date_created.date() == today
        ),
    }

    if workers_count is not None:
        stats["active_workers"] = workers_count

    return jsonify(stats)
