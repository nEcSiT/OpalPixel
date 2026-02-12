"""
Invoice CRUD routes — create, view, edit, pay, receipts.
"""

import uuid
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app.models import Invoice, InvoiceItem, Receipt
from app.services.invoice_service import generate_invoice_number

invoices_bp = Blueprint("invoices", __name__)


def _get_invoice(invoice_id):
    """Fetch an invoice by ID, returning None on invalid/missing ID."""
    try:
        return Invoice.objects(id=invoice_id).first()
    except Exception:
        return None


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------
@invoices_bp.route("/create-invoice", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        client_name = request.form.get("client_name")
        client_email = request.form.get("client_email")
        client_phone = request.form.get("client_phone")
        client_address = request.form.get("client_address")
        date_str = request.form.get("due_date")
        due_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()

        descriptions = request.form.getlist("descriptions[]")
        quantities = request.form.getlist("quantities[]")
        prices = request.form.getlist("prices[]")
        tax_rate = float(request.form.get("tax_rate") or 0)

        subtotal = 0.0
        items: list[InvoiceItem] = []
        for i in range(len(descriptions)):
            if descriptions[i]:
                qty = int(quantities[i]) if quantities[i] else 0
                price = float(prices[i]) if prices[i] else 0.0
                line_total = qty * price
                subtotal += line_total
                items.append(
                    InvoiceItem(description=descriptions[i], quantity=qty, unit_price=price, total=line_total)
                )

        tax_amount = subtotal * (tax_rate / 100.0)
        total_amount = subtotal + tax_amount

        new_invoice = Invoice(
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            client_address=client_address,
            amount=total_amount,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            due_date=due_date,
            user_id=current_user.id,
            status="Pending",
            invoice_number=generate_invoice_number(due_date),
            items=items,
        )
        new_invoice.save()

        flash("Invoice created successfully!")
        if current_user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("worker.dashboard"))

    return render_template(
        "create_invoice.html",
        next_invoice_number=generate_invoice_number(),
        user=current_user,
    )


# --------------------------------------------------------------------------
# View
# --------------------------------------------------------------------------
@invoices_bp.route("/invoice/<invoice_id>")
@login_required
def view(invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        flash("Invoice not found.")
        return redirect(url_for("admin.dashboard"))

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        flash("You can only view your own invoices.")
        return redirect(url_for("worker.dashboard"))

    return render_template("invoice_detail.html", invoice=invoice, user=current_user)


# --------------------------------------------------------------------------
# Edit
# --------------------------------------------------------------------------
@invoices_bp.route("/invoice/<invoice_id>/edit", methods=["GET", "POST"])
@login_required
def edit(invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        flash("Invoice not found.")
        return redirect(url_for("admin.dashboard"))

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        flash("You can only edit your own invoices.")
        return redirect(url_for("worker.dashboard"))

    if invoice.status == "Paid":
        flash("Cannot edit a paid invoice.")
        return redirect(url_for("invoices.view", invoice_id=invoice_id))

    if request.method == "POST":
        invoice.client_name = request.form.get("client_name")
        invoice.client_email = request.form.get("client_email")
        invoice.client_phone = request.form.get("client_phone")
        invoice.client_address = request.form.get("client_address")
        date_str = request.form.get("due_date")
        if date_str:
            invoice.due_date = datetime.strptime(date_str, "%Y-%m-%d")

        descriptions = request.form.getlist("descriptions[]")
        quantities = request.form.getlist("quantities[]")
        prices = request.form.getlist("prices[]")
        tax_rate = float(request.form.get("tax_rate") or 0)

        # Replace items
        new_items: list[InvoiceItem] = []
        subtotal = 0.0
        for i in range(len(descriptions)):
            if descriptions[i]:
                qty = int(quantities[i]) if quantities[i] else 0
                price = float(prices[i]) if prices[i] else 0.0
                line_total = qty * price
                subtotal += line_total
                new_items.append(
                    InvoiceItem(
                        description=descriptions[i],
                        quantity=qty,
                        unit_price=price,
                        total=line_total,
                    )
                )

        invoice.items = new_items
        invoice.tax_rate = tax_rate
        invoice.tax_amount = subtotal * (tax_rate / 100.0)
        invoice.amount = subtotal + invoice.tax_amount
        invoice.save()

        flash("Invoice updated successfully!")
        return redirect(url_for("invoices.view", invoice_id=invoice_id))

    return render_template("edit_invoice.html", invoice=invoice, user=current_user)


# --------------------------------------------------------------------------
# Pay
# --------------------------------------------------------------------------
@invoices_bp.route("/pay-invoice/<invoice_id>", methods=["POST"])
@login_required
def pay(invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        flash("Invoice not found.")
        return redirect(url_for("admin.dashboard"))

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        flash("You can only manage your own invoices.")
        return redirect(url_for("worker.dashboard"))

    if invoice.status != "Paid":
        invoice.status = "Paid"
        invoice.save()
        receipt = Receipt(
            invoice_id=invoice.id,
            amount_paid=invoice.amount,
            receipt_number=f"REC-{uuid.uuid4().hex[:8].upper()}",
        )
        receipt.save()
        flash("Invoice paid and receipt generated!")

    if current_user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("worker.dashboard"))


# --------------------------------------------------------------------------
# Receipt
# --------------------------------------------------------------------------
@invoices_bp.route("/receipt/<invoice_id>")
@login_required
def view_receipt(invoice_id):
    invoice = _get_invoice(invoice_id)
    if not invoice:
        flash("Invoice not found.")
        return redirect(url_for("admin.dashboard"))

    if current_user.role != "admin" and invoice.user_id != current_user.id:
        flash("You can only view receipts for your own invoices.")
        return redirect(url_for("worker.dashboard"))

    receipt = Receipt.objects(invoice_id=invoice.id).first()
    if not receipt:
        flash("Receipt not found or invoice not paid yet.")
        if current_user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("worker.dashboard"))

    return render_template("official_receipt.html", invoice=invoice, receipt=receipt, user=current_user)


# --------------------------------------------------------------------------
# Static pages
# --------------------------------------------------------------------------
@invoices_bp.route("/receipt-workflow")
def receipt_workflow():
    return render_template("receipt_workflow.html")


@invoices_bp.route("/official-receipt")
def official_receipt():
    return render_template("official_receipt.html")
