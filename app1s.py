#standard library imports 
import os
import sys
import warnings
import logging

# Suppress ALL warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['PYTHONWARNINGS'] = 'ignore'
logging.getLogger('streamlit').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)


import streamlit as st
import sqlite3
import json
from datetime import datetime
from kyc_agent import (
    process_kyc_workflow, 
    generate_compliance_report, 
    init_database,
    check_and_notify_expired_ids,
    get_expired_customers,
    revalidate_all_records
)
from groq import Groq
from dotenv import load_dotenv

#streamlit warnings 
st.set_option('client.showErrorDetails', False)
st.set_option('client.toolbarMode', 'minimal')

load_dotenv()

# Initialize Groq with validation
api_key = os.getenv('GROQ_API_KEY')
if not api_key:
    st.error("⚠️ GROQ_API_KEY not found in .env file. Please add your API key.")
    st.info("Get a free Groq API key at: https://console.groq.com/")
    st.stop()
client = Groq(api_key=api_key)

st.set_page_config(page_title="KYC Compliance Agent", page_icon="🔐", layout="wide")

# Initialize database
init_database()

def get_db_connection():
    return sqlite3.connect('kyc_compliance.db')

#for querying the database via llm
def query_database(question: str) -> str:
    """Use LLM to query database based on natural language"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Get all records
        c.execute('SELECT * FROM kyc_records')
        records = c.fetchall()
        
        # Get logs
        c.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT 50')
        logs = c.fetchall()
        conn.close()
    except Exception as e:
        return f"❌ Database error: {e}"
    
    #prepare json data for llm prompts 
    data_summary = f"""
KYC Records in Database:
{json.dumps([{
    'customer_id': r[0], 'status': r[2], 'name': r[3], 'dob': r[4],
    'id_type': r[6], 'id_expiry': r[7], 'flags': json.loads(r[11]) if r[11] else []
} for r in records], indent=2)}

Recent Activity Logs:
{json.dumps([{'timestamp': l[1], 'customer_id': l[2], 'action': l[3]} for l in logs[:10]], indent=2)}
"""
    
    prompt = f"""You are a KYC compliance assistant. Answer the following question based on the database:

Question: {question}

Database Data:
{data_summary}

Provide a clear, concise answer. If asked to list customers, format them nicely. 
Include relevant details like customer IDs, status, and any flags."""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are a helpful KYC compliance assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=1500
    )
    
    return response.choices[0].message.content

# Sidebar
with st.sidebar:
    st.title("🔐 KYC Compliance Agent")
    st.markdown("---")
    
    if st.button("🔄 Process New KYC Emails", type="primary"):
        with st.spinner("Processing KYC emails..."):
            try:
                process_kyc_workflow()
                st.success("✅ Processing complete!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    if st.button("🔍 Re-validate All Records"):
        with st.spinner("Re-validating expired IDs..."):
            try:
                updated = revalidate_all_records()
                if updated > 0:
                    st.success(f"✅ Updated {updated} records with expired IDs!")
                else:
                    st.info("✅ All records are up to date!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    st.markdown("---")
    
    # Quick Stats
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM kyc_records')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM kyc_records WHERE status = "APPROVED"')
    approved = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM kyc_records WHERE status = "REJECTED"')
    rejected = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM kyc_records WHERE status = "HUMAN_REVIEW_NEEDED"')
    review = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM kyc_records WHERE customer_email IS NOT NULL')
    with_email = c.fetchone()[0]
    conn.close()
    
    st.metric("Total KYC Records", total)
    st.metric("✅ Approved", approved)
    st.metric("❌ Rejected", rejected)
    st.metric("⚠️ Needs Review", review)
    st.metric("📧 With Email", with_email)

# Main area
tab1, tab2, tab3 = st.tabs(["💬 AI Assistant", "📊 Dashboard", "📋 Records"])

with tab1:
    st.header("💬 Ask the KYC Assistant")
    st.markdown("Ask questions about KYC compliance, send notifications, or manage records.")
    
    # Example questions
    st.markdown("**Example commands:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Show expired IDs"):
            user_question = "Show me all customers with expired IDs"
        if st.button("Pending reviews"):
            user_question = "Which customers need human review?"
    with col2:
        if st.button("Check expiring soon"):
            user_question = "Show IDs expiring within 30 days"
        if st.button("Recent activity"):
            user_question = "What are the most recent KYC activities?"
    with col3:
        if st.button("Send notifications"):
            user_question = "Send expiry notifications to expired customers"
        if st.button("Compliance report"):
            user_question = "Generate a summary compliance report"
    
    # User input
    user_question = st.text_input("Your question:", placeholder="e.g., Send notification to customer 98765 or Show expired IDs")
    
    if user_question:
        # Check if it's a notification command
        if any(keyword in user_question.lower() for keyword in ['send notification', 'send email', 'notify', 'send reminder']):
            st.markdown("### 📧 Email Notification")
            
            # Get expired customers
            expired, expiring_soon = get_expired_customers()
            
            if expired or expiring_soon:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("🔴 Expired IDs", len(expired))
                with col2:
                    st.metric("🟡 Expiring Soon", len(expiring_soon))
                
                st.markdown("---")
                
                # Check if customers have saved emails
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM kyc_records WHERE id_expiry IS NOT NULL AND customer_email IS NOT NULL')
                has_saved_emails = c.fetchone()[0] > 0
                conn.close()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if has_saved_emails and st.button("📧 Send to Saved Emails (Auto)", type="primary"):
                        with st.spinner("Sending notifications to customer emails..."):
                            count = check_and_notify_expired_ids(use_saved_emails=True)
                            st.success(f"✅ Sent {count} notification emails to customer email addresses!")
                            
                            # Show what was sent
                            if expired:
                                st.write("**Expired IDs notified:**")
                                for c in expired:
                                    st.write(f"- {c['customer_id']} ({c['name']}): Expired {c['days_expired']} days ago")
                            if expiring_soon:
                                st.write("**Expiring soon notified:**")
                                for c in expiring_soon:
                                    st.write(f"- {c['customer_id']} ({c['name']}): Expires in {c['days_remaining']} days")
                
                with col2:
                    with st.expander("📝 Manual Email Override"):
                        notification_email = st.text_input(
                            "Enter test email address:",
                            placeholder="your-test@example.com",
                            key="notify_email",
                            help="For testing: all notifications will be sent to this email"
                        )
                        
                        if notification_email and st.button("📧 Send to Test Email"):
                            with st.spinner(f"Sending notifications to {notification_email}..."):
                                count = check_and_notify_expired_ids(notification_email)
                                st.success(f"✅ Sent {count} notification emails to {notification_email}!")
            else:
                st.success("🎉 No expired or expiring IDs found!")
        else:
            # Regular query
            with st.spinner("Thinking..."):
                answer = query_database(user_question)
                st.markdown("### 🤖 Answer:")
                st.markdown(answer)
                if 'query' in st.session_state:
                    del st.session_state.query

with tab2:
    st.header("📊 Compliance Dashboard")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM kyc_records')
    records = c.fetchall()
    conn.close()
    
    if records:
        # Status breakdown
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("✅ Approved")
            approved_list = [r for r in records if r[3] == 'APPROVED']
            for rec in approved_list:
                st.success(f"**{rec[0]}** - {rec[4] or 'N/A'}")
        
        with col2:
            st.subheader("⚠️ Needs Review")
            review_list = [r for r in records if r[3] == 'HUMAN_REVIEW_NEEDED']
            for rec in review_list:
                st.warning(f"**{rec[0]}** - {rec[4] or 'N/A'}")
                flags = json.loads(rec[12]) if rec[12] else []
                if flags:
                    st.caption(f"Flags: {', '.join(flags)}")
        
        with col3:
            st.subheader("❌ Rejected")
            rejected_list = [r for r in records if r[3] == 'REJECTED']
            for rec in rejected_list:
                st.error(f"**{rec[0]}** - {rec[4] or 'N/A'}")
    else:
        st.info("No KYC records found. Click 'Process New KYC Emails' to fetch and process emails.")

with tab3:
    st.header("📋 All KYC Records")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM kyc_records ORDER BY processed_at DESC')
    records = c.fetchall()
    conn.close()
    
    if records:
        for rec in records:
            # rec[0]=customer_id, rec[1]=customer_email, rec[2]=email_date, rec[3]=status, rec[4]=name
            with st.expander(f"**{rec[0]}** - {rec[4] or 'Unknown'} [{rec[3]}]"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Customer ID:** {rec[0]}")
                    if rec[1]:
                        st.write(f"**Email:** {rec[1]} 📧")
                    st.write(f"**Name:** {rec[4] or 'N/A'}")
                    st.write(f"**DOB:** {rec[5] or 'N/A'}")
                    st.write(f"**ID Type:** {rec[7] or 'N/A'}")
                    st.write(f"**ID Number:** {rec[6] or 'N/A'}")
                
                with col2:
                    st.write(f"**ID Expiry:** {rec[8] or 'N/A'}")
                    st.write(f"**Status:** {rec[3]}")
                    st.write(f"**Processed:** {rec[13]}")
                    flags = json.loads(rec[12]) if rec[12] else []
                    if flags:
                        st.write(f"**Flags:** {', '.join(flags)}")
                
                if rec[11]:
                    validation = json.loads(rec[11])
                    st.markdown("**Compliance Report:**")
                    st.info(validation.get('compliance_report', 'N/A'))
    else:
        st.info("No records to display.")
