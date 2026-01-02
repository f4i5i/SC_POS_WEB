"""
Email Service
Handles sending automated email reports and notifications
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, and_
from app.models import Sale, Product, SaleItem, Customer

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails and scheduled reports"""

    def __init__(self, app):
        self.app = app
        self.scheduler = None

    def send_email(self, to_addresses, subject, html_content, attachments=None):
        """
        Send email with HTML content and optional attachments

        Args:
            to_addresses: List of recipient email addresses
            subject: Email subject
            html_content: HTML email body
            attachments: List of file paths to attach
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.app.config['MAIL_DEFAULT_SENDER']
            msg['To'] = ', '.join(to_addresses)
            msg['Subject'] = subject

            # Add HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Add attachments
            if attachments:
                for filepath in attachments:
                    try:
                        with open(filepath, 'rb') as f:
                            attachment = MIMEApplication(f.read())
                            attachment.add_header('Content-Disposition', 'attachment',
                                                filename=filepath.split('/')[-1])
                            msg.attach(attachment)
                    except Exception as e:
                        logger.error(f"Error attaching file {filepath}: {e}")

            # Send email
            with smtplib.SMTP(self.app.config['MAIL_SERVER'],
                            self.app.config['MAIL_PORT']) as server:
                if self.app.config['MAIL_USE_TLS']:
                    server.starttls()

                server.login(self.app.config['MAIL_USERNAME'],
                           self.app.config['MAIL_PASSWORD'])
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_addresses}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def generate_daily_report_html(self, report_date=None):
        """
        Generate HTML content for daily sales report

        Args:
            report_date: Date for report (default: today)

        Returns:
            HTML string
        """
        if report_date is None:
            report_date = datetime.now().date()
        elif isinstance(report_date, str):
            report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

        with self.app.app_context():
            from app.models import db

            # Get sales for the day
            sales = Sale.query.filter(
                and_(
                    func.date(Sale.sale_date) == report_date,
                    Sale.status == 'completed'
                )
            ).all()

            # Calculate summary
            total_sales = sum(float(sale.total) for sale in sales)
            total_transactions = len(sales)
            avg_transaction = total_sales / total_transactions if total_transactions > 0 else 0

            # Payment method breakdown
            payment_methods = {}
            for sale in sales:
                method = sale.payment_method
                if method not in payment_methods:
                    payment_methods[method] = 0
                payment_methods[method] += float(sale.total)

            # Top products
            top_products = db.session.query(
                Product.name,
                Product.brand,
                func.sum(SaleItem.quantity).label('total_quantity'),
                func.sum(SaleItem.subtotal).label('total_sales')
            ).join(SaleItem).join(Sale).filter(
                func.date(Sale.sale_date) == report_date
            ).group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).limit(5).all()

            # Low stock alerts
            low_stock = Product.query.filter(
                Product.quantity <= Product.reorder_level
            ).all()

            out_of_stock = Product.query.filter(Product.quantity == 0).all()

        # Build HTML email
        currency_symbol = self.app.config.get('CURRENCY_SYMBOL', 'Rs.')
        business_name = self.app.config.get('BUSINESS_NAME', 'Sunnat Collection')

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #3B82F6; color: white; padding: 20px; text-align: center; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #3B82F6; }}
                .metric-label {{ font-size: 14px; color: #666; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f3f4f6; font-weight: bold; }}
                .alert {{ background-color: #FEF3C7; padding: 10px; margin: 10px 0; border-left: 4px solid #F59E0B; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{business_name}</h1>
                    <h2>Daily Sales Report - {report_date}</h2>
                </div>

                <div class="section">
                    <h3>📊 Sales Summary</h3>
                    <div class="metric">
                        <div class="metric-value">{currency_symbol} {total_sales:,.2f}</div>
                        <div class="metric-label">Total Sales</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{total_transactions}</div>
                        <div class="metric-label">Transactions</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{currency_symbol} {avg_transaction:,.2f}</div>
                        <div class="metric-label">Average Sale</div>
                    </div>
                </div>

                <div class="section">
                    <h3>💰 Payment Breakdown</h3>
                    <table>
                        <tr>
                            <th>Payment Method</th>
                            <th>Amount</th>
                            <th>Percentage</th>
                        </tr>
        """

        for method, amount in payment_methods.items():
            percentage = (amount / total_sales * 100) if total_sales > 0 else 0
            html += f"""
                        <tr>
                            <td>{method.replace('_', ' ').title()}</td>
                            <td>{currency_symbol} {amount:,.2f}</td>
                            <td>{percentage:.1f}%</td>
                        </tr>
            """

        html += """
                    </table>
                </div>

                <div class="section">
                    <h3>🏆 Top Products</h3>
                    <table>
                        <tr>
                            <th>Product</th>
                            <th>Brand</th>
                            <th>Quantity</th>
                            <th>Sales</th>
                        </tr>
        """

        for product in top_products:
            html += f"""
                        <tr>
                            <td>{product.name}</td>
                            <td>{product.brand or '-'}</td>
                            <td>{product.total_quantity}</td>
                            <td>{currency_symbol} {float(product.total_sales):,.2f}</td>
                        </tr>
            """

        html += """
                    </table>
                </div>
        """

        if low_stock or out_of_stock:
            html += """
                <div class="section">
                    <h3>⚠️ Stock Alerts</h3>
            """

            if out_of_stock:
                html += f"""
                    <div class="alert">
                        <strong>Out of Stock ({len(out_of_stock)} items):</strong><br>
                """
                for product in out_of_stock[:10]:
                    html += f"{product.name}, "
                html += """
                    </div>
                """

            if low_stock:
                html += f"""
                    <div class="alert">
                        <strong>Low Stock ({len(low_stock)} items):</strong><br>
                """
                for product in low_stock[:10]:
                    html += f"{product.name} ({product.quantity} units), "
                html += """
                    </div>
                """

            html += """
                </div>
            """

        html += f"""
                <div class="footer">
                    <p>🤖 Generated with POS System - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>{business_name}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def send_daily_report(self, report_date=None):
        """Send daily sales report via email"""
        try:
            recipients = self.app.config.get('DAILY_REPORT_RECIPIENTS', [])
            if not recipients or recipients == ['faisalnazir22@gmail.com']:
                logger.warning("No recipients configured for daily report")
                return False

            html_content = self.generate_daily_report_html(report_date)

            subject = f"Daily Sales Report - {report_date or datetime.now().date()}"

            success = self.send_email(recipients, subject, html_content)

            if success:
                logger.info(f"Daily report sent successfully to {recipients}")
            else:
                logger.error("Failed to send daily report")

            return success

        except Exception as e:
            logger.error(f"Error sending daily report: {e}")
            return False

    def start_scheduler(self):
        """Start background scheduler for daily reports"""
        if self.scheduler:
            logger.warning("Scheduler already running")
            return

        self.scheduler = BackgroundScheduler()

        # Parse time from config (e.g., "18:00")
        report_time = self.app.config.get('DAILY_REPORT_TIME', '18:00')
        hour, minute = map(int, report_time.split(':'))

        # Schedule daily report
        self.scheduler.add_job(
            func=self.send_daily_report,
            trigger='cron',
            hour=hour,
            minute=minute,
            id='daily_report'
        )

        self.scheduler.start()
        logger.info(f"Email scheduler started. Daily reports will be sent at {report_time}")

    def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("Email scheduler stopped")
