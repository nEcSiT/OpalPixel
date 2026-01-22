import os
import csv
import io
import uuid
from datetime import datetime
from typing import Optional
from flask import Flask, render_template, redirect, url_for, request, flash, Response
from flask_login import login_required, current_user
from bson import ObjectId
import mongoengine

from .extensions import login_manager
from .models import User, Invoice, InvoiceItem, Receipt
from .auth import auth_bp

app = Flask(__name__)

# Production-ready configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# MongoDB Configuration - Connect using mongoengine
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/opalpixel')

# Connect to MongoDB with connection timeout settings
try:
    mongoengine.connect(host=MONGODB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    print(f"Connected to MongoDB")
except Exception as e:
    print(f"Warning: Could not connect to MongoDB: {e}")
    print("Make sure MONGODB_URI environment variable is set correctly")

app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager.init_app(app)
login_manager.login_view = 'auth.login'  # type: ignore[assignment]

app.register_blueprint(auth_bp)




def _format_invoice_number(sequence: int, target_date: Optional[datetime] = None) -> str:
    """Return invoice number like OPL-0001-26 (YY suffix)."""
    target_date = target_date or datetime.utcnow()
    year_suffix = target_date.strftime('%y')
    return f"OPL-{sequence:04d}-{year_suffix}"


def _generate_invoice_number(target_date: Optional[datetime] = None) -> str:
    """Generate the next invoice number for the target year."""
    target_date = target_date or datetime.utcnow()
    year_suffix = target_date.strftime('%y')
    pattern = f"OPL-.*-{year_suffix}"
    import re
    count = Invoice.objects(invoice_number=re.compile(pattern)).count()
    return _format_invoice_number(count + 1, target_date)


def _init_admin():
    """Create default admin if not exists."""
    try:
        if not User.objects(role='admin').first():
            admin = User(
                full_name='OpalPixel',
                worker_id='OPL-0508748992',
                position='System Admin',
                role='admin'
            )
            admin.set_password('admin123')
            admin.save()
            print("Default admin created: OPL-0508748992")
    except Exception as e:
        print(f"Could not initialize admin (MongoDB may not be connected): {e}")


# Initialize admin on startup
with app.app_context():
    _init_admin()



@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('worker_dashboard'))
    return redirect(url_for('auth.login'))


@app.route('/login-split')
def login_split():
    return render_template('login_split.html')


# ==================== WORKER ROUTES ====================

@app.route('/worker/dashboard')
@login_required
def worker_dashboard():
    """Worker's personal dashboard showing their own stats."""
    my_invoices = list(Invoice.objects(user_id=current_user.id).order_by('-date_created'))
    
    stats = {
        'total_invoices': len(my_invoices),
        'pending_invoices': sum(1 for inv in my_invoices if inv.status == 'Pending'),
        'paid_invoices': sum(1 for inv in my_invoices if inv.status == 'Paid'),
        'total_revenue': sum(inv.amount for inv in my_invoices if inv.status == 'Paid')
    }
    
    recent_invoices = my_invoices[:5]
    return render_template('worker_dashboard.html', user=current_user, stats=stats, recent_invoices=recent_invoices)


@app.route('/worker/invoices')
@login_required
def my_invoices():
    """Worker's own invoices list."""
    invoices = list(Invoice.objects(user_id=current_user.id).order_by('-date_created'))
    return render_template('my_invoices.html', user=current_user, invoices=invoices)


@app.route('/worker/receipts')
@login_required
def my_receipts():
    """Worker's own receipts (from their paid invoices)."""
    my_invoice_ids = [inv.id for inv in Invoice.objects(user_id=current_user.id)]
    receipts = list(Receipt.objects(invoice_id__in=my_invoice_ids).order_by('-payment_date'))
    return render_template('my_receipts.html', user=current_user, receipts=receipts)


# ==================== ADMIN ROUTES ====================

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    invoices = list(Invoice.objects.order_by('-date_created'))
    workers = list(User.objects(role='worker'))
    receipts = list(Receipt.objects.order_by('-payment_date'))
    
    total_revenue = sum(inv.amount for inv in invoices if inv.status == 'Paid')
    today = datetime.utcnow().date()
    invoices_today = sum(1 for inv in invoices if inv.date_created and inv.date_created.date() == today)
    pending_approvals = sum(1 for inv in invoices if inv.status == 'Pending')
    active_workers = len(workers)
    
    stats = {
        'revenue': total_revenue,
        'invoices_today': invoices_today,
        'pending': pending_approvals,
        'active_workers': active_workers
    }
    
    activities = []
    for inv in invoices[:8]:
        activities.append({
            'type': 'invoice',
            'title': f"Invoice {inv.invoice_number or str(inv.id)[:8]} ({inv.status})",
            'meta': inv.client_name,
            'timestamp': inv.date_created
        })
    for rec in receipts[:8]:
        inv = rec.invoice_id
        activities.append({
            'type': 'receipt',
            'title': f"Receipt {rec.receipt_number}",
            'meta': inv.client_name if inv else '—',
            'timestamp': rec.payment_date
        })
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    activities = activities[:8]

    return render_template('admin_dashboard.html', user=current_user, invoices=invoices, workers=workers, stats=stats, recent_activities=activities)


@app.route('/invoices')
@login_required
def invoices_list():
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    invoices = list(Invoice.objects.order_by('-date_created'))
    return render_template('invoices_list.html', user=current_user, invoices=invoices)


@app.route('/receipts')
@login_required
def receipts_list():
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    receipts = list(Receipt.objects.order_by('-payment_date'))
    return render_template('receipts_list.html', user=current_user, receipts=receipts)


# ==================== CSV EXPORT ROUTES (Admin Only) ====================

@app.route('/export/invoices')
@login_required
def export_invoices_csv():
    """Export all invoices to CSV file."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    invoices = list(Invoice.objects.order_by('-date_created'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Invoice Number', 'Client Name', 'Client Email', 'Client Phone', 'Client Address',
        'Amount (GH₵)', 'Tax Rate (%)', 'Tax Amount (GH₵)', 'Status',
        'Date Created', 'Due Date', 'Created By', 'Worker ID'
    ])
    
    for inv in invoices:
        creator = inv.user_id
        writer.writerow([
            inv.invoice_number or f'INV-{str(inv.id)[:8]}',
            inv.client_name,
            inv.client_email or '',
            inv.client_phone or '',
            inv.client_address or '',
            f'{inv.amount:.2f}',
            f'{inv.tax_rate:.2f}',
            f'{inv.tax_amount:.2f}',
            inv.status,
            inv.date_created.strftime('%Y-%m-%d %H:%M') if inv.date_created else '',
            inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '',
            creator.full_name if creator else '',
            creator.worker_id if creator else ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=invoices_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'}
    )


@app.route('/export/receipts')
@login_required
def export_receipts_csv():
    """Export all receipts to CSV file."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    receipts = list(Receipt.objects.order_by('-payment_date'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Receipt Number', 'Invoice Number', 'Client Name', 'Client Email', 'Client Phone', 'Client Address',
        'Amount Paid (GH₵)', 'Payment Date', 'Issued By', 'Worker ID'
    ])
    
    for rec in receipts:
        inv = rec.invoice_id
        creator = inv.user_id if inv else None
        writer.writerow([
            rec.receipt_number,
            inv.invoice_number if inv else '',
            inv.client_name if inv else '',
            inv.client_email or '' if inv else '',
            inv.client_phone or '' if inv else '',
            inv.client_address or '' if inv else '',
            f'{rec.amount_paid:.2f}',
            rec.payment_date.strftime('%Y-%m-%d %H:%M') if rec.payment_date else '',
            creator.full_name if creator else '',
            creator.worker_id if creator else ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=receipts_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'}
    )


@app.route('/export/clients')
@login_required
def export_clients_csv():
    """Export all unique clients to CSV file."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    invoices = list(Invoice.objects.order_by('client_name'))
    
    seen_clients = {}
    for inv in invoices:
        key = inv.client_name.lower().strip()
        if key not in seen_clients:
            seen_clients[key] = {
                'name': inv.client_name,
                'email': inv.client_email or '',
                'phone': inv.client_phone or '',
                'address': inv.client_address or '',
                'total_invoices': 0,
                'total_amount': 0.0,
                'paid_amount': 0.0
            }
        seen_clients[key]['total_invoices'] += 1
        seen_clients[key]['total_amount'] += inv.amount
        if inv.status == 'Paid':
            seen_clients[key]['paid_amount'] += inv.amount
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Client Name', 'Email', 'Phone', 'Address',
        'Total Invoices', 'Total Amount (GH₵)', 'Paid Amount (GH₵)'
    ])
    
    for client in seen_clients.values():
        writer.writerow([
            client['name'],
            client['email'],
            client['phone'],
            client['address'],
            client['total_invoices'],
            f'{client["total_amount"]:.2f}',
            f'{client["paid_amount"]:.2f}'
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=clients_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'}
    )


@app.route('/export/all')
@login_required
def export_all_csv():
    """Export complete data report (invoices with items) to CSV."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    invoices = list(Invoice.objects.order_by('-date_created'))
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Invoice Number', 'Client Name', 'Client Email', 'Client Phone', 'Client Address',
        'Item Description', 'Quantity', 'Unit Price (GH₵)', 'Line Total (GH₵)',
        'Invoice Total (GH₵)', 'Tax Rate (%)', 'Tax Amount (GH₵)', 'Status',
        'Date Created', 'Due Date', 'Receipt Number', 'Payment Date',
        'Created By', 'Worker ID'
    ])
    
    for inv in invoices:
        creator = inv.user_id
        receipt = Receipt.objects(invoice_id=inv.id).first()
        receipt_num = receipt.receipt_number if receipt else ''
        payment_date = receipt.payment_date.strftime('%Y-%m-%d %H:%M') if receipt and receipt.payment_date else ''
        
        if inv.items:
            for item in inv.items:
                writer.writerow([
                    inv.invoice_number or f'INV-{str(inv.id)[:8]}',
                    inv.client_name,
                    inv.client_email or '',
                    inv.client_phone or '',
                    inv.client_address or '',
                    item.description,
                    item.quantity,
                    f'{item.unit_price:.2f}',
                    f'{item.total:.2f}',
                    f'{inv.amount:.2f}',
                    f'{inv.tax_rate:.2f}',
                    f'{inv.tax_amount:.2f}',
                    inv.status,
                    inv.date_created.strftime('%Y-%m-%d %H:%M') if inv.date_created else '',
                    inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '',
                    receipt_num,
                    payment_date,
                    creator.full_name if creator else '',
                    creator.worker_id if creator else ''
                ])
        else:
            writer.writerow([
                inv.invoice_number or f'INV-{str(inv.id)[:8]}',
                inv.client_name,
                inv.client_email or '',
                inv.client_phone or '',
                inv.client_address or '',
                '', '', '', '',
                f'{inv.amount:.2f}',
                f'{inv.tax_rate:.2f}',
                f'{inv.tax_amount:.2f}',
                inv.status,
                inv.date_created.strftime('%Y-%m-%d %H:%M') if inv.date_created else '',
                inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '',
                receipt_num,
                payment_date,
                creator.full_name if creator else '',
                creator.worker_id if creator else ''
            ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=full_report_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'}
    )


@app.route('/team')
@login_required
def team_list():
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    workers = list(User.objects(role='worker'))
    return render_template('team_list.html', user=current_user, workers=workers)


@app.route('/create-invoice', methods=['GET', 'POST'])
@login_required
def create_invoice():
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        client_email = request.form.get('client_email')
        client_phone = request.form.get('client_phone')
        client_address = request.form.get('client_address')
        date_str = request.form.get('due_date')
        if date_str:
            due_date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            due_date = datetime.utcnow()
        
        descriptions = request.form.getlist('descriptions[]')
        quantities = request.form.getlist('quantities[]')
        prices = request.form.getlist('prices[]')
        tax_rate = float(request.form.get('tax_rate') or 0)

        subtotal = 0
        items = []
        
        for i in range(len(descriptions)):
            if descriptions[i]:
                qty = int(quantities[i]) if quantities[i] else 0
                price = float(prices[i]) if prices[i] else 0.0
                line_total = qty * price
                subtotal += line_total
                items.append(InvoiceItem(
                    description=descriptions[i],
                    quantity=qty,
                    unit_price=price,
                    total=line_total
                ))

        tax_amount = subtotal * (tax_rate / 100.0)
        total_amount = subtotal + tax_amount

        invoice_number = _generate_invoice_number(due_date)

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
            status='Pending',
            invoice_number=invoice_number,
            items=items
        )
        new_invoice.save()
        
        flash('Invoice created successfully!')
        if current_user.role == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('worker_dashboard'))

    next_invoice_number = _generate_invoice_number()
    return render_template('create_invoice.html', next_invoice_number=next_invoice_number, user=current_user)


@app.route('/pay-invoice/<invoice_id>', methods=['POST'])
@login_required
def pay_invoice(invoice_id):
    try:
        invoice = Invoice.objects(id=ObjectId(invoice_id)).first()
    except:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if not invoice:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if current_user.role != 'admin' and str(invoice.user_id.id) != str(current_user.id):
        flash('You can only manage your own invoices.')
        return redirect(url_for('worker_dashboard'))
    
    if invoice.status != 'Paid':
        invoice.status = 'Paid'
        invoice.save()
        
        receipt_number = f"REC-{uuid.uuid4().hex[:8].upper()}"
        
        receipt = Receipt(
            invoice_id=invoice,
            amount_paid=invoice.amount,
            receipt_number=receipt_number
        )
        receipt.save()
        flash('Invoice paid and receipt generated!')
    
    if current_user.role == 'admin':
        return redirect(url_for('dashboard'))
    return redirect(url_for('worker_dashboard'))


@app.route('/receipt/<invoice_id>')
@login_required
def view_receipt(invoice_id):
    try:
        invoice = Invoice.objects(id=ObjectId(invoice_id)).first()
    except:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if not invoice:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if current_user.role != 'admin' and str(invoice.user_id.id) != str(current_user.id):
        flash('You can only view receipts for your own invoices.')
        return redirect(url_for('worker_dashboard'))
    
    receipt = Receipt.objects(invoice_id=invoice.id).first()
    if not receipt:
        flash('Receipt not found or invoice not paid yet.')
        if current_user.role == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('worker_dashboard'))
    
    return render_template('official_receipt.html', invoice=invoice, receipt=receipt, user=current_user)


@app.route('/invoice/<invoice_id>')
@login_required
def view_invoice(invoice_id):
    try:
        invoice = Invoice.objects(id=ObjectId(invoice_id)).first()
    except:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if not invoice:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if current_user.role != 'admin' and str(invoice.user_id.id) != str(current_user.id):
        flash('You can only view your own invoices.')
        return redirect(url_for('worker_dashboard'))
    
    return render_template('invoice_detail.html', invoice=invoice, user=current_user)


@app.route('/invoice/<invoice_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_invoice(invoice_id):
    try:
        invoice = Invoice.objects(id=ObjectId(invoice_id)).first()
    except:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if not invoice:
        flash('Invoice not found.')
        return redirect(url_for('dashboard'))
    
    if current_user.role != 'admin' and str(invoice.user_id.id) != str(current_user.id):
        flash('You can only edit your own invoices.')
        return redirect(url_for('worker_dashboard'))
    
    if invoice.status == 'Paid':
        flash('Cannot edit a paid invoice.')
        return redirect(url_for('view_invoice', invoice_id=invoice_id))
    
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        client_email = request.form.get('client_email')
        client_phone = request.form.get('client_phone')
        client_address = request.form.get('client_address')
        date_str = request.form.get('due_date')
        if date_str:
            due_date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            due_date = invoice.due_date
        
        descriptions = request.form.getlist('descriptions[]')
        quantities = request.form.getlist('quantities[]')
        prices = request.form.getlist('prices[]')
        tax_rate = float(request.form.get('tax_rate') or 0)

        subtotal = 0
        items = []
        
        for i in range(len(descriptions)):
            if descriptions[i]:
                qty = int(quantities[i]) if quantities[i] else 0
                price = float(prices[i]) if prices[i] else 0.0
                line_total = qty * price
                subtotal += line_total
                items.append(InvoiceItem(
                    description=descriptions[i],
                    quantity=qty,
                    unit_price=price,
                    total=line_total
                ))

        tax_amount = subtotal * (tax_rate / 100.0)
        total_amount = subtotal + tax_amount

        invoice.client_name = client_name
        invoice.client_email = client_email
        invoice.client_phone = client_phone
        invoice.client_address = client_address
        invoice.amount = total_amount
        invoice.tax_rate = tax_rate
        invoice.tax_amount = tax_amount
        invoice.due_date = due_date
        invoice.items = items
        invoice.save()
        
        flash('Invoice updated successfully!')
        return redirect(url_for('view_invoice', invoice_id=invoice_id))

    return render_template('edit_invoice.html', invoice=invoice, user=current_user)


@app.route('/receipt-workflow')
def receipt_workflow():
    return render_template('receipt_workflow.html')


@app.route('/official-receipt')
def official_receipt():
    return render_template('official_receipt.html')


# ==================== ADMIN PORTAL ROUTES ====================

@app.route('/document-logs')
@login_required
def document_logs():
    """Document Logs page - combined view of invoices and receipts with filtering."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    doc_type = request.args.get('type', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    worker_id = request.args.get('worker', '')
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = 15
    
    # Build queries
    invoice_filter = {}
    receipt_filter = {}
    
    if worker_id:
        try:
            invoice_filter['user_id'] = ObjectId(worker_id)
            worker_invoices = Invoice.objects(user_id=ObjectId(worker_id))
            receipt_filter['invoice_id__in'] = [inv.id for inv in worker_invoices]
        except:
            pass
    
    if status:
        invoice_filter['status'] = status
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            invoice_filter['date_created__gte'] = from_date
            receipt_filter['payment_date__gte'] = from_date
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            invoice_filter['date_created__lte'] = to_date
            receipt_filter['payment_date__lte'] = to_date
        except ValueError:
            pass
    
    invoices = list(Invoice.objects(**invoice_filter).order_by('-date_created')) if doc_type in ['all', 'invoice'] else []
    receipts = list(Receipt.objects(**receipt_filter).order_by('-payment_date')) if doc_type in ['all', 'receipt'] else []
    
    documents = []
    for inv in invoices:
        creator = inv.user_id
        documents.append({
            'type': 'invoice',
            'id': str(inv.id),
            'doc_number': inv.invoice_number or f'INV-{str(inv.id)[:8]}',
            'client_name': inv.client_name,
            'amount': inv.amount,
            'date': inv.date_created,
            'status': inv.status,
            'creator': creator
        })
    
    for rec in receipts:
        inv = rec.invoice_id
        creator = inv.user_id if inv else None
        documents.append({
            'type': 'receipt',
            'id': str(rec.id),
            'doc_number': rec.receipt_number,
            'client_name': inv.client_name if inv else '—',
            'amount': rec.amount_paid,
            'date': rec.payment_date,
            'status': 'Completed',
            'creator': creator,
            'invoice_id': str(inv.id) if inv else None
        })
    
    documents.sort(key=lambda x: x['date'] or datetime.min, reverse=True)
    
    total_count = len(documents)
    total_pages = (total_count + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    documents = documents[start:end]
    
    workers = list(User.objects())
    all_invoices = list(Invoice.objects())
    all_receipts = list(Receipt.objects())
    
    return render_template('document_logs.html',
        user=current_user,
        documents=documents,
        invoices=all_invoices,
        receipts=all_receipts,
        workers=workers,
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        current_type=doc_type,
        current_date_from=date_from,
        current_date_to=date_to,
        current_worker=worker_id,
        current_status=status
    )


@app.route('/user-management')
@login_required
def user_management():
    """User Management page - view and manage all users."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    all_users = list(User.objects())
    users_data = []
    
    for u in all_users:
        user_invoices = list(Invoice.objects(user_id=u.id))
        invoice_count = len(user_invoices)
        revenue = sum(inv.amount for inv in user_invoices if inv.status == 'Paid')
        
        users_data.append({
            'user': u,
            'invoice_count': invoice_count,
            'revenue': revenue
        })
    
    stats = {
        'total_users': len(all_users),
        'admins': sum(1 for u in all_users if u.role == 'admin'),
        'workers': sum(1 for u in all_users if u.role == 'worker'),
        'total_invoices': Invoice.objects.count()
    }
    
    return render_template('user_management.html',
        user=current_user,
        users=users_data,
        stats=stats
    )


@app.route('/edit-user/<user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit user details."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    try:
        user_to_edit = User.objects(id=ObjectId(user_id)).first()
    except:
        flash('User not found.')
        return redirect(url_for('user_management'))
    
    if not user_to_edit:
        flash('User not found.')
        return redirect(url_for('user_management'))
    
    if request.method == 'POST':
        user_to_edit.full_name = request.form.get('full_name', user_to_edit.full_name).strip()
        user_to_edit.position = request.form.get('position', '').strip() or None
        user_to_edit.location = request.form.get('location', '').strip() or None
        user_to_edit.nationality = request.form.get('nationality', '').strip() or None
        user_to_edit.role = request.form.get('role', user_to_edit.role)
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                from werkzeug.utils import secure_filename
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext in app.config['ALLOWED_IMAGE_EXTENSIONS']:
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    user_to_edit.image_path = f"uploads/{filename}"
        
        user_to_edit.save()
        flash('User updated successfully')
        return redirect(url_for('user_management'))
    
    return render_template('edit_user.html', user=current_user, edit_user=user_to_edit)


@app.route('/reports')
@login_required
def reports():
    """Reports page - financial analytics with charts."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    from collections import defaultdict
    import json
    
    selected_year = request.args.get('year', str(datetime.utcnow().year))
    selected_month = request.args.get('month', '')
    
    all_invoices = list(Invoice.objects.order_by('-date_created'))
    all_receipts = list(Receipt.objects())
    
    available_years = sorted(set(inv.date_created.year for inv in all_invoices if inv.date_created), reverse=True)
    if not available_years:
        available_years = [datetime.utcnow().year]
    
    year_invoices = [inv for inv in all_invoices if inv.date_created and inv.date_created.year == int(selected_year)]
    
    if selected_month:
        month_invoices = [inv for inv in year_invoices if inv.date_created.month == int(selected_month)]
    else:
        month_invoices = year_invoices
    
    paid_invoices = [inv for inv in month_invoices if inv.status == 'Paid']
    pending_invoices = [inv for inv in month_invoices if inv.status == 'Pending']
    
    total_revenue = sum(inv.amount for inv in paid_invoices)
    total_pending = sum(inv.amount for inv in pending_invoices)
    total_invoices = len(month_invoices)
    average_invoice = total_revenue / len(paid_invoices) if paid_invoices else 0
    unique_clients = len(set(inv.client_name for inv in month_invoices))
    
    monthly_data = defaultdict(lambda: {'revenue': 0, 'count': 0, 'paid': 0, 'pending': 0})
    
    for inv in year_invoices:
        if inv.date_created:
            month_key = inv.date_created.strftime('%b')
            monthly_data[month_key]['count'] += 1
            if inv.status == 'Paid':
                monthly_data[month_key]['revenue'] += inv.amount
                monthly_data[month_key]['paid'] += 1
            else:
                monthly_data[month_key]['pending'] += 1
    
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_labels = month_names
    monthly_revenue = [monthly_data[m]['revenue'] for m in month_names]
    monthly_counts = [monthly_data[m]['count'] for m in month_names]
    monthly_paid = [monthly_data[m]['paid'] for m in month_names]
    monthly_pending = [monthly_data[m]['pending'] for m in month_names]
    
    daily_labels = []
    daily_revenue = []
    daily_counts = []
    
    if selected_month:
        import calendar
        days_in_month = calendar.monthrange(int(selected_year), int(selected_month))[1]
        daily_data = defaultdict(lambda: {'revenue': 0, 'count': 0})
        
        for inv in month_invoices:
            if inv.date_created:
                day_key = inv.date_created.day
                daily_data[day_key]['count'] += 1
                if inv.status == 'Paid':
                    daily_data[day_key]['revenue'] += inv.amount
        
        daily_labels = list(range(1, days_in_month + 1))
        daily_revenue = [daily_data[d]['revenue'] for d in daily_labels]
        daily_counts = [daily_data[d]['count'] for d in daily_labels]
    
    yearly_data = defaultdict(lambda: {'revenue': 0, 'count': 0})
    for inv in all_invoices:
        if inv.date_created:
            year_key = inv.date_created.year
            yearly_data[year_key]['count'] += 1
            if inv.status == 'Paid':
                yearly_data[year_key]['revenue'] += inv.amount
    
    yearly_labels = sorted(yearly_data.keys())
    yearly_revenue = [yearly_data[y]['revenue'] for y in yearly_labels]
    yearly_counts = [yearly_data[y]['count'] for y in yearly_labels]
    
    current_year_revenue = yearly_data.get(int(selected_year), {}).get('revenue', 0)
    prev_year_revenue = yearly_data.get(int(selected_year) - 1, {}).get('revenue', 0)
    if prev_year_revenue > 0:
        revenue_growth = round(((current_year_revenue - prev_year_revenue) / prev_year_revenue) * 100, 1)
    else:
        revenue_growth = 0
    
    status_counts = {
        'Paid': len(paid_invoices),
        'Pending': len(pending_invoices),
        'Overdue': sum(1 for inv in month_invoices if inv.status == 'Overdue')
    }
    
    workers = list(User.objects())
    worker_stats = []
    for w in workers:
        w_invoices = [inv for inv in month_invoices if inv.user_id and str(inv.user_id.id) == str(w.id)]
        w_revenue = sum(inv.amount for inv in w_invoices if inv.status == 'Paid')
        w_count = len(w_invoices)
        if w_count > 0:
            worker_stats.append({
                'user': w,
                'full_name': w.full_name,
                'image_path': w.image_path,
                'revenue': w_revenue,
                'invoice_count': w_count
            })
    
    worker_stats.sort(key=lambda x: x['revenue'], reverse=True)
    top_workers = worker_stats[:5]
    
    recent_invoices = month_invoices[:10]
    
    current_month = datetime.utcnow().month
    current_year_num = datetime.utcnow().year
    invoices_this_month = sum(1 for inv in all_invoices if inv.date_created and inv.date_created.month == current_month and inv.date_created.year == current_year_num)
    
    report = {
        'total_revenue': total_revenue,
        'total_pending': total_pending,
        'pending_amount': total_pending,
        'total_invoices': total_invoices,
        'total_receipts': len(all_receipts),
        'average_invoice': average_invoice,
        'avg_invoice': average_invoice,
        'status_counts': status_counts,
        'paid_invoices': len(paid_invoices),
        'pending_invoices': len(pending_invoices),
        'unique_clients': unique_clients,
        'invoices_this_month': invoices_this_month,
        'revenue_growth': revenue_growth
    }
    
    return render_template('reports.html',
        user=current_user,
        report=report,
        top_workers=top_workers,
        recent_invoices=recent_invoices,
        selected_year=selected_year,
        selected_month=selected_month,
        available_years=available_years,
        monthly_labels=json.dumps(monthly_labels),
        monthly_revenue=json.dumps(monthly_revenue),
        monthly_counts=json.dumps(monthly_counts),
        monthly_paid=json.dumps(monthly_paid),
        monthly_pending=json.dumps(monthly_pending),
        daily_labels=json.dumps(daily_labels),
        daily_revenue=json.dumps(daily_revenue),
        daily_counts=json.dumps(daily_counts),
        yearly_labels=json.dumps(yearly_labels),
        yearly_revenue=json.dumps(yearly_revenue),
        yearly_counts=json.dumps(yearly_counts)
    )


@app.route('/settings')
@login_required
def settings():
    """Settings page - user account and system preferences."""
    if current_user.role != 'admin':
        return redirect(url_for('worker_dashboard'))
    
    system_info = {
        'total_invoices': Invoice.objects.count(),
        'total_receipts': Receipt.objects.count(),
        'total_users': User.objects.count()
    }
    
    return render_template('settings.html', user=current_user, system_info=system_info)


@app.route('/logs')
def logs():
    return render_template('logs.html')


if __name__ == '__main__':
    app.run(debug=True)
