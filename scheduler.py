
import schedule
import time
from kyc_agent import process_kyc_workflow, generate_compliance_report
from datetime import datetime

def scheduled_task():
    print(f"\n{'='*60}")
    print(f"🕐 Scheduled KYC Processing - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    try:
        process_kyc_workflow()
        print("\n" + generate_compliance_report())
    except Exception as e:
        print(f"❌ Error during scheduled processing: {str(e)}")

# Schedule the task every 30 minutes
schedule.every(30).minutes.do(scheduled_task)

print("🤖 KYC Compliance Agent Scheduler Started")
print("⏰ Running KYC processing every 30 minutes")
print("Press Ctrl+C to stop\n")

# Run once immediately
scheduled_task()

# Keep running
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute
