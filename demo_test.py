"""
Demo/Test script for KYC Compliance Agent
This creates sample data to test the system without needing real emails
"""
import sqlite3
import json
from datetime import datetime, timedelta
from kyc_agent import init_database, update_temp_db, generate_compliance_report

def create_sample_data():
    """Create sample KYC records for testing"""
    init_database()
    
    print("🧪 Creating sample KYC test data...\n")
    
    # Sample 1: Approved KYC
    sample1 = {
        "validation_status": "APPROVED",
        "name": "John Doe",
        "dob": "1990-05-15",
        "id_type": "passport",
        "id_number": "P12345678",
        "id_expiry": "2027-05-15",
        "address": "123 Main Street, Dubai, UAE",
        "flags": [],
        "compliance_report": "All documents are valid and match. ID is not expired. Address proof is recent.",
        "missing_documents": [],
        "data_consistency": "All data is consistent across documents"
    }
    update_temp_db("CUST001", datetime.now().isoformat(), sample1, 
                   ["passport.pdf", "address_proof.pdf", "photo.jpg"])
    print("✅ Created CUST001 - Approved")
    
    # Sample 2: Expired ID
    sample2 = {
        "validation_status": "REJECTED",
        "name": "Jane Smith",
        "dob": "1985-08-20",
        "id_type": "emirates_id",
        "id_number": "784-1985-1234567-1",
        "id_expiry": "2023-08-20",  # Expired
        "address": "456 Palm Street, Abu Dhabi, UAE",
        "flags": ["ID expired", "Requires renewal"],
        "compliance_report": "Emirates ID has expired on 2023-08-20. Customer must renew ID before KYC can be approved.",
        "missing_documents": [],
        "data_consistency": "Data matches across documents"
    }
    update_temp_db("CUST002", datetime.now().isoformat(), sample2,
                   ["emirates_id.jpg", "utility_bill.pdf"])
    print("❌ Created CUST002 - Rejected (Expired ID)")
    
    # Sample 3: Human review needed
    sample3 = {
        "validation_status": "HUMAN_REVIEW_NEEDED",
        "name": "Ahmed Hassan",
        "dob": "1992-12-10",
        "id_type": "passport",
        "id_number": "A9876543",
        "id_expiry": "2026-12-10",
        "address": "Partial address visible",
        "flags": ["Document quality poor", "Address proof unclear", "Name spelling mismatch"],
        "compliance_report": "Passport image quality is poor making some details difficult to read. Address proof document is unclear. Name on passport shows 'Ahmed Hasan' but address proof shows 'Ahmad Hassan'. Human verification required.",
        "missing_documents": ["Photo ID"],
        "data_consistency": "Inconsistencies detected in name spelling"
    }
    update_temp_db("CUST003", datetime.now().isoformat(), sample3,
                   ["passport_blurry.jpg", "address_unclear.pdf"])
    print("⚠️  Created CUST003 - Human Review Needed")
    
    # Sample 4: Missing documents
    sample4 = {
        "validation_status": "HUMAN_REVIEW_NEEDED",
        "name": "Sarah Johnson",
        "dob": "1988-03-25",
        "id_type": "pan_card",
        "id_number": "ABCDE1234F",
        "id_expiry": "N/A",
        "address": "Not provided",
        "flags": ["Missing address proof", "Missing photo", "Incomplete submission"],
        "compliance_report": "Only PAN card was submitted. Missing required documents: address proof and photograph. KYC cannot be completed.",
        "missing_documents": ["Address proof", "Photograph"],
        "data_consistency": "Insufficient documents to verify consistency"
    }
    update_temp_db("CUST004", datetime.now().isoformat(), sample4,
                   ["pan_card.jpg"])
    print("⚠️  Created CUST004 - Missing Documents")
    
    # Sample 5: Another approved
    sample5 = {
        "validation_status": "APPROVED",
        "name": "Mohammed Ali",
        "dob": "1995-07-18",
        "id_type": "passport",
        "id_number": "K5566778",
        "id_expiry": "2028-07-18",
        "address": "789 Beach Road, Sharjah, UAE",
        "flags": [],
        "compliance_report": "All documents verified successfully. Passport is valid. Address proof is recent (dated within 3 months). All information matches across documents.",
        "missing_documents": [],
        "data_consistency": "Perfect match across all documents"
    }
    update_temp_db("CUST005", datetime.now().isoformat(), sample5,
                   ["passport.pdf", "utility_bill.pdf", "photo.jpg"])
    print("✅ Created CUST005 - Approved")
    
    print("\n" + "="*60)
    print(generate_compliance_report())
    print("="*60)
    print("\n🎉 Sample data created successfully!")
    print("\nNext steps:")
    print("1. Run: streamlit run app.py")
    print("2. Try asking questions like:")
    print("   - 'Show me customers with expired IDs'")
    print("   - 'Which KYCs need human review?'")
    print("   - 'List all approved customers'")
    print("   - 'What documents are missing for pending KYCs?'")

if __name__ == "__main__":
    create_sample_data()
