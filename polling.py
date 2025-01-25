import os
import schedule
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fiken_to_notion import fetch_fiken_purchases, sync_fiken_to_notion

# Load environment variables
load_dotenv()

FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN")
COMPANY_SLUG = os.getenv("COMPANY_SLUG")

# Last sync time
last_sync_time = datetime.now() - timedelta(days=1)  # Example: start 1 day in the past

def check_for_new_transactions():
    global last_sync_time
    print(f"Checking for new transactions since {last_sync_time.isoformat()}...")

    try:
        # Fetch purchases from Fiken API
        purchases = fetch_fiken_purchases(from_date=last_sync_time.isoformat().split('T')[0])
        if purchases:
            print(f"Found {len(purchases)} new transactions.")
            sync_fiken_to_notion()  # Trigger the sync
        else:
            print("No new transactions found.")
    except Exception as e:
        print(f"Error during polling: {e}")

    # Update the last sync time to now
    last_sync_time = datetime.now()

# Schedule the polling task
schedule.every(180).minutes.do(check_for_new_transactions)

if __name__ == "__main__":
    print("Listening for new transactions...")
    while True:
        schedule.run_pending()
        time.sleep(1)
