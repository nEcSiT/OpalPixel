"""
Worker routes — personal dashboard, invoices, receipts.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.models import Invoice, Receipt

worker_bp = Blueprint("worker", __name__, url_prefix="/worker")


@worker_bp.route("/dashboard")
@login_required
def dashboard():
    """Worker's personal dashboard showing their own stats."""
    my_invoices = list(
        Invoice.objects(user_id=current_user.id).order_by('-date_created')
    )
    stats = {
        "total_invoices": len(my_invoices),
        "pending_invoices": sum(1 for i in my_invoices if i.status == "Pending"),
        "paid_invoices": sum(1 for i in my_invoices if i.status == "Paid"),
        "total_revenue": sum(i.amount for i in my_invoices if i.status == "Paid"),
    }
    return render_template(
        "worker_dashboard.html",
        user=current_user,
        stats=stats,
        recent_invoices=my_invoices[:5],
    )


@worker_bp.route("/invoices")
@login_required
def my_invoices():
    """Worker's own invoices."""
    invoices = list(
        Invoice.objects(user_id=current_user.id).order_by('-date_created')
    )
    return render_template("my_invoices.html", user=current_user, invoices=invoices)


@worker_bp.route("/receipts")
@login_required
def my_receipts():
    """Receipts from the worker's paid invoices."""
    my_inv_ids = [
        i.id for i in Invoice.objects(user_id=current_user.id).only('id')
    ]
    receipts = list(
        Receipt.objects(invoice_id__in=my_inv_ids).order_by('-payment_date')
    )
    return render_template("my_receipts.html", user=current_user, receipts=receipts)
