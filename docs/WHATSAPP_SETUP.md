# WhatsApp Cloud API Setup Guide

## Overview
This guide will help you set up **FREE** WhatsApp messaging for your POS system using Meta's WhatsApp Cloud API.

### What's Included (FREE):
- Unlimited messages to verified test numbers (up to 5)
- 1,000 free service conversations per month
- Free utility messages within 24-hour customer-initiated window

---

## Step 1: Create Meta Business Account

1. Go to [business.facebook.com](https://business.facebook.com/)
2. Click "Create Account"
3. Enter your business details:
   - Business name: Sunnat Collection
   - Your name and email
4. Verify your email address

---

## Step 2: Create Meta Developer Account

1. Go to [developers.facebook.com](https://developers.facebook.com/)
2. Click "Get Started" or "My Apps"
3. Accept the terms and complete registration
4. Link your Meta Business account

---

## Step 3: Create WhatsApp Business App

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps/)
2. Click "Create App"
3. Select "Business" as app type
4. Fill in:
   - App name: `Sunnat Collection POS`
   - Contact email: your email
   - Business Account: Select your business
5. Click "Create App"

---

## Step 4: Add WhatsApp Product

1. In your app dashboard, find "Add Products"
2. Click "Set up" on WhatsApp
3. You'll be taken to WhatsApp setup wizard

---

## Step 5: Get Your Credentials

### A. Phone Number ID
1. Go to WhatsApp > API Setup in left sidebar
2. You'll see a test phone number provided by Meta
3. Copy the **Phone number ID** (looks like: `123456789012345`)

### B. Access Token
1. On the same API Setup page
2. Find "Temporary access token"
3. Click "Copy" to get your token

**Important:** Temporary tokens expire in 24 hours. For production:
1. Go to WhatsApp > Configuration
2. Click "Generate" under Permanent Token
3. Or create a System User token (recommended for production)

### C. Business Account ID
1. Go to WhatsApp > Configuration
2. Find your WhatsApp Business Account ID

---

## Step 6: Add Test Numbers

Before you can send messages, you must verify recipient numbers:

1. Go to WhatsApp > API Setup
2. Scroll to "To" phone number dropdown
3. Click "Manage phone number list"
4. Add up to 5 phone numbers for testing
5. Each number will receive a verification code
6. Enter the code to verify

**Tip:** Add your own number and a few test customer numbers.

---

## Step 7: Configure Your POS

Add these to your `.env` file:

```env
# WhatsApp Cloud API (FREE)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id_here
```

Example:
```env
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAABsbCS1I...long_token...ZDZD
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
```

---

## Step 8: Test the Integration

1. Restart your Flask app
2. Make a test sale
3. At checkout, select a customer with a verified phone number
4. Click "Send WhatsApp Receipt"
5. Check the phone for the message

---

## Sending Receipts

### From POS Interface
After completing a sale, you can:
1. Click the WhatsApp icon on the receipt
2. Enter/confirm customer phone number
3. Click Send

### API Endpoint
```
POST /receipts/send-whatsapp/<sale_id>
{
    "phone": "03001234567"  // Optional if customer has phone
}
```

---

## Phone Number Format

The system automatically formats Pakistani numbers:
- `03001234567` → `923001234567`
- `+923001234567` → `923001234567`
- `923001234567` → `923001234567`

---

## Fallback System

If WhatsApp Cloud API fails, the system automatically falls back to:

1. **Primary:** WhatsApp Cloud API (FREE, automatic)
2. **Secondary:** Twilio (if configured, paid)
3. **Fallback:** wa.me link (always works, manual click required)

---

## Troubleshooting

### "WhatsApp Cloud API not configured"
- Check your `.env` file has the correct values
- Restart the Flask app after adding credentials

### "Message failed to send"
- Verify the recipient number is in your test numbers list
- Check your access token hasn't expired
- Ensure phone number format is correct

### "Recipient not in allowed list"
- In test mode, you can only message verified numbers
- Add the number to your test list in Meta Developer Console

### Token Expired
- Generate a new token from Meta Developer Console
- Update your `.env` file
- Restart the app

---

## Going to Production

When you're ready for unlimited messaging:

1. **Verify Your Business**
   - Go to Business Settings > Security Center
   - Complete Business Verification

2. **Add Your Own Phone Number**
   - Go to WhatsApp > Phone Numbers
   - Click "Add phone number"
   - Verify with OTP

3. **Create Permanent Token**
   - Go to Business Settings > Users > System Users
   - Create a system user
   - Generate permanent token

4. **Request Higher Limits**
   - After verification, you get 1,000/day
   - Request increase through Meta Business Help

---

## Receipt Format Example

When sent, receipts look like this:

```
*SUNNAT COLLECTION*
━━━━━━━━━━━━━━━━━━━━
📄 Receipt: *SC-2026-001234*
📅 Date: 09 Jan 2026, 02:30 PM

*Items:*
• Oud Perfume 50ml
  1 × Rs.2,500 = Rs.2,500
• Rose Attar 10ml
  2 × Rs.800 = Rs.1,600

━━━━━━━━━━━━━━━━━━━━
Subtotal: Rs.4,100.00
*TOTAL: Rs.4,100.00*

💳 Paid by: Cash

👤 Ahmed Khan
⭐ Loyalty Points: 250

━━━━━━━━━━━━━━━━━━━━
Thank you for shopping with us! 🙏
```

---

## Support

For Meta/WhatsApp API issues:
- [WhatsApp Business API Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Meta Business Help Center](https://www.facebook.com/business/help)

For POS integration issues:
- Check application logs at `/logs/app.log`
- Contact system administrator
