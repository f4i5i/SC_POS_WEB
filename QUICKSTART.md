# Quick Start Guide - Sunnat Collection POS

## Store Information
**Sunnat Collection**
First Floor, Mall of Wah, G.T Road
Quality Perfumes at Best Prices

---

## 🚀 Quick Setup (5 Minutes)

### 1. Activate Virtual Environment
```bash
cd /home/f4i5i/SC_POC/SOC_WEB_APP
source venv/bin/activate
```

### 2. Initialize Database (First Time Only)
```bash
python3 init_db.py
```

### 3. Start the Application
```bash
python3 run.py
```

### 4. Open in Browser
Go to: **http://localhost:5000**

### 5. Login
- **Username**: `admin`
- **Password**: `admin123`

⚠️ Change password immediately after first login!

---

## 📋 Daily Operations

### Opening Procedure
1. Start the application: `python3 run.py`
2. Login to the system
3. Check inventory alerts (if any)
4. Start POS for sales

### Making a Sale
1. Go to **POS** (sidebar or F1)
2. Search for product by name/code
3. Add items to cart
4. Apply discount (if needed)
5. Click **Checkout** (F4)
6. Select payment method
7. Enter amount paid
8. Complete sale
9. Print receipt

### Adding New Products
1. Go to **Inventory** → **Add Product**
2. Fill in product details:
   - Product Code, Name, Brand
   - Category (e.g., Perfumes - Men)
   - Size, Price, Stock Quantity
3. Click **Add Product**

### End of Day
1. Go to **Reports** → **Daily Report**
2. Review sales summary
3. Check cash in drawer
4. Print/export report if needed

---

## 🎯 Quick Tips

### Keyboard Shortcuts (POS)
- `F1` - Focus search box
- `F4` - Open checkout

### Payment Methods
- Cash
- Card
- EasyPaisa
- JazzCash

### Product Categories
- Perfumes - Men
- Perfumes - Women
- Perfumes - Unisex
- Attars
- Body Sprays
- Gift Sets
- Accessories

### User Roles
- **Admin** - Full access (you)
- **Manager** - All operations
- **Cashier** - POS only
- **Stock Manager** - Inventory only
- **Accountant** - Reports only

---

## 🔧 Common Tasks

### Add New User
1. Settings → User Management
2. Click **Add New User**
3. Fill details and select role
4. Save

### Update Business Info
1. Settings → Business Settings
2. Update phone, email, tax rate
3. Address is pre-set: "First Floor, Mall of Wah, G.T Road"
4. Save changes

### Check Low Stock
1. Go to **Inventory**
2. Click **Low Stock** filter
3. Reorder products as needed

### View Sales History
1. Go to **POS** → **Sales**
2. Filter by date range
3. Click any sale to view details

### Generate Reports
1. Go to **Reports**
2. Select report type:
   - Daily (today's sales)
   - Weekly (last 7 days)
   - Monthly (current month)
   - Custom (any date range)

---

## ⚠️ Troubleshooting

### Can't Login
- Check username/password
- Default: admin / admin123
- Reset database if needed: `python3 init_db.py` (⚠️ deletes all data!)

### Port Already in Use
- Close other applications using port 5000
- Or change port in `run.py`

### Product Not Found
- Check spelling
- Try searching by product code
- Use barcode scanner

### Receipt Not Printing
- Check printer connection
- Try browser print (Ctrl+P)
- Check receipt template settings

---

## 📞 Support

For technical support:
- Check `logs/app.log` for errors
- Review README.md for detailed documentation
- Contact: admin@sunnatcollection.com

---

## 🎨 Branding

The system includes Sunnat Collection branding:
- Logo on login page
- Logo in navigation bar
- Logo on printed receipts
- Business address on all receipts
- Professional thermal receipt layout

---

**Version 1.0.0** | Last Updated: December 2024
