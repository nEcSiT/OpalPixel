"""
CSV export routes (admin only).
"""

import csv
import io
from datetime import datetime

from flask import Blueprint, redirect, url_for, Response
from flask_login import login_required

from app.models import User, Invoice, Receipt
from app.utils.decorators import admin_required

exports_bp = Blueprint("exports", __name__, url_prefix="/export")


def _csv_response(output: io.StringIO, filename: str) -> Response:
    """Build a CSV download response."""
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------
@exports_bp.route("/invoices")
@login_required
@admin_required
def invoices_csv():
    invoices = Invoice.objects.order_by('-date_created')
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Invoice Number", "Client Name", "Client Email", "Client Phone",
        "Client Address", "Amount (GH₵)", "Tax Rate (%)", "Tax Amount (GH₵)",
        "Status", "Date Created", "Due Date", "Created By", "Worker ID",
    ])
    for inv in invoices:
        creator = User.objects(id=inv.user_id).first()
        w.writerow([
            inv.invoice_number or f"INV-{str(inv.id)[:8]}",
            inv.client_name,
            inv.client_email or "",
            inv.client_phone or "",
            inv.client_address or "",
            f"{inv.amount:.2f}",
            f"{inv.tax_rate:.2f}",
            f"{inv.tax_amount:.2f}",
            inv.status,
            inv.date_created.strftime("%Y-%m-%d %H:%M") if inv.date_created else "",
            inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "",
            creator.full_name if creator else "",
            creator.worker_id if creator else "",
        ])
    return _csv_response(buf, f"invoices_{_timestamp()}.csv")


# --------------------------------------------------------------------------
# Receipts
# --------------------------------------------------------------------------
@exports_bp.route("/receipts")
@login_required
@admin_required
def receipts_csv():
    receipts = Receipt.objects.order_by('-payment_date')
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Receipt Number", "Invoice Number", "Client Name", "Client Email",
        "Client Phone", "Client Address", "Amount Paid (GH₵)", "Payment Date",
        "Issued By", "Worker ID",
    ])
    for rec in receipts:
        inv = Invoice.objects(id=rec.invoice_id).first()
        creator = User.objects(id=inv.user_id).first() if inv else None
        w.writerow([
            rec.receipt_number,
            inv.invoice_number if inv else "",
            inv.client_name if inv else "",
            (inv.client_email or "") if inv else "",
            (inv.client_phone or "") if inv else "",
            (inv.client_address or "") if inv else "",
            f"{rec.amount_paid:.2f}",
            rec.payment_date.strftime("%Y-%m-%d %H:%M") if rec.payment_date else "",
            creator.full_name if creator else "",
            creator.worker_id if creator else "",
        ])
    return _csv_response(buf, f"receipts_{_timestamp()}.csv")


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
@exports_bp.route("/clients")
@login_required
@admin_required
def clients_csv():
    invoices = Invoice.objects.order_by('client_name')
    seen: dict[str, dict] = {}
    for inv in invoices:
        key = inv.client_name.lower().strip()
        if key not in seen:
            seen[key] = {
                "name": inv.client_name,
                "email": inv.client_email or "",
                "phone": inv.client_phone or "",
                "address": inv.client_address or "",
                "total_invoices": 0,
                "total_amount": 0.0,
                "paid_amount": 0.0,
            }
        seen[key]["total_invoices"] += 1
        seen[key]["total_amount"] += inv.amount
        if inv.status == "Paid":
            seen[key]["paid_amount"] += inv.amount

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Client Name", "Email", "Phone", "Address",
        "Total Invoices", "Total Amount (GH₵)", "Paid Amount (GH₵)",
    ])
    for c in seen.values():
        w.writerow([
            c["name"], c["email"], c["phone"], c["address"],
            c["total_invoices"], f'{c["total_amount"]:.2f}', f'{c["paid_amount"]:.2f}',
        ])
    return _csv_response(buf, f"clients_{_timestamp()}.csv")


# --------------------------------------------------------------------------
# Full Report
# --------------------------------------------------------------------------
@exports_bp.route("/all")
@login_required
@admin_required
def all_csv():
    invoices = Invoice.objects.order_by('-date_created')
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Invoice Number", "Client Name", "Client Email", "Client Phone",
        "Client Address", "Item Description", "Quantity", "Unit Price (GH₵)",
        "Line Total (GH₵)", "Invoice Total (GH₵)", "Tax Rate (%)",
        "Tax Amount (GH₵)", "Status", "Date Created", "Due Date",
        "Receipt Number", "Payment Date", "Created By", "Worker ID",
    ])
    for inv in invoices:
        creator = User.objects(id=inv.user_id).first()
        receipt = Receipt.objects(invoice_id=inv.id).first()
        rec_num = receipt.receipt_number if receipt else ""
        pay_date = (
            receipt.payment_date.strftime("%Y-%m-%d %H:%M")
            if receipt and receipt.payment_date
            else ""
        )
        inv_items = inv.items
        base = [
            inv.invoice_number or f"INV-{str(inv.id)[:8]}",
            inv.client_name,
            inv.client_email or "",
            inv.client_phone or "",
            inv.client_address or "",
        ]
        tail = [
            f"{inv.amount:.2f}",
            f"{inv.tax_rate:.2f}",
            f"{inv.tax_amount:.2f}",
            inv.status,
            inv.date_created.strftime("%Y-%m-%d %H:%M") if inv.date_created else "",
            inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "",
            rec_num,
            pay_date,
            creator.full_name if creator else "",
            creator.worker_id if creator else "",
        ]
        if inv_items:
            for item in inv_items:
                w.writerow(base + [item.description, item.quantity, f"{item.unit_price:.2f}", f"{item.total:.2f}"] + tail)
        else:
            w.writerow(base + ["", "", "", ""] + tail)

    return _csv_response(buf, f"full_report_{_timestamp()}.csv")
