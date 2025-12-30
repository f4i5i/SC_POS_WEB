# Sunnat Collection - POS & Inventory Management System

A comprehensive, offline-first Point of Sale and Inventory Management system built with Python Flask for perfume retail business.

## Business Information

**Sunnat Collection**
- **Address**: First Floor, Mall of Wah, G.T Road
- **Specialty**: Quality Perfumes at Best Prices
- **Business Type**: Perfume Retail Store

## Features

### Core Modules
- **Point of Sale (POS)**: Fast checkout, multiple payment methods, receipt printing
- **Inventory Management**: Product management, stock tracking, low stock alerts
- **Customer Management**: Customer database, purchase history, loyalty tracking
- **Supplier Management**: Supplier database, purchase orders, payment tracking
- **Reports & Analytics**: Daily/weekly/monthly reports, sales analytics, profit tracking
- **User Management**: Multi-user support with role-based access control

### Key Capabilities
- ✅ **Offline-First**: Works completely offline, syncs when internet available
- ✅ **Automated Reports**: Daily email reports with sales summary and alerts
- ✅ **Cloud Sync**: Automatic synchronization with cloud database
- ✅ **Backup & Restore**: Automated daily backups with retention management
- ✅ **Multi-User**: Support for multiple users with different permission levels
- ✅ **Mobile Responsive**: Touch-friendly UI optimized for tablets
- ✅ **Professional Branding**: Complete Sunnat Collection branding throughout the system

### Branding & Design
The system features professional **Sunnat Collection** branding:
- 🎨 **Logo Integration**: Business logo appears in navigation bar, login page, receipts, and settings
- 🖼️ **Favicon**: Custom favicon displays in browser tabs
- 🧾 **Branded Receipts**: Professional thermal receipts with business logo and contact information
- 🎯 **Multiple Logo Variations**: 7 logo variations (black, white, blue, grey, with/without text) optimized for different contexts
- 📍 **Business Address**: "First Floor, Mall of Wah, G.T Road" displayed on all customer-facing documents

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Step 1: Clone or Download

```bash
cd /path/to/project
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

**Important configurations in `.env`:**
- `SECRET_KEY`: Change to a random secret key for production
- Email settings (MAIL_USERNAME, MAIL_PASSWORD)
- Business details (BUSINESS_NAME, BUSINESS_ADDRESS, etc.)
- Cloud database URL (if using sync feature)

### Step 5: Initialize Database

```bash
# Initialize database and create tables
python3 init_db.py
```

This will create:
- Database tables
- Default admin user (username: `admin`, password: `admin123`)
- Business settings with Sunnat Collection details
- Business address: "First Floor, Mall of Wah, G.T Road"
- Default product categories (Perfumes - Men/Women/Unisex, Attars, Body Sprays, Gift Sets, Accessories)

**⚠️ IMPORTANT**: Change the admin password after first login!

### Step 6: Run the Application

```bash
python run.py
```

The application will be available at: `http://localhost:5000`

## First Time Setup

1. **Login**: Use credentials `admin` / `admin123`
2. **Change Password**: Go to Settings → User Profile
3. **Configure Business**: Settings → Business Settings
4. **Add Products**: Inventory → Add Products
5. **Create Users**: Settings → User Management
6. **Test POS**: Go to POS and make a test sale

## Usage

### Creating Sample Data (For Testing)

```bash
flask create-sample-data
```

This creates:
- Sample perfume products
- Sample customers
- Categories and suppliers

### Manual Operations

```bash
# Manual sync to cloud
flask run-sync

# Send daily report manually
flask send-daily-report

# Create backup manually
flask backup-database
```

### User Roles

- **Admin**: Full access to all features
- **Manager**: All features except system settings
- **Cashier**: POS operations only
- **Stock Manager**: Inventory management only
- **Accountant**: Reports and analytics only

## Configuration Guide

### Email Setup (Gmail Example)

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account Settings
   - Security → 2-Step Verification → App Passwords
   - Generate password for "Mail"
3. Update `.env`:
   ```
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   DAILY_REPORT_RECIPIENTS=recipient1@example.com,recipient2@example.com
   ```

### Cloud Sync Setup

1. Set up PostgreSQL or MySQL database on cloud (Heroku, AWS, etc.)
2. Update `.env`:
   ```
   ENABLE_CLOUD_SYNC=True
   CLOUD_DATABASE_URL=postgresql://user:pass@host:port/dbname
   ```
3. Restart application

### Backup Configuration

Backups are stored in the `backups/` folder.

- Automatic backups run daily at configured time
- Retention period: 30 days (configurable)
- Manual backup: `flask backup-database`

## Project Structure

```
perfume_pos/
├── app/                    # Application package
│   ├── models.py          # Database models
│   ├── routes/            # Route blueprints
│   ├── services/          # Background services
│   ├── templates/         # HTML templates
│   ├── static/            # CSS, JS, images
│   └── utils/             # Helper functions
├── backups/               # Database backups
├── logs/                  # Application logs
├── migrations/            # Database migrations
├── config.py             # Configuration classes
├── run.py                # Application entry point
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables
```

## API Endpoints

### Authentication
- `POST /login` - User login
- `POST /logout` - User logout

### POS
- `GET /pos` - POS interface
- `POST /pos/sale` - Complete sale
- `GET /pos/search` - Search products

### Inventory
- `GET /inventory` - Product list
- `POST /inventory/add` - Add product
- `PUT /inventory/edit/<id>` - Edit product
- `DELETE /inventory/delete/<id>` - Delete product

### Reports
- `GET /reports/daily` - Daily sales report
- `GET /reports/weekly` - Weekly report
- `GET /reports/monthly` - Monthly report
- `GET /reports/custom` - Custom date range report

## Troubleshooting

### Database Issues

```bash
# Reset database (⚠️ deletes all data!)
rm perfume_pos.db
flask init-db
```

### Sync Not Working

1. Check internet connection
2. Verify `CLOUD_DATABASE_URL` in `.env`
3. Check logs in `logs/app.log`
4. Try manual sync: `flask run-sync`

### Email Not Sending

1. Verify email credentials in `.env`
2. Check if 2FA and App Password are set (for Gmail)
3. Check logs for errors
4. Test with: `flask send-daily-report`

### Port Already in Use

Change port in `run.py`:
```python
app.run(host='0.0.0.0', port=5001)  # Changed from 5000
```

## Security Best Practices

1. **Change Default Password**: Immediately after installation
2. **Use Strong SECRET_KEY**: Generate random key for production
3. **Enable HTTPS**: In production, use SSL certificate
4. **Regular Backups**: Enable automatic backups
5. **Update Dependencies**: Keep packages up to date
6. **Limit Access**: Use firewall to restrict access
7. **Monitor Logs**: Regularly check logs for suspicious activity

## Performance Tips

1. **Database Indexing**: Automatically handled by migrations
2. **Image Optimization**: Resize product images before upload
3. **Regular Cleanup**: Delete old logs and backups
4. **Hardware**: Use SSD for better database performance
5. **Network**: Use ethernet for stable sync connection

## Support

For issues, questions, or feature requests:
- Check logs in `logs/app.log`
- Review documentation
- Contact: admin@sunnatcollection.com

## License

Proprietary software for Sunnat Collection.
All rights reserved.

## Version

Version: 1.0.0
Last Updated: December 2024

---

**Made with ❤️ for Sunnat Collection**
