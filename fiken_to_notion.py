import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import time
import sqlite3
import hashlib

# Load environment variables
load_dotenv()

FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN")
COMPANY_SLUG = os.getenv("COMPANY_SLUG")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# API headers
fiken_headers = {
    'Authorization': f'Bearer {FIKEN_API_TOKEN}',
    'Content-Type': 'application/json'
}

notion_headers = {
    'Authorization': f'Bearer {NOTION_API_TOKEN}',
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}

# Initialize or connect to SQLite database
def init_database():
    connection = sqlite3.connect("processed_transactions.db")
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_transactions (
            transaction_id TEXT PRIMARY KEY,
            transaction_hash TEXT NOT NULL
        )
    """)
    connection.commit()
    return connection

# Generate a hash for a transaction based on its ID and Formål
def generate_transaction_hash(purchase_id, formål):
    unique_string = f"{purchase_id}-{formål}"
    return hashlib.md5(unique_string.encode()).hexdigest()

# Save a transaction hash to the database
def save_processed_transaction(connection, transaction_id, transaction_hash):
    cursor = connection.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO processed_transactions (transaction_id, transaction_hash)
        VALUES (?, ?)
    """, (transaction_id, transaction_hash))
    connection.commit()

# Load all processed transaction hashes from the database
def load_processed_transaction_hashes(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT transaction_hash FROM processed_transactions")
    return set(row[0] for row in cursor.fetchall())

# Send Slack notification
def send_slack_message(message, retries=3):
    if not SLACK_WEBHOOK_URL:
        print("Slack Webhook URL is not set. Skipping Slack notification.")
        return

    payload = {"text": message}

    for attempt in range(retries):
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json=payload)
            if response.status_code == 200:
                print(f"Slack message sent: {message}")
                return
            else:
                print(f"Failed to send Slack message: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error sending Slack notification: {e}")
        time.sleep(5)

    print("Slack notification failed after retries.")

# Fetch existing transaction IDs from Notion
def fetch_existing_notion_entries():
    notion_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    existing_hashes = set()
    has_more = True
    next_cursor = None

    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        response = requests.post(notion_url, headers=notion_headers, json=payload)
        if response.status_code != 200:
            print(f"Failed to fetch existing Notion entries: {response.status_code} - {response.text}")
            response.raise_for_status()

        data = response.json()
        for result in data.get("results", []):
            try:
                transaction_id = result["properties"]["Navn"]["title"][0]["text"]["content"]
                formål = result["properties"]["Formål"]["rich_text"][0]["text"]["content"]
                transaction_hash = generate_transaction_hash(transaction_id, formål)
                existing_hashes.add(transaction_hash)
            except (KeyError, IndexError):
                print(f"Skipping malformed Notion entry: {result}")

        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    print(f"Fetched {len(existing_hashes)} existing transaction hashes from Notion.")
    return existing_hashes

# Fetch purchases from Fiken API
def fetch_fiken_purchases(from_date=None):
    url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/purchases"
    params = {}
    if from_date:
        params['fromDate'] = from_date

    purchases = []
    unique_ids = set()
    page = 0
    page_size = 100

    while True:
        params.update({'page': page, 'pageSize': page_size})
        response = requests.get(url, headers=fiken_headers, params=params)
        if response.status_code != 200:
            print(f"Failed to fetch purchases: {response.status_code} - {response.text}")
            response.raise_for_status()

        data = response.json()
        for purchase in data:
            purchase_id = purchase.get('identifier', purchase.get('purchaseId'))
            if purchase_id not in unique_ids:
                purchases.append(purchase)
                unique_ids.add(purchase_id)

        time.sleep(1)  # Throttle API requests
        page += 1
        if page >= int(response.headers.get('Fiken-Api-Page-Count', 0)):
            break

    print(f"Fetched {len(purchases)} purchases from Fiken.")
    return purchases

# Create a page in Notion
def create_notion_page(purchase):
    notion_url = "https://api.notion.com/v1/pages"
    lines = purchase.get('lines', [])
    if not lines:
        print(f"Skipping purchase without lines.")
        return

    total_amount = 0
    formatted_lines = []
    for line in lines:
        net_price = line.get('netPrice', 0) / 100
        vat = line.get('vat', 0) / 100
        total_amount += net_price + vat
        description = line.get('description', 'No description')
        formatted_lines.append(f"{description}: {net_price:.2f} NOK + {vat:.2f} NOK VAT")

    lines_description = "\n".join(formatted_lines)
    purchase_id = purchase.get('identifier', purchase.get('purchaseId', 'Unnamed Purchase'))
    supplier_name = purchase.get('supplier', {}).get('name', 'Unknown Supplier')
    purchase_date = purchase.get('date')

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Navn": {"title": [{"text": {"content": str(purchase_id)}}]},
            "Leverandør": {"rich_text": [{"text": {"content": supplier_name}}]},
            "Beløp ink. mva": {"number": total_amount},
            "Formål": {"rich_text": [{"text": {"content": lines_description}}]},
        }
    }

    if purchase_date:
        data["properties"]["Forfallsdato"] = {"date": {"start": purchase_date}}

    response = requests.post(notion_url, headers=notion_headers, json=data)
    if response.status_code != 200:
        print(f"Failed to create Notion page: {response.status_code} - {response.text}")
        response.raise_for_status()

# Main function
def sync_fiken_to_notion():
    try:
        # Initialize SQLite database
        connection = init_database()

        # Load processed transaction hashes from the database
        processed_hashes = load_processed_transaction_hashes(connection)

        # Fetch existing hashes from Notion
        existing_hashes = fetch_existing_notion_entries()

        # Fetch purchases from Fiken API
        purchases = fetch_fiken_purchases()
        synced_count = 0

        for purchase in purchases:
            purchase_id = purchase.get('identifier', purchase.get('purchaseId'))
            formål = "\n".join([line.get('description', 'No description') for line in purchase.get('lines', [])])
            transaction_hash = generate_transaction_hash(purchase_id, formål)

            # Skip if transaction exists in Notion or database
            if transaction_hash in processed_hashes or transaction_hash in existing_hashes:
                print(f"Skipping already processed transaction: {purchase_id}")
                continue

            # Sync to Notion
            create_notion_page(purchase)
            synced_count += 1

            # Save to local database
            save_processed_transaction(connection, purchase_id, transaction_hash)
            print(f"Synced and saved purchase: {purchase_id}")

        # Send Slack notification
        if synced_count > 0:
            send_slack_message(f":white_check_mark: Synkronisert {synced_count} nye transaksjoner til Notion!")
        else:
            send_slack_message(":heavy_check_mark: Ingen nye transaksjoner å synkronisere.")

    except Exception as e:
        send_slack_message(f":warning: En feil oppstod under synkronisering: {str(e)}")
        print(f"Error during sync: {e}")

if __name__ == "__main__":
    sync_fiken_to_notion()