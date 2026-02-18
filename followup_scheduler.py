"""
Daily Scheduler for PandaDoc Follow-up Workflow
Runs the follow-up workflow at scheduled times
"""

import schedule
import time
from datetime import datetime
import os
from dotenv import load_dotenv
from followup_workflow import run_followup_workflow

load_dotenv()

# Get scheduled time from environment or use default
FOLLOWUP_TIME = os.getenv("FOLLOWUP_TIME", "09:00")


def job():
    """Job to run the follow-up workflow"""
    print("\n" + "=" * 70)
    print(f"🕐 Scheduled Follow-up Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    try:
        run_followup_workflow()
    except Exception as e:
        print(f"\n❌ Error in scheduled job: {str(e)}")

    print("\n" + "=" * 70)
    print(f"✅ Scheduled job complete - Next run: Tomorrow at {FOLLOWUP_TIME}")
    print("=" * 70 + "\n")


def run_scheduler():
    """Run the scheduler loop"""
    print("📅 PandaDoc Follow-up Scheduler Starting")
    print("=" * 70)
    print(f"⏰ Scheduled time: {FOLLOWUP_TIME} daily")
    print(f"🖥️  Press Ctrl+C to stop")
    print("=" * 70 + "\n")

    # Schedule the job
    schedule.every().day.at(FOLLOWUP_TIME).do(job)

    # Also run immediately on first start (optional - comment out if not desired)
    print("🚀 Running initial follow-up check...")
    job()

    # Main loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n\n⏹️  Scheduler stopped by user")
            print("👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Scheduler error: {str(e)}")
            print("   Continuing...")
            time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
