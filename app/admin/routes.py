"""
Admin-only routes — dashboard, user management, reports, settings, logs, team.
"""

import json
import uuid
import calendar
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
import cloudinary.uploader

from app.models import User, Invoice, Receipt
from app.utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__)


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    invoices = list(Invoice.objects.order_by('-date_created'))
    workers = list(User.objects(role="worker"))
    receipts = list(Receipt.objects.order_by('-payment_date'))

    today = datetime.utcnow().date()
    stats = {
        "revenue": sum(i.amount for i in invoices if i.status == "Paid"),
        "invoices_today": sum(
            1 for i in invoices if i.date_created and i.date_created.date() == today
        ),
        "pending": sum(1 for i in invoices if i.status == "Pending"),
        "active_workers": len(workers),
    }

    activities: list[dict] = []
    for inv in invoices[:8]:
        activities.append(
            {
                "type": "invoice",
                "title": f"Invoice {inv.invoice_number or str(inv.id)[:8]} ({inv.status})",
                "meta": inv.client_name,
                "timestamp": inv.date_created,
            }
        )
    for rec in receipts[:8]:
        inv = Invoice.objects(id=rec.invoice_id).first()
        activities.append(
            {
                "type": "receipt",
                "title": f"Receipt {rec.receipt_number}",
                "meta": inv.client_name if inv else "—",
                "timestamp": rec.payment_date,
            }
        )
    activities.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)

    return render_template(
        "admin_dashboard.html",
        user=current_user,
        invoices=invoices,
        workers=workers,
        stats=stats,
        recent_activities=activities[:8],
    )


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------
@admin_bp.route("/invoices")
@login_required
@admin_required
def invoices_list():
    invoices = list(Invoice.objects.order_by('-date_created'))
    return render_template("invoices_list.html", user=current_user, invoices=invoices)


@admin_bp.route("/receipts")
@login_required
@admin_required
def receipts_list():
    receipts = list(Receipt.objects.order_by('-payment_date'))
    return render_template("receipts_list.html", user=current_user, receipts=receipts)


@admin_bp.route("/team")
@login_required
@admin_required
def team_list():
    workers = list(User.objects(role="worker"))
    return render_template("team_list.html", user=current_user, workers=workers)


# --------------------------------------------------------------------------
# Document Logs
# --------------------------------------------------------------------------
@admin_bp.route("/document-logs")
@login_required
@admin_required
def document_logs():
    """Combined view of invoices and receipts with filtering."""
    doc_type = request.args.get("type", "all")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    worker_filter = request.args.get("worker", "")
    status = request.args.get("status", "")
    page = int(request.args.get("page", 1))
    per_page = 15

    # Build invoice query
    inv_query = Invoice.objects()
    if worker_filter:
        inv_query = inv_query.filter(user_id=worker_filter)
    if status:
        inv_query = inv_query.filter(status=status)
    if date_from:
        inv_query = inv_query.filter(date_created__gte=datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        inv_query = inv_query.filter(date_created__lte=datetime.strptime(date_to, "%Y-%m-%d"))

    # Build receipt query
    rec_query = Receipt.objects()
    if worker_filter:
        worker_inv_ids = [
            i.id for i in Invoice.objects(user_id=worker_filter).only('id')
        ]
        rec_query = rec_query.filter(invoice_id__in=worker_inv_ids)
    if date_from:
        rec_query = rec_query.filter(payment_date__gte=datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        rec_query = rec_query.filter(payment_date__lte=datetime.strptime(date_to, "%Y-%m-%d"))

    invoices = (
        list(inv_query.order_by('-date_created'))
        if doc_type in ("all", "invoice")
        else []
    )
    receipts = (
        list(rec_query.order_by('-payment_date'))
        if doc_type in ("all", "receipt")
        else []
    )

    documents: list[dict] = []
    for inv in invoices:
        documents.append(
            {
                "type": "invoice",
                "id": str(inv.id),
                "doc_number": inv.invoice_number or f"INV-{str(inv.id)[:8]}",
                "client_name": inv.client_name,
                "amount": inv.amount,
                "date": inv.date_created,
                "status": inv.status,
                "creator": User.objects(id=inv.user_id).first(),
            }
        )
    for rec in receipts:
        inv = Invoice.objects(id=rec.invoice_id).first()
        creator = User.objects(id=inv.user_id).first() if inv else None
        documents.append(
            {
                "type": "receipt",
                "id": str(rec.id),
                "doc_number": rec.receipt_number,
                "client_name": inv.client_name if inv else "—",
                "amount": rec.amount_paid,
                "date": rec.payment_date,
                "status": "Completed",
                "creator": creator,
                "invoice_id": str(inv.id) if inv else None,
            }
        )

    documents.sort(key=lambda x: x["date"] or datetime.min, reverse=True)

    total_count = len(documents)
    total_pages = (total_count + per_page - 1) // per_page
    start = (page - 1) * per_page
    documents = documents[start : start + per_page]

    return render_template(
        "document_logs.html",
        user=current_user,
        documents=documents,
        invoices=list(Invoice.objects()),
        receipts=list(Receipt.objects()),
        workers=list(User.objects()),
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        current_type=doc_type,
        current_date_from=date_from,
        current_date_to=date_to,
        current_worker=worker_filter,
        current_status=status,
    )


# --------------------------------------------------------------------------
# User Management
# --------------------------------------------------------------------------
@admin_bp.route("/user-management")
@login_required
@admin_required
def user_management():
    all_users = list(User.objects())
    users_data = []

    for u in all_users:
        user_invoices = list(Invoice.objects(user_id=u.id))
        users_data.append(
            {
                "user": u,
                "invoice_count": len(user_invoices),
                "revenue": sum(i.amount for i in user_invoices if i.status == "Paid"),
            }
        )

    stats = {
        "total_users": len(all_users),
        "admins": sum(1 for u in all_users if u.role == "admin"),
        "workers": sum(1 for u in all_users if u.role == "worker"),
        "total_invoices": Invoice.objects.count(),
    }

    return render_template(
        "user_management.html", user=current_user, users=users_data, stats=stats
    )


@admin_bp.route("/edit-user/<user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    try:
        user_to_edit = User.objects(id=user_id).first()
    except Exception:
        user_to_edit = None
    if not user_to_edit:
        flash("User not found.")
        return redirect(url_for("admin.user_management"))

    if request.method == "POST":
        user_to_edit.full_name = request.form.get("full_name", user_to_edit.full_name).strip()
        user_to_edit.position = request.form.get("position", "").strip() or None
        user_to_edit.location = request.form.get("location", "").strip() or None
        user_to_edit.nationality = request.form.get("nationality", "").strip() or None
        user_to_edit.role = request.form.get("role", user_to_edit.role)

        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename:
                from flask import current_app
                ext = file.filename.rsplit(".", 1)[-1].lower()
                if ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
                    try:
                        upload_result = cloudinary.uploader.upload(
                            file,
                            folder="opalpixel/profiles",
                            public_id=f"user_{user_to_edit.worker_id}_{uuid.uuid4().hex[:8]}",
                            overwrite=True,
                            transformation=[
                                {"width": 400, "height": 400, "crop": "fill", "gravity": "face"}
                            ],
                        )
                        user_to_edit.image_path = upload_result["secure_url"]
                    except Exception as e:
                        flash(f"Error uploading image: {e}")

        user_to_edit.save()
        flash("User updated successfully")
        return redirect(url_for("admin.user_management"))

    return render_template("edit_user.html", user=current_user, edit_user=user_to_edit)


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
@admin_bp.route("/reports")
@login_required
@admin_required
def reports():
    """Financial analytics with chart data."""
    selected_year = request.args.get("year", str(datetime.utcnow().year))
    selected_month = request.args.get("month", "")

    all_invoices = list(Invoice.objects.order_by('-date_created'))
    all_receipts = list(Receipt.objects())

    available_years = sorted(
        {i.date_created.year for i in all_invoices if i.date_created}, reverse=True
    ) or [datetime.utcnow().year]

    year_invoices = [
        i for i in all_invoices if i.date_created and i.date_created.year == int(selected_year)
    ]
    month_invoices = (
        [i for i in year_invoices if i.date_created.month == int(selected_month)]
        if selected_month
        else year_invoices
    )

    paid = [i for i in month_invoices if i.status == "Paid"]
    pending = [i for i in month_invoices if i.status == "Pending"]

    total_revenue = sum(i.amount for i in paid)
    total_pending = sum(i.amount for i in pending)

    # Monthly breakdown
    monthly_data = defaultdict(lambda: {"revenue": 0, "count": 0, "paid": 0, "pending": 0})
    for inv in year_invoices:
        if inv.date_created:
            mk = inv.date_created.strftime("%b")
            monthly_data[mk]["count"] += 1
            if inv.status == "Paid":
                monthly_data[mk]["revenue"] += inv.amount
                monthly_data[mk]["paid"] += 1
            else:
                monthly_data[mk]["pending"] += 1

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Daily breakdown (when a month is selected)
    daily_labels: list = []
    daily_revenue: list = []
    daily_counts: list = []
    if selected_month:
        dim = calendar.monthrange(int(selected_year), int(selected_month))[1]
        dd = defaultdict(lambda: {"revenue": 0, "count": 0})
        for inv in month_invoices:
            if inv.date_created:
                dd[inv.date_created.day]["count"] += 1
                if inv.status == "Paid":
                    dd[inv.date_created.day]["revenue"] += inv.amount
        daily_labels = list(range(1, dim + 1))
        daily_revenue = [dd[d]["revenue"] for d in daily_labels]
        daily_counts = [dd[d]["count"] for d in daily_labels]

    # Yearly breakdown
    yearly_data = defaultdict(lambda: {"revenue": 0, "count": 0})
    for inv in all_invoices:
        if inv.date_created:
            yearly_data[inv.date_created.year]["count"] += 1
            if inv.status == "Paid":
                yearly_data[inv.date_created.year]["revenue"] += inv.amount

    yearly_labels = sorted(yearly_data.keys())
    cur_rev = yearly_data.get(int(selected_year), {}).get("revenue", 0)
    prev_rev = yearly_data.get(int(selected_year) - 1, {}).get("revenue", 0)
    revenue_growth = round(((cur_rev - prev_rev) / prev_rev) * 100, 1) if prev_rev else 0

    # Top workers
    workers = list(User.objects())
    worker_stats = []
    for w in workers:
        w_invs = [i for i in month_invoices if i.user_id == w.id]
        if w_invs:
            worker_stats.append(
                {
                    "user": w,
                    "full_name": w.full_name,
                    "image_path": w.image_path,
                    "revenue": sum(i.amount for i in w_invs if i.status == "Paid"),
                    "invoice_count": len(w_invs),
                }
            )
    worker_stats.sort(key=lambda x: x["revenue"], reverse=True)

    now = datetime.utcnow()
    report = {
        "total_revenue": total_revenue,
        "total_pending": total_pending,
        "pending_amount": total_pending,
        "total_invoices": len(month_invoices),
        "total_receipts": len(all_receipts),
        "average_invoice": total_revenue / len(paid) if paid else 0,
        "avg_invoice": total_revenue / len(paid) if paid else 0,
        "status_counts": {
            "Paid": len(paid),
            "Pending": len(pending),
            "Overdue": sum(1 for i in month_invoices if i.status == "Overdue"),
        },
        "paid_invoices": len(paid),
        "pending_invoices": len(pending),
        "unique_clients": len({i.client_name for i in month_invoices}),
        "invoices_this_month": sum(
            1 for i in all_invoices
            if i.date_created and i.date_created.month == now.month and i.date_created.year == now.year
        ),
        "revenue_growth": revenue_growth,
    }

    return render_template(
        "reports.html",
        user=current_user,
        report=report,
        top_workers=worker_stats[:5],
        recent_invoices=month_invoices[:10],
        selected_year=selected_year,
        selected_month=selected_month,
        available_years=available_years,
        monthly_labels=json.dumps(month_names),
        monthly_revenue=json.dumps([monthly_data[m]["revenue"] for m in month_names]),
        monthly_counts=json.dumps([monthly_data[m]["count"] for m in month_names]),
        monthly_paid=json.dumps([monthly_data[m]["paid"] for m in month_names]),
        monthly_pending=json.dumps([monthly_data[m]["pending"] for m in month_names]),
        daily_labels=json.dumps(daily_labels),
        daily_revenue=json.dumps(daily_revenue),
        daily_counts=json.dumps(daily_counts),
        yearly_labels=json.dumps(list(yearly_labels)),
        yearly_revenue=json.dumps([yearly_data[y]["revenue"] for y in yearly_labels]),
        yearly_counts=json.dumps([yearly_data[y]["count"] for y in yearly_labels]),
    )


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
@admin_bp.route("/settings")
@login_required
@admin_required
def settings():
    system_info = {
        "total_invoices": Invoice.objects.count(),
        "total_receipts": Receipt.objects.count(),
        "total_users": User.objects.count(),
    }
    return render_template("settings.html", user=current_user, system_info=system_info)


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------
@admin_bp.route("/logs")
@login_required
@admin_required
def logs():
    return render_template("logs.html")
