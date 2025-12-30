"""
PDF Generation Utilities
Functions for generating PDF receipts and reports
"""

import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfgen import canvas


def generate_receipt_pdf(sale):
    """
    Generate PDF receipt for a sale

    Args:
        sale: Sale object

    Returns:
        str: Path to generated PDF file
    """
    from flask import current_app

    # Create receipts folder if it doesn't exist
    receipts_folder = os.path.join(current_app.static_folder, 'receipts')
    os.makedirs(receipts_folder, exist_ok=True)

    # Generate filename
    filename = f"receipt_{sale.sale_number}.pdf"
    filepath = os.path.join(receipts_folder, filename)

    # Create PDF
    pdf = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter

    # Business header
    business_name = current_app.config.get('BUSINESS_NAME', 'Sunnat Collection')
    business_address = current_app.config.get('BUSINESS_ADDRESS', '')
    business_phone = current_app.config.get('BUSINESS_PHONE', '')

    y = height - 50

    # Title
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(width / 2, y, business_name)

    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(width / 2, y, business_address)

    y -= 15
    pdf.drawCentredString(width / 2, y, f"Phone: {business_phone}")

    y -= 30
    pdf.line(50, y, width - 50, y)

    # Receipt details
    y -= 30
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "SALES RECEIPT")

    y -= 25
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Receipt #: {sale.sale_number}")
    pdf.drawString(width - 200, y, f"Date: {sale.sale_date.strftime('%Y-%m-%d %H:%M')}")

    if sale.customer:
        y -= 20
        pdf.drawString(50, y, f"Customer: {sale.customer.name}")
        pdf.drawString(width - 200, y, f"Phone: {sale.customer.phone}")

    # Items table
    y -= 40
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Item")
    pdf.drawString(250, y, "Qty")
    pdf.drawString(320, y, "Price")
    pdf.drawString(width - 150, y, "Total")

    y -= 5
    pdf.line(50, y, width - 50, y)

    # Items
    y -= 20
    pdf.setFont("Helvetica", 9)

    currency_symbol = current_app.config.get('CURRENCY_SYMBOL', 'Rs.')

    for item in sale.items:
        product_name = item.product.name if item.product else "Unknown"
        if len(product_name) > 30:
            product_name = product_name[:27] + "..."

        pdf.drawString(50, y, product_name)
        pdf.drawString(250, y, str(item.quantity))
        pdf.drawString(320, y, f"{currency_symbol} {float(item.unit_price):,.2f}")
        pdf.drawString(width - 150, y, f"{currency_symbol} {float(item.subtotal):,.2f}")

        y -= 18

        if y < 150:  # Start new page if needed
            pdf.showPage()
            y = height - 50

    # Totals
    y -= 10
    pdf.line(50, y, width - 50, y)

    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(width - 250, y, f"Subtotal:")
    pdf.drawString(width - 150, y, f"{currency_symbol} {float(sale.subtotal):,.2f}")

    if sale.discount > 0:
        y -= 18
        discount_text = f"Discount ({sale.discount_type}):"
        pdf.drawString(width - 250, y, discount_text)
        pdf.drawString(width - 150, y, f"-{currency_symbol} {float(sale.discount):,.2f}")

    if sale.tax > 0:
        y -= 18
        pdf.drawString(width - 250, y, f"Tax:")
        pdf.drawString(width - 150, y, f"{currency_symbol} {float(sale.tax):,.2f}")

    y -= 5
    pdf.line(width - 250, y, width - 50, y)

    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(width - 250, y, f"TOTAL:")
    pdf.drawString(width - 150, y, f"{currency_symbol} {float(sale.total):,.2f}")

    # Payment info
    y -= 30
    pdf.setFont("Helvetica", 9)
    pdf.drawString(50, y, f"Payment Method: {sale.payment_method.replace('_', ' ').title()}")

    # Footer
    y = 70
    pdf.setFont("Helvetica-Italic", 8)
    pdf.drawCentredString(width / 2, y, "Thank you for your business!")

    y -= 15
    pdf.drawCentredString(width / 2, y, "Visit us again!")

    # Save PDF
    pdf.save()

    return f'/static/receipts/{filename}'


def generate_daily_report(date_str):
    """
    Generate daily sales report PDF

    Args:
        date_str: Date string in format YYYY-MM-DD

    Returns:
        str: Path to generated PDF
    """
    from flask import current_app
    from app.models import Sale, Product, SaleItem
    from sqlalchemy import func, and_

    # Create reports folder
    reports_folder = os.path.join(current_app.static_folder, 'reports')
    os.makedirs(reports_folder, exist_ok=True)

    filename = f"daily_report_{date_str}.pdf"
    filepath = os.path.join(reports_folder, filename)

    # This is a simplified version - you can expand with more detailed reporting
    pdf = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    # Header
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, height - 50, "Daily Sales Report")

    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, height - 70, f"Date: {date_str}")

    # Add more report content here...

    pdf.save()

    return filepath


def generate_sales_report(from_date, to_date):
    """
    Generate sales report for date range

    Args:
        from_date: Start date
        to_date: End date

    Returns:
        str: Path to generated PDF
    """
    # Implementation similar to daily report
    pass
