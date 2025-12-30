"""
Daily Report Generation Utilities
"""

from datetime import datetime, date
from decimal import Decimal
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def generate_daily_report(day_close, sales_list):
    """Generate PDF daily sales report"""
    from flask import current_app

    # Create reports directory if it doesn't exist
    reports_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads'), 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    # Generate filename
    filename = f"daily_report_{day_close.close_date.strftime('%Y%m%d')}.pdf"
    filepath = os.path.join(reports_dir, filename)

    # Create PDF
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    # Add custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#3B82F6'),
        spaceAfter=30,
        alignment=TA_CENTER
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1F2937'),
        spaceAfter=12,
        spaceBefore=20
    )

    # Title
    title = Paragraph("Daily Sales Report", title_style)
    story.append(title)

    # Date and business info
    info_data = [
        ['Business Name:', current_app.config.get('BUSINESS_NAME', 'Sunnat Collection')],
        ['Report Date:', day_close.close_date.strftime('%B %d, %Y')],
        ['Closed By:', day_close.user.full_name],
        ['Closed At:', day_close.closed_at.strftime('%I:%M %p')]
    ]

    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6B7280')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*inch))

    # Sales Summary
    story.append(Paragraph("Sales Summary", heading_style))

    summary_data = [
        ['Metric', 'Amount'],
        ['Total Transactions', str(day_close.total_sales)],
        ['Total Revenue', f"Rs. {day_close.total_revenue:,.2f}"],
        ['Cash Sales', f"Rs. {day_close.total_cash:,.2f}"],
        ['Card Sales', f"Rs. {day_close.total_card:,.2f}"],
        ['Other Payment', f"Rs. {day_close.total_other:,.2f}"],
    ]

    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')])
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))

    # Cash Drawer Summary
    story.append(Paragraph("Cash Drawer", heading_style))

    cash_data = [
        ['Description', 'Amount'],
        ['Opening Balance', f"Rs. {day_close.opening_balance:,.2f}"],
        ['Cash Sales', f"Rs. {day_close.total_cash:,.2f}"],
        ['Expected Cash', f"Rs. {day_close.expected_cash:,.2f}"],
        ['Actual Closing', f"Rs. {day_close.closing_balance:,.2f}"],
        ['Variance', f"Rs. {day_close.cash_variance:,.2f}"],
    ]

    cash_table = Table(cash_data, colWidths=[3*inch, 3*inch])
    cash_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10B981')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
        # Highlight variance row
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEF3C7') if day_close.cash_variance != 0 else colors.HexColor('#D1FAE5')),
    ]))
    story.append(cash_table)

    # Top selling products
    if sales_list:
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Top Selling Products", heading_style))

        # Aggregate product sales
        from collections import defaultdict
        product_sales = defaultdict(lambda: {'quantity': 0, 'revenue': Decimal('0.00')})

        for sale in sales_list:
            for item in sale.items:
                product_sales[item.product.name]['quantity'] += item.quantity
                product_sales[item.product.name]['revenue'] += item.subtotal

        # Sort by revenue
        top_products = sorted(product_sales.items(), key=lambda x: x[1]['revenue'], reverse=True)[:10]

        products_data = [['Product', 'Qty Sold', 'Revenue']]
        for product_name, data in top_products:
            products_data.append([
                product_name,
                str(data['quantity']),
                f"Rs. {data['revenue']:,.2f}"
            ])

        products_table = Table(products_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        products_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B5CF6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')])
        ]))
        story.append(products_table)

    # Notes
    if day_close.notes:
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Notes", heading_style))
        story.append(Paragraph(day_close.notes, styles['Normal']))

    # Footer
    story.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    footer = Paragraph(
        f"Generated by Sunnat Collection POS System on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        footer_style
    )
    story.append(footer)

    # Build PDF
    doc.build(story)

    return filepath
