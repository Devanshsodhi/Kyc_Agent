import os
import re
import base64
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import json
import warnings
import logging
import sys

# Suppress ALL warnings 
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['PYTHONWARNINGS'] = 'ignore'

# Suppress specific loggers
logging.getLogger('easyocr').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('torch').setLevel(logging.ERROR)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import PyPDF2
import pdfplumber
from pdf2image import convert_from_path
import easyocr
from PIL import Image
from groq import Groq
from dotenv import load_dotenv
import numpy as np

# Initialize EasyOCR reader (loaded once globally)
print("🔄 Initializing EasyOCR (first run takes a moment to download models)...")
ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)  # English only, CPU mode, suppress logs
print("✅ EasyOCR ready!")

load_dotenv()

# Constants
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'  # Email notifications enabled
]
DB_PATH = 'kyc_compliance.db'
DOCS_PATH = Path('kyc_documents')
DOCS_PATH.mkdir(exist_ok=True)

# Initialize Groq
api_key = os.getenv('GROQ_API_KEY')
if not api_key:
    print("⚠️  Warning: GROQ_API_KEY not set in .env file")
    print("Please add your Groq API key to continue.")
    print("Get one free at: https://console.groq.com/")
client = Groq(api_key=api_key) if api_key else None

# KYC Validation Rules
KYC_RULES = """
1. ID should not be expired (check expiry date)
2. Name and date of birth must match across all documents
3. Address proof must be valid and recent (within 3 months)
4. Validate PAN/Passport/Emirates ID format
5. All required documents must be present (ID proof, address proof, photo)
6. Document images must be clear and readable
"""

def init_database():
    """Initialize SQLite database for KYC records"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS kyc_records (
        customer_id TEXT PRIMARY KEY,
        customer_email TEXT,
        email_date TEXT,
        status TEXT,
        name TEXT,
        dob TEXT,
        id_number TEXT,
        id_type TEXT,
        id_expiry TEXT,
        address TEXT,
        documents TEXT,
        validation_result TEXT,
        flags TEXT,
        processed_at TEXT
    )''')
    
    try:
        c.execute("SELECT customer_email FROM kyc_records LIMIT 1")
    except sqlite3.OperationalError:
        print("🔄 Migrating database: Adding customer_email column...")
        c.execute("ALTER TABLE kyc_records ADD COLUMN customer_email TEXT")
        conn.commit()
        print("✅ Database migration complete!")
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        customer_id TEXT,
        action TEXT,
        details TEXT
    )''')
    conn.commit()
    conn.close()

def log_action(customer_id: str, action: str, details: str):
    """Log actions to database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO logs (timestamp, customer_id, action, details) VALUES (?, ?, ?, ?)',
              (datetime.now().isoformat(), customer_id, action, details))
    conn.commit()
    conn.close()

def get_gmail_service():
    """Authenticate and return Gmail API service"""
    if not os.path.exists('credentials.json'):
        raise FileNotFoundError(
            "credentials.json not found. Please download OAuth credentials from Google Cloud Console.\n"
            "See README.md for setup instructions."
        )
    
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def fetch_kyc_emails() -> List[Dict[str, Any]]:
    """Fetch emails with subject containing KYC-related keywords"""
    service = get_gmail_service()
    # Search for emails with KYC in subject (more flexible)
    results = service.users().messages().list(userId='me', q='subject:KYC', maxResults=5).execute()
    messages = results.get('messages', [])
    
    email_data = []
    for msg in messages:
        message = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = message['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        
        # Extract sender email address
        sender_email = next((h['value'] for h in headers if h['name'] == 'From'), '')
        # Parse email from "Name <email@example.com>" format
        email_match = re.search(r'<(.+?)>|^([^\s<>]+@[^\s<>]+)$', sender_email)
        customer_email = email_match.group(1) or email_match.group(2) if email_match else sender_email
        
        # Extract customer_id from various subject formats:
        customer_id = None
        
        # Patterns
        match = re.search(r'KYC\s*[:\-]\s*(\w+)', subject, re.IGNORECASE)
        if match:
            customer_id = match.group(1)
        
        
        if not customer_id:
            match = re.search(r'ID\s*[:\-]?\s*(\w+)', subject, re.IGNORECASE)
            if match:
                customer_id = match.group(1)
        
        if not customer_id:
            match = re.search(r'\b(\d{4,})\b', subject)  # At least 4 digits
            if match:
                customer_id = match.group(1)
        
        if customer_id:
            email_data.append({
                'customer_id': customer_id,
                'customer_email': customer_email,
                'message_id': msg['id'],
                'message': message,
                'date': next((h['value'] for h in headers if h['name'] == 'Date'), '')
            })
            log_action(customer_id, 'EMAIL_FETCHED', f'Subject: {subject}, From: {customer_email}')
    
    return email_data

def extract_documents(email_data: Dict[str, Any]) -> List[Path]:
    """Extract and download PDF/image attachments from email"""
    service = get_gmail_service()
    customer_id = email_data['customer_id']
    message = email_data['message']
    files = []
    
    customer_dir = DOCS_PATH / customer_id
    customer_dir.mkdir(exist_ok=True)
    
    def process_parts(parts):
        for part in parts:
            if part.get('filename'):
                filename = part['filename']
                if filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
                    if 'data' in part['body']:
                        data = part['body']['data']
                    else:
                        att_id = part['body']['attachmentId']
                        att = service.users().messages().attachments().get(
                            userId='me', messageId=message['id'], id=att_id).execute()
                        data = att['data']
                    
                    file_data = base64.urlsafe_b64decode(data)
                    file_path = customer_dir / filename
                    with open(file_path, 'wb') as f:
                        f.write(file_data)
                    files.append(file_path)
            
            if 'parts' in part:
                process_parts(part['parts'])
    
    if 'parts' in message['payload']:
        process_parts(message['payload']['parts'])
    
    log_action(customer_id, 'DOCUMENTS_EXTRACTED', f'Files: {[f.name for f in files]}')
    return files

def perform_ocr(file_path: Path) -> str:
    """Perform OCR on PDF or image files using EasyOCR"""
    text = ""
    
    if file_path.suffix.lower() == '.pdf':
    #try first with pypdf for parsing text
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        except Exception as e:
            print(f"⚠️  PyPDF2 extraction failed: {e}")
        
        # If no text, use OCR
        if not text.strip():
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
            except Exception as e:
                print(f"⚠️  pdfplumber failed: {e}")
                # Fallback to image OCR with EasyOCR
                try:
                    images = convert_from_path(file_path)
                    for img in images:
                        # Convert PIL image to numpy array for EasyOCR
                        img_array = np.array(img)
                        results = ocr_reader.readtext(img_array, detail=0)
                        text += " ".join(results) + "\n"
                except Exception as ocr_error:
                    print(f"❌ OCR failed: {ocr_error}")
                    print("Note: pdf2image requires poppler. On Windows, install from: https://github.com/oschwartz10612/poppler-windows/releases/")
                    raise
    else:
        # Image file - Use EasyOCR
        try:
            # EasyOCR can read directly from file path
            results = ocr_reader.readtext(str(file_path), detail=0)
            text = " ".join(results)
        except Exception as e:
            print(f"❌ Image OCR failed for {file_path.name}: {e}")
            raise
    
    return text.strip()

def validate_documents_with_llm(customer_id: str, documents_text: Dict[str, str]) -> Dict[str, Any]:
    """Use LLM to validate KYC documents and extract information"""
    if not client:
        raise ValueError("Groq client not initialized. Please set GROQ_API_KEY in .env file")
    
    prompt = f"""You are a KYC compliance validator. Analyze the following documents and extract information.

KYC Validation Rules:
{KYC_RULES}

Documents Text:
{json.dumps(documents_text, indent=2)}

Provide a JSON response with:
{{
    "name": "extracted full name",
    "dob": "date of birth (YYYY-MM-DD)",
    "id_type": "passport/pan/emirates_id/etc",
    "id_number": "ID number",
    "id_expiry": "expiry date (YYYY-MM-DD) if applicable",
    "address": "extracted address",
    "validation_status": "APPROVED/REJECTED/HUMAN_REVIEW_NEEDED",
    "flags": ["list of issues or empty if none"],
    "compliance_report": "detailed explanation of findings",
    "missing_documents": ["list of missing required documents"],
    "data_consistency": "assessment of data matching across documents"
}}

If documents are unclear, incomplete, or have compliance issues, set validation_status to HUMAN_REVIEW_NEEDED or REJECTED.
If ID is expired, flag it. If data doesn't match across documents, flag it.

IMPORTANT: Respond with ONLY valid JSON, no additional text."""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a KYC compliance expert. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=2000
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Post-validation: Check for expired ID (override LLM if needed)
    id_expiry = result.get('id_expiry')
    if id_expiry:
        try:
            expiry_date = datetime.strptime(id_expiry, '%Y-%m-%d').date()
            today = datetime.now().date()
            
            if expiry_date < today:
                # ID is expired - override to REJECTED
                days_expired = (today - expiry_date).days
                result['validation_status'] = 'REJECTED'
                
                # Add or update flags
                flags = result.get('flags', [])
                expiry_flag = f"ID expired {days_expired} days ago on {id_expiry}"
                if expiry_flag not in flags:
                    flags.append(expiry_flag)
                result['flags'] = flags
                
                # Update compliance report
                result['compliance_report'] = f"❌ REJECTED: ID expired {days_expired} days ago. " + result.get('compliance_report', '')
                
                print(f"⚠️  Auto-rejected: ID expired {days_expired} days ago")
            
            elif (expiry_date - today).days <= 30:
                # ID expiring soon - add warning flag
                days_remaining = (expiry_date - today).days
                flags = result.get('flags', [])
                warning_flag = f"ID expires in {days_remaining} days"
                if warning_flag not in flags:
                    flags.append(warning_flag)
                result['flags'] = flags
                print(f"🔔 Warning: ID expires in {days_remaining} days")
                
        except ValueError:
            print(f"⚠️  Invalid date format for expiry: {id_expiry}")
    
    log_action(customer_id, 'LLM_VALIDATION', f'Status: {result.get("validation_status")}')
    return result

def update_temp_db(customer_id: str, email_date: str, validation_result: Dict[str, Any], documents: List[str], customer_email: str = None):
    """Update database with KYC validation results"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO kyc_records 
        (customer_id, customer_email, email_date, status, name, dob, id_number, id_type, id_expiry, 
         address, documents, validation_result, flags, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (customer_id, customer_email, email_date, validation_result.get('validation_status'),
         validation_result.get('name'), validation_result.get('dob'),
         validation_result.get('id_number'), validation_result.get('id_type'),
         validation_result.get('id_expiry'), validation_result.get('address'),
         json.dumps(documents), json.dumps(validation_result),
         json.dumps(validation_result.get('flags', [])), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    log_action(customer_id, 'DB_UPDATED', f'Status: {validation_result.get("validation_status")}')

def process_kyc_workflow():
    """Main workflow to process KYC emails"""
    init_database()
    print("🔍 Fetching KYC emails...")
    
    try:
        emails = fetch_kyc_emails()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return
    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        return
    
    print(f"📧 Found {len(emails)} KYC emails")
    
    for email_data in emails:
        customer_id = email_data['customer_id']
        print(f"\n📋 Processing KYC for customer: {customer_id}")
        
        try:
            # Extract documents
            documents = extract_documents(email_data)
            print(f"📎 Extracted {len(documents)} documents")
            
            if not documents:
                print(f"⚠️  No documents found for {customer_id}")
                continue
            
            # Perform OCR
            documents_text = {}
            for doc in documents:
                print(f"🔎 OCR on {doc.name}...")
                try:
                    text = perform_ocr(doc)
                    documents_text[doc.name] = text
                except Exception as ocr_error:
                    print(f"⚠️  Failed to process {doc.name}: {ocr_error}")
                    continue
            
            if not documents_text:
                print(f"⚠️  No text extracted from documents for {customer_id}")
                continue
            
            # Validate with LLM
            print(f"🤖 Validating with AI...")
            validation = validate_documents_with_llm(customer_id, documents_text)
            
            # Update database
            update_temp_db(customer_id, email_data['date'], validation, [d.name for d in documents], email_data.get('customer_email'))
            
            status = validation.get('validation_status')
            print(f"✅ Status: {status}")
            if validation.get('flags'):
                print(f"🚩 Flags: {', '.join(validation['flags'])}")
        
        except Exception as e:
            print(f"❌ Error processing {customer_id}: {e}")
            log_action(customer_id, 'ERROR', str(e))
            continue

def generate_compliance_report() -> str:
    """Generate a summary compliance report"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM kyc_records')
    records = c.fetchall()
    conn.close()
    
    report = f"📊 KYC Compliance Report ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
    report += "=" * 60 + "\n\n"
    
    approved = sum(1 for r in records if r[2] == 'APPROVED')
    rejected = sum(1 for r in records if r[2] == 'REJECTED')
    review = sum(1 for r in records if r[2] == 'HUMAN_REVIEW_NEEDED')
    
    report += f"Total Records: {len(records)}\n"
    report += f"✅ Approved: {approved}\n"
    report += f"❌ Rejected: {rejected}\n"
    report += f"⚠️  Human Review Needed: {review}\n"
    
    return report

def send_email_notification(to_email: str, customer_id: str, customer_name: str, id_expiry: str, reason: str = "expired"):
    """Send automated email notification for KYC renewal"""
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import base64
    
    service = get_gmail_service()
    
    # Email templates
    if reason == "expired":
        subject = f"⚠️ KYC Update Required - ID Expired for {customer_id}"
        body = f"""
Dear {customer_name or 'Valued Customer'},

This is an automated notification from our KYC Compliance System.

Our records indicate that your identification document has expired on {id_expiry}.

🔔 Action Required:
To continue using our services without interruption, please update your KYC documents by submitting:
- Valid ID proof (Passport/Emirates ID/National ID)
- Recent address proof (within 3 months)
- Clear photograph

📧 How to Update:
Reply to this email with your updated documents attached, or send a new email with subject:
"KYC - {customer_id}"

⏰ Important: Please complete this process within 7 days to avoid service suspension.

If you have already submitted your documents, please disregard this message.

Best regards,
KYC Compliance Team

---
This is an automated message. For assistance, please contact support.
"""
    elif reason == "expiring_soon":
        subject = f"🔔 Reminder: Your ID will expire soon - {customer_id}"
        body = f"""
Dear {customer_name or 'Valued Customer'},

This is a friendly reminder from our KYC Compliance System.

Your identification document is set to expire on {id_expiry} (within 30 days).

📋 Proactive Action:
To ensure uninterrupted service, we recommend updating your KYC documents before expiry:
- Valid ID proof (Passport/Emirates ID/National ID)
- Recent address proof (within 3 months)
- Clear photograph

📧 How to Update:
Send an email with your updated documents with subject: "KYC - {customer_id}"

Thank you for keeping your information current!

Best regards,
KYC Compliance Team

---
This is an automated reminder. You will receive another notification if your ID expires.
"""
    else:
        subject = f"KYC Verification Required - {customer_id}"
        body = f"""
Dear {customer_name or 'Valued Customer'},

Our KYC Compliance System requires your attention.

Customer ID: {customer_id}
Reason: {reason}

Please submit your KYC documents at your earliest convenience.

Best regards,
KYC Compliance Team
"""
    
    # Create message
    message = MIMEMultipart()
    message['to'] = to_email
    message['subject'] = subject
    message.attach(MIMEText(body, 'plain'))
    
    # Encode and send
    try:
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        print(f"✅ Email sent to {to_email} for {customer_id}")
        log_action(customer_id, 'EMAIL_SENT', f'Reason: {reason}, To: {to_email}')
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
        log_action(customer_id, 'EMAIL_FAILED', f'Error: {str(e)}')
        return False

def check_and_notify_expired_ids(notification_email: str = None, use_saved_emails: bool = False):
    """Check for expired IDs and send automated notifications
    
    Args:
        notification_email: Manual email override (for testing)
        use_saved_emails: If True, use customer_email from database instead
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT customer_id, name, id_expiry, status, customer_email FROM kyc_records WHERE id_expiry IS NOT NULL')
    records = c.fetchall()
    conn.close()
    
    today = datetime.now().date()
    notified_count = 0
    
    print(f"\n🔍 Checking {len(records)} records for expired IDs...")
    
    for customer_id, name, id_expiry_str, status, saved_email in records:
        try:
            # Determine which email to use
            target_email = saved_email if use_saved_emails else notification_email
            
            if not target_email:
                print(f"⚠️  {customer_id}: No email address available, skipping")
                continue
            
            # Parse expiry date
            id_expiry = datetime.strptime(id_expiry_str, '%Y-%m-%d').date()
            days_until_expiry = (id_expiry - today).days
            
            # Check if expired
            if days_until_expiry < 0:
                print(f"⚠️  {customer_id}: ID expired {abs(days_until_expiry)} days ago")
                send_email_notification(
                    target_email, 
                    customer_id, 
                    name, 
                    id_expiry_str, 
                    "expired"
                )
                notified_count += 1
            
            # Check if expiring within 30 days
            elif 0 <= days_until_expiry <= 30:
                print(f"🔔 {customer_id}: ID expires in {days_until_expiry} days")
                send_email_notification(
                    target_email, 
                    customer_id, 
                    name, 
                    id_expiry_str, 
                    "expiring_soon"
                )
                notified_count += 1
            else:
                print(f"✅ {customer_id}: ID valid for {days_until_expiry} days")
                
        except ValueError:
            print(f"⚠️  {customer_id}: Invalid date format: {id_expiry_str}")
            continue
    
    print(f"\n📧 Sent {notified_count} notification emails")
    return notified_count

def get_expired_customers():
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT customer_id, name, id_expiry, id_type FROM kyc_records WHERE id_expiry IS NOT NULL')
    records = c.fetchall()
    conn.close()
    
    today = datetime.now().date()
    expired = []
    expiring_soon = []
    
    for customer_id, name, id_expiry_str, id_type in records:
        try:
            id_expiry = datetime.strptime(id_expiry_str, '%Y-%m-%d').date()
            days_until_expiry = (id_expiry - today).days
            
            if days_until_expiry < 0:
                expired.append({
                    'customer_id': customer_id,
                    'name': name,
                    'id_type': id_type,
                    'id_expiry': id_expiry_str,
                    'days_expired': abs(days_until_expiry)
                })
            elif 0 <= days_until_expiry <= 30:
                expiring_soon.append({
                    'customer_id': customer_id,
                    'name': name,
                    'id_type': id_type,
                    'id_expiry': id_expiry_str,
                    'days_remaining': days_until_expiry
                })
        except ValueError:
            continue
    
    return expired, expiring_soon

def revalidate_all_records():
    """Re-validate all existing records to check for expired IDs"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT customer_id, id_expiry, status, validation_result, flags FROM kyc_records WHERE id_expiry IS NOT NULL')
    records = c.fetchall()
    
    today = datetime.now().date()
    updated_count = 0
    
    print(f"\n🔄 Re-validating {len(records)} records...")
    
    for customer_id, id_expiry_str, current_status, validation_json, flags_json in records:
        try:
            id_expiry = datetime.strptime(id_expiry_str, '%Y-%m-%d').date()
            days_until_expiry = (id_expiry - today).days
            
            # Check if expired but marked as APPROVED
            if days_until_expiry < 0 and current_status == 'APPROVED':
                days_expired = abs(days_until_expiry)
                
                # Update to REJECTED
                validation_result = json.loads(validation_json) if validation_json else {}
                flags = json.loads(flags_json) if flags_json else []
                
                # Add expiry flag
                expiry_flag = f"ID expired {days_expired} days ago on {id_expiry_str}"
                if expiry_flag not in flags:
                    flags.append(expiry_flag)
                
                # Update validation result
                validation_result['validation_status'] = 'REJECTED'
                validation_result['flags'] = flags
                validation_result['compliance_report'] = f"❌ REJECTED: ID expired {days_expired} days ago. " + validation_result.get('compliance_report', '')
                
                # Update database
                c.execute('''UPDATE kyc_records 
                            SET status = ?, validation_result = ?, flags = ?
                            WHERE customer_id = ?''',
                         ('REJECTED', json.dumps(validation_result), json.dumps(flags), customer_id))
                
                print(f"✅ Updated {customer_id}: APPROVED → REJECTED (expired {days_expired} days ago)")
                updated_count += 1
                
        except ValueError:
            continue
    
    conn.commit()
    conn.close()
    
    print(f"✅ Re-validation complete: {updated_count} records updated\n")
    return updated_count

if __name__ == "__main__":
    process_kyc_workflow()
    print("\n" + generate_compliance_report())
