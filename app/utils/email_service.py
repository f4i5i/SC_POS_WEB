"""
Email Service for sending reports and notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import current_app
import os


def send_daily_report_email(day_close, report_path, recipient_email):
    """Send daily sales report via email"""

    # Email configuration from app config or environment variables
    smtp_server = current_app.config.get('SMTP_SERVER', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))
    smtp_port = current_app.config.get('SMTP_PORT', int(os.getenv('SMTP_PORT', 587)))
    smtp_username = current_app.config.get('SMTP_USERNAME', os.getenv('SMTP_USERNAME'))
    smtp_password = current_app.config.get('SMTP_PASSWORD', os.getenv('SMTP_PASSWORD'))
    sender_email = current_app.config.get('SENDER_EMAIL', os.getenv('SENDER_EMAIL', smtp_username))

    if not all([smtp_username, smtp_password]):
        raise ValueError("Email credentials not configured. Please set SMTP_USERNAME and SMTP_PASSWORD in environment variables or config.")

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"Daily Sales Report - {day_close.close_date.strftime('%B %d, %Y')} - Sunnat Collection"

    # Email body
    body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background: linear-gradient(135deg, #3B82F6, #8B5CF6); color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .summary-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .summary-table th {{ background: #3B82F6; color: white; padding: 12px; text-align: left; }}
            .summary-table td {{ padding: 10px; border-bottom: 1px solid #E5E7EB; }}
            .metric {{ font-weight: bold; color: #1F2937; }}
            .value {{ color: #059669; font-size: 1.2em; font-weight: bold; }}
            .footer {{ background: #F3F4F6; padding: 15px; text-align: center; font-size: 0.9em; color: #6B7280; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Daily Sales Report</h1>
            <p>{day_close.close_date.strftime('%B %d, %Y')}</p>
        </div>

        <div class="content">
            <h2>Sales Summary</h2>
            <table class="summary-table">
                <tr>
                    <td class="metric">Total Transactions:</td>
                    <td class="value">{day_close.total_sales}</td>
                </tr>
                <tr>
                    <td class="metric">Total Revenue:</td>
                    <td class="value">Rs. {day_close.total_revenue:,.2f}</td>
                </tr>
                <tr>
                    <td class="metric">Cash Sales:</td>
                    <td>Rs. {day_close.total_cash:,.2f}</td>
                </tr>
                <tr>
                    <td class="metric">Card Sales:</td>
                    <td>Rs. {day_close.total_card:,.2f}</td>
                </tr>
            </table>

            <h2>Cash Drawer</h2>
            <table class="summary-table">
                <tr>
                    <td class="metric">Opening Balance:</td>
                    <td>Rs. {day_close.opening_balance:,.2f}</td>
                </tr>
                <tr>
                    <td class="metric">Expected Cash:</td>
                    <td>Rs. {day_close.expected_cash:,.2f}</td>
                </tr>
                <tr>
                    <td class="metric">Actual Closing:</td>
                    <td>Rs. {day_close.closing_balance:,.2f}</td>
                </tr>
                <tr>
                    <td class="metric">Variance:</td>
                    <td style="color: {'#EF4444' if day_close.cash_variance != 0 else '#059669'};">
                        Rs. {day_close.cash_variance:,.2f}
                    </td>
                </tr>
            </table>

            <p>Please find the detailed daily sales report attached to this email.</p>

            <p><strong>Closed By:</strong> {day_close.user.full_name}<br>
            <strong>Closed At:</strong> {day_close.closed_at.strftime('%I:%M %p')}</p>
        </div>

        <div class="footer">
            <p>This is an automated email from Sunnat Collection POS System</p>
            <p>First Floor, Mall of Wah, G.T Road</p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    # Attach PDF report
    if report_path and os.path.exists(report_path):
        with open(report_path, 'rb') as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
            pdf_attachment.add_header('Content-Disposition', 'attachment',
                                    filename=os.path.basename(report_path))
            msg.attach(pdf_attachment)

    # Send email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    return True


def send_low_stock_alert(products, recipient_email):
    """Send low stock alert email"""

    smtp_server = current_app.config.get('SMTP_SERVER', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))
    smtp_port = current_app.config.get('SMTP_PORT', int(os.getenv('SMTP_PORT', 587)))
    smtp_username = current_app.config.get('SMTP_USERNAME', os.getenv('SMTP_USERNAME'))
    smtp_password = current_app.config.get('SMTP_PASSWORD', os.getenv('SMTP_PASSWORD'))
    sender_email = current_app.config.get('SENDER_EMAIL', os.getenv('SENDER_EMAIL', smtp_username))

    if not all([smtp_username, smtp_password]):
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"Low Stock Alert - Sunnat Collection"

    products_html = ""
    for product in products:
        products_html += f"""
        <tr>
            <td>{product.name}</td>
            <td>{product.code}</td>
            <td style="color: #EF4444; font-weight: bold;">{product.quantity}</td>
            <td>{product.reorder_level}</td>
            <td>{product.suggested_reorder_quantity}</td>
        </tr>
        """

    body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background: #EF4444; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background: #3B82F6; color: white; padding: 12px; text-align: left; }}
            td {{ padding: 10px; border-bottom: 1px solid #E5E7EB; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>⚠️ Low Stock Alert</h1>
        </div>

        <div class="content">
            <p>The following products are running low on stock and need to be reordered:</p>

            <table>
                <thead>
                    <tr>
                        <th>Product Name</th>
                        <th>Code</th>
                        <th>Current Stock</th>
                        <th>Reorder Level</th>
                        <th>Suggested Order Qty</th>
                    </tr>
                </thead>
                <tbody>
                    {products_html}
                </tbody>
            </table>

            <p>Please take necessary action to replenish stock.</p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

    return True
