"""
Invoice business logic — number generation, calculations.
"""

from datetime import datetime
from typing import Optional

from app.models import Invoice


def format_invoice_number(sequence: int, target_date: Optional[datetime] = None) -> str:
    """Return an invoice number like ``OPL-0001-26`` (YY suffix)."""
    target_date = target_date or datetime.utcnow()
    year_suffix = target_date.strftime("%y")
    return f"OPL-{sequence:04d}-{year_suffix}"


def generate_invoice_number(target_date: Optional[datetime] = None) -> str:
    """Generate the next sequential invoice number for *target_date*'s year."""
    target_date = target_date or datetime.utcnow()
    year_suffix = target_date.strftime("%y")
    count = Invoice.objects(invoice_number__regex=f"^OPL-.*-{year_suffix}$").count()
    return format_invoice_number(count + 1, target_date)
