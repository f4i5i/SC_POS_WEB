# Installation Guide - Sunnat Collection POS System

## Prerequisites

Before installing the POS system, ensure you have:

- **Python 3.8 or higher** installed
- **pip** (Python package manager)
- **Git** (optional, for cloning)
- At least **500MB** free disk space
- **Internet connection** (for initial setup only)

## Quick Installation (Recommended)

### Step 1: Navigate to Project Directory

```bash
cd /home/f4i5i/SC_POC/SOC_WEB_APP
```

### Step 2: Run Setup Script

```bash
./setup.sh
```

The setup script will:
- Create a Python virtual environment
- Install all required dependencies
- Create necessary directories
- Initialize the database
- Create a default admin user

### Step 3: Configure Environment

Edit the `.env` file with your business details:

```bash
nano .env
```

Important settings to configure:
- `BUSINESS_NAME`: Your business name
- `BUSINESS_ADDRESS`: Your physical address
- `BUSINESS_PHONE`: Contact phone number
- Email settings (if you want daily reports)

### Step 4: Start the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Run the application
python run.py
```

The application will start on `http://localhost:5000`

### Step 5: First Login

- **URL**: http://localhost:5000/auth/login
- **Username**: admin
- **Password**: admin123

**⚠️ IMPORTANT**: Change the admin password immediately after first login!

---

## Manual Installation (Alternative)

If you prefer manual installation:

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Setup Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Create Directories

```bash
mkdir -p backups logs static/{uploads,receipts,reports}
```

### 5: Initialize Database

```bash
export FLASK_APP=run.py
flask init-db
```

Or using Python directly:

```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

### 6. Create Admin User

```bash
python -c "
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    admin = User(username='admin', email='admin@sunnatcollection.com',
                 full_name='Administrator', role='admin', is_active=True)
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    print('Admin user created successfully!')
"
```

### 7. Run Application

```bash
python run.py
```

---

## Creating Sample Data (Optional)

To create sample products and customers for testing:

```bash
# Activate virtual environment first
source venv/bin/activate

# Run sample data creation
flask create-sample-data
```

This will create:
- 5 sample perfume products
- 3 sample customers
- 1 sample supplier
- Product categories

---

## Configuration Details

### Email Configuration (Gmail Example)

To enable daily email reports:

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate App Password**:
   - Go to Google Account → Security → 2-Step Verification → App Passwords
   - Select "Mail" and generate password

3. **Update .env**:
```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-generated-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
DAILY_REPORT_RECIPIENTS=manager@example.com,owner@example.com
DAILY_REPORT_TIME=18:00
```

### Cloud Sync Configuration

To enable cloud database synchronization:

1. **Set up a cloud PostgreSQL database** (Heroku, AWS RDS, etc.)

2. **Update .env**:
```env
ENABLE_CLOUD_SYNC=True
CLOUD_DATABASE_URL=postgresql://user:password@host:port/database
SYNC_INTERVAL_MINUTES=30
AUTO_SYNC=True
```

### Backup Configuration

Backups are enabled by default:

```env
BACKUP_ENABLED=True
BACKUP_TIME=23:00
BACKUP_RETENTION_DAYS=30
```

Backups are stored in the `backups/` directory.

---

## Running as a Service (Production)

### Using systemd (Linux)

Create a service file `/etc/systemd/system/sunnat-pos.service`:

```ini
[Unit]
Description=Sunnat Collection POS System
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/f4i5i/SC_POC/SOC_WEB_APP
Environment="PATH=/home/f4i5i/SC_POC/SOC_WEB_APP/venv/bin"
ExecStart=/home/f4i5i/SC_POC/SOC_WEB_APP/venv/bin/python run.py

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable sunnat-pos
sudo systemctl start sunnat-pos
sudo systemctl status sunnat-pos
```

---

## Troubleshooting

### Database Errors

```bash
# Reset database (⚠️ deletes all data!)
rm perfume_pos.db
flask init-db
```

### Permission Errors

```bash
# Fix permissions
chmod -R 755 .
chmod +x setup.sh
```

### Port Already in Use

Change the port in `run.py`:

```python
app.run(host='0.0.0.0', port=5001)  # Changed from 5000
```

### Missing Dependencies

```bash
# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

### Email Not Sending

1. Verify email credentials in `.env`
2. Check if 2FA is enabled and App Password is used
3. Check logs: `tail -f logs/app.log`
4. Test manually: `flask send-daily-report`

---

## Upgrading

To upgrade to a new version:

```bash
# Backup current database
cp perfume_pos.db perfume_pos.db.backup

# Pull latest code
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations if any
flask db upgrade

# Restart application
```

---

## Uninstallation

To remove the application:

```bash
# Stop the application
# Ctrl+C or stop the service

# Backup your data first!
cp perfume_pos.db ~/backup-$(date +%Y%m%d).db
cp -r backups ~/backups-$(date +%Y%m%d)

# Remove virtual environment
rm -rf venv

# Remove database
rm perfume_pos.db

# Remove logs and temporary files
rm -rf logs backups static/uploads static/receipts static/reports
```

---

## Security Notes

1. **Change default password** immediately
2. **Use strong SECRET_KEY** in production
3. **Enable HTTPS** in production
4. **Regular backups** are critical
5. **Update dependencies** regularly
6. **Restrict network access** using firewall
7. **Monitor logs** for suspicious activity

---

## Getting Help

- Check logs: `tail -f logs/app.log`
- Review error messages carefully
- Ensure all prerequisites are met
- Verify .env configuration
- Check Python version compatibility

For additional support, contact your system administrator.
