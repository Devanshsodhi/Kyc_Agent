# 🤖 AI-Powered KYC Compliance Agent

**An intelligent, fully automated KYC (Know Your Customer) compliance system powered by Groq AI that processes documents, validates compliance rules, and sends automated expiry notifications.**
---

## ✨ Features

### 🤖 **Intelligent Document Processing**
- Automatically fetches KYC emails from Gmail
- Extracts text from PDFs and images using **EasyOCR** (pure Python, no external dependencies)
- AI-powered document analysis using **Groq Llama 3.1-8B-Instant**
- Multi-format support: PDF, PNG, JPG, JPEG

### 📊 **Smart Compliance Validation**
- Automatic ID expiry detection and rejection
- Cross-document data consistency verification
- Address proof recency validation (3-month rule)
- Document format and completeness checks
- Intelligent flagging with clear reasoning

### 📧 **Automated Email Notifications**
- Captures customer email addresses automatically
- Sends expiry notifications to expired ID holders
- Advance reminders (30 days before expiry)
- Professional email templates with clear action items
- Full audit trail of all sent notifications

### 💬 **Conversational AI Interface**
- Natural language queries: *"Show expired IDs"*, *"Send notifications"*
- Smart intent detection (queries vs actions)
- Real-time compliance dashboard
- Detailed record viewer with validation reports

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **AI/LLM** | Groq Llama 3.1-8B-Instant |
| **OCR** | EasyOCR (Python-based) |
| **Email** | Gmail API (OAuth 2.0) |
| **Database** | SQLite |
| **UI** | Streamlit |
| **Language** | Python 3.10+ |

---

## 🚀 Quick Start

### 1. **Install Dependencies**

```bash
pip install -r requirements.txt
```

### 2. **Set Up API Keys**

Create `.env` file:
```bash
GROQ_API_KEY=your_groq_api_key_here
```

Get a free Groq API key at: https://console.groq.com/

### 3. **Configure Gmail API**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable **Gmail API**
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json` to project root
5. Required scopes:
   - `gmail.readonly` (read emails)
   - `gmail.send` (send notifications)

### 4. **Run the App**

```bash
streamlit run app.py
```

🎉 **Done!** Open http://localhost:8501

---

## 📋 How It Works

### **Email Processing Flow**

```
┌─────────────────┐
│ Gmail Inbox     │
│ "KYC - 98765"   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Extract Docs    │
│ (PDF/Images)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ EasyOCR         │
│ Text Extraction │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Groq AI         │
│ Validation      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Auto Reject     │
│ if ID Expired   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save to DB      │
│ + Customer Email│
└─────────────────┘
```

### **Notification Flow**

```
User: "Send notifications"
         │
         ▼
Check for expired/expiring IDs
         │
         ▼
Use saved customer emails
         │
         ▼
Send professional email
         │
         ▼
Log in database ✅
```

---

## 📊 Features in Detail

### **1. Automatic Email Capture**

When processing KYC emails, the system automatically:
- Extracts sender's email address
- Stores it in `customer_email` field
- Uses it for automated notifications

**No manual email entry needed!**

### **2. Smart Expiry Detection**

The system automatically:
- Checks ID expiry dates against current date
- **Overrides LLM** if it incorrectly approves expired IDs
- Adds flags: *"ID expired X days ago"*
- Changes status: `APPROVED` → `REJECTED`

### **3. Natural Language Interface**

**Example commands:**
- `"Show expired IDs"` → Lists all expired customers
- `"Send notifications"` → Triggers email notification workflow
- `"Which customers need review?"` → Shows flagged records
- `"Show IDs expiring soon"` → Lists IDs expiring within 30 days

### **4. Email Notification Templates**

**Expired ID Email:**
```
Subject: ⚠️ KYC Update Required - ID Expired

Your ID expired on 2025-10-22.
Please submit updated documents within 7 days.
```

**Expiring Soon Email:**
```
Subject: 🔔 Reminder: Your ID expires in 15 days

Proactive reminder to renew before expiry.
```

---

## 🗂️ Project Structure

```
kyc-agent/
├── app.py                          # Streamlit web interface
├── kyc_agent.py                    # Core processing engine
├── requirements.txt                # Python dependencies
├── .env                            # API keys (create from .env.example)
├── .env.example                    # Template
├── credentials.json                # Gmail OAuth (download from Google)
├── token.json                      # Auto-generated after auth
├── kyc_compliance.db               # SQLite database
├── kyc_documents/                  # Downloaded documents
├── .streamlit/
│   └── config.toml                 # Streamlit config
├── demo_test.py                    # Generate test data
├── scheduler.py                    # Automation script
├── AUTO_NOTIFICATIONS_GUIDE.md     # Detailed notification docs
└── README.md                       # This file
```

---

## 💻 Usage

### **Interactive Web Interface**

```bash
streamlit run app.py
```

Then:
1. Click **"🔄 Process New KYC Emails"** → Fetches and processes emails
2. Go to **"💬 AI Assistant"** → Ask questions or send notifications
3. Go to **"📊 Dashboard"** → View compliance overview
4. Go to **"📋 Records"** → See detailed records with customer emails

### **Automated Notifications**

In the AI Assistant tab:
1. Type: `"Send notifications"`
2. Click: **"📧 Send to Saved Emails (Auto)"**
3. Done! Emails sent to all expired/expiring customers

### **Testing Mode**

Use manual email override for testing:
1. Type: `"Send notifications"`
2. Expand **"📝 Manual Email Override"**
3. Enter your test email
4. All notifications go to your email instead

### **Re-validate Existing Records**

If you have old records marked as APPROVED but IDs have since expired:
- Click **"🔍 Re-validate All Records"**
- System automatically updates expired IDs to REJECTED

---

## 📧 Email Subject Formats

The system accepts flexible subject formats:

✅ **Supported:**
- `KYC - 98765`
- `ID: 98765 - KYC Documents`
- `KYC Documents - CUST12345`
- `KYC: CUST12345`
- Any subject with "KYC" and a 4+ digit customer ID

---

## 🗄️ Database Schema

### **kyc_records table**
```sql
- customer_id (TEXT, PRIMARY KEY)
- customer_email (TEXT)          ← Auto-captured from email
- email_date (TEXT)
- status (TEXT)                   ← APPROVED/REJECTED/HUMAN_REVIEW_NEEDED
- name (TEXT)
- dob (TEXT)
- id_number (TEXT)
- id_type (TEXT)
- id_expiry (TEXT)                ← Auto-validated
- address (TEXT)
- documents (TEXT, JSON)
- validation_result (TEXT, JSON)
- flags (TEXT, JSON)
- processed_at (TEXT)
```

### **logs table**
```sql
- id (INTEGER, PRIMARY KEY)
- timestamp (TEXT)
- customer_id (TEXT)
- action (TEXT)
- details (TEXT)
```

---

## 🔐 Validation Rules

The AI validates against these rules:

1. ✅ **ID Expiry**: Must not be expired
2. ✅ **Data Consistency**: Name/DOB must match across documents
3. ✅ **Address Proof**: Must be recent (within 3 months)
4. ✅ **ID Format**: Validates format based on ID type
5. ✅ **Completeness**: All required documents must be present
6. ✅ **Clarity**: Documents must be clear and readable

**Post-Processing:** System automatically rejects if ID expiry date < today

---

## 🤖 AI Prompt Example

```
You are a KYC compliance validator. Analyze documents and extract:
- Name, DOB, ID type, ID number, ID expiry, Address
- Validation status: APPROVED/REJECTED/HUMAN_REVIEW_NEEDED
- Flags for any issues
- Detailed compliance report

Rules:
1. ID should not be expired
2. Name and DOB must match across documents
3. Address proof must be valid and recent
...
```

---

## 🔄 Automation

### **Scheduled Processing (Every 30 minutes)**

Use `scheduler.py`:
```bash
python scheduler.py
```

Or set up a cron job:
```bash
*/30 * * * * cd /path/to/kyc-agent && python kyc_agent.py
```

### **Automated Daily Notifications**

Add to cron:
```bash
0 9 * * * cd /path/to/kyc-agent && python -c "from kyc_agent import check_and_notify_expired_ids; check_and_notify_expired_ids(use_saved_emails=True)"
```

---

## ⚙️ Configuration

### **Streamlit Config** (`.streamlit/config.toml`)
```toml
[logger]
level = "error"  # Suppress warnings

[client]
showErrorDetails = false
toolbarMode = "minimal"
```

### **Environment Variables** (`.env`)
```bash
GROQ_API_KEY=gsk_...
```

---

## 🐛 Troubleshooting

### **Gmail API Errors**

**Problem:** `invalid_scope: Bad Request`

**Solution:**
```bash
# Delete old token
del token.json

# Restart app and re-authenticate
streamlit run app.py
```

### **OCR Not Working**

**Problem:** `PIL.Image has no attribute 'ANTIALIAS'`

**Solution:**
```bash
# Downgrade Pillow
pip install Pillow==9.5.0
```

### **No Email Notifications Sent**

**Problem:** Notifications don't send

**Check:**
1. Gmail API has `gmail.send` scope (line 46 in `kyc_agent.py` uncommented)
2. Deleted `token.json` and re-authenticated
3. Customer email exists in database: `SELECT customer_email FROM kyc_records`

---

## 📊 Sample Output

### **Console Output**
```
🔄 Initializing EasyOCR...
✅ EasyOCR ready!
🔍 Fetching KYC emails...
📧 Found 1 KYC emails

📋 Processing KYC for customer: 98765
📎 Extracted 1 documents
🔎 OCR on id_proof.jpg...
🤖 Validating with AI...
⚠️  Auto-rejected: ID expired 5 days ago
✅ Status: REJECTED
🚩 Flags: ID expired 5 days ago on 2025-10-22
```

### **Email Notification Log**
```
🔍 Checking 1 records for expired IDs...
⚠️  98765: ID expired 5 days ago
✅ Email sent to customer@example.com for 98765
📧 Sent 1 notification emails
```

---

## 🎯 Use Cases

- **Fintech Companies**: Automate customer onboarding KYC
- **Banks**: Compliance validation for account opening
- **Crypto Exchanges**: Regulatory compliance automation
- **Insurance**: Policy holder verification
- **E-commerce**: Seller verification
- **Lending Platforms**: Borrower identity verification

---

## 🚀 Future Enhancements

- [ ] HTML email templates with branding
- [ ] Multi-language email support
- [ ] SMS notifications via Twilio
- [ ] Face recognition for photo verification
- [ ] Bulk upload interface
- [ ] REST API for integrations
- [ ] Advanced fraud detection
- [ ] Export compliance reports (PDF)
- [ ] Integration with AML (Anti-Money Laundering) systems

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push and create a Pull Request

---

## 📄 License

MIT License - Free to use and modify

---

## 🙏 Acknowledgments

- **Groq** for blazing-fast LLM inference
- **EasyOCR** for pure Python OCR
- **Streamlit** for beautiful UI framework
- **Gmail API** for email automation

---

## 📞 Support

Having issues? Check:
- [AUTO_NOTIFICATIONS_GUIDE.md](AUTO_NOTIFICATIONS_GUIDE.md) for notification setup
- `.env.example` for configuration template
- `demo_test.py` for generating test data

---

**Built with ❤️ for automated compliance**

*Powered by Groq AI | No external OCR dependencies | Production-ready*
