# Quick Start Guide - Sunnat Collection POS System

Get up and running in 5 minutes!

## 🚀 Installation

```bash
cd /home/f4i5i/SC_POC/SOC_WEB_APP
./setup.sh
```

## 🔧 Configuration

Edit `.env` with your details:

```bash
nano .env
```

Minimum required:
- `BUSINESS_NAME=Sunnat Collection`
- `BUSINESS_ADDRESS=Mall of Wah, Pakistan`

## ▶️ Run Application

```bash
source venv/bin/activate
python run.py
```

## 🔐 First Login

- URL: http://localhost:5000/auth/login
- Username: `admin`
- Password: `admin123`

**⚠️ Change password after login!**

## 📦 Create Sample Data

```bash
flask create-sample-data
```

## 🎯 Basic Usage

### Add Your First Product

1. Go to **Inventory** → **Add Product**
2. Fill in:
   - Product Code: `PERF001`
   - Name: `Musk Al Madinah`
   - Selling Price: `750`
   - Quantity: `50`
3. Click **Save**

### Make Your First Sale

1. Go to **POS**
2. Search for product by name or code
3. Add to cart
4. Select payment method
5. Click **Complete Sale**
6. Print receipt

### Add a Customer

1. Go to **Customers** → **Add Customer**
2. Fill in name and phone
3. Click **Save**

### View Reports

1. Go to **Reports** → **Daily Report**
2. See sales summary, top products, and alerts

## 📧 Setup Email Reports (Optional)

1. Get Gmail App Password (see INSTALLATION_GUIDE.md)
2. Update `.env`:
```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
DAILY_REPORT_RECIPIENTS=manager@example.com
```

## 💾 Backup Your Data

Manual backup:
```bash
flask backup-database
```

Backups are automatically created daily at 11 PM.

## 🆘 Common Issues

### Port Already in Use
```bash
# Edit run.py and change port to 5001
```

### Database Error
```bash
rm perfume_pos.db
flask init-db
```

### Email Not Working
- Enable 2FA on Gmail
- Use App Password, not regular password
- Check logs: `tail -f logs/app.log`

## 📱 User Roles

- **Admin**: Full access
- **Manager**: All except settings
- **Cashier**: POS only
- **Stock Manager**: Inventory only
- **Accountant**: Reports only

## ⌨️ Keyboard Shortcuts (POS)

- `F1` - Focus search
- `F2` - Quick add customer
- `F3` - Hold sale
- `F4` - Retrieve held sales
- `Enter` - Complete sale
- `Esc` - Clear cart

## 📊 Daily Workflow

1. **Morning**: Check stock alerts
2. **During Day**: Process sales at POS
3. **Evening**: Review daily report
4. **Night**: Automatic backup runs

## 🔄 Offline Operation

The system works completely offline:
- All sales are saved locally
- Syncs to cloud when internet returns
- No data loss during offline periods

## 📈 Next Steps

1. **Add all your products** in Inventory
2. **Create customer database**
3. **Train staff** on POS system
4. **Configure email reports**
5. **Set up cloud sync** (optional)
6. **Regular backups** to external drive

## 🎓 Training Tips

- Use **sample data** for practice
- Test all features before going live
- Keep the **README.md** handy
- Review **INSTALLATION_GUIDE.md** for details

## 📞 Need Help?

- Check logs: `logs/app.log`
- Review documentation
- Contact system administrator

---

**Ready to go! Happy selling! 🛍️**
