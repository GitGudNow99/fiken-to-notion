from flask import Flask, request, jsonify
import requests
from notion_client import Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Fiken and Notion configuration
FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN")
COMPANY_SLUG = os.getenv("COMPANY_SLUG")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
LYNDB25_ID = os.getenv("LYNDB25_ID")
CUSTOMER_DB_ID = os.getenv("CUSTOMER_DB_ID")
TIMEFØRING_DB_ID = os.getenv("TIMEFØRING_DB_ID")
UTSTYRSLEIE_DB_ID = os.getenv("UTSTYRSLEIE_DB_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

fiken_headers = {
    'Authorization': f'Bearer {FIKEN_API_TOKEN}',
    'Content-Type': 'application/json'
}

notion = Client(auth=NOTION_API_TOKEN)
app = Flask(__name__)

# Helper function: Send Slack message
def send_slack_message(message):
    if not SLACK_WEBHOOK_URL:
        print("No Slack webhook URL configured.")
        return
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Slack message: {e}")

# Helper function: Fetch project details from Notion
def fetch_project_details_from_notion(project_name):
    try:
        response = notion.databases.query(
            database_id=LYNDB25_ID,
            filter={
                "property": "Navn",
                "title": {
                    "equals": project_name
                }
            }
        )
        if not response["results"]:
            raise ValueError(f"Project '{project_name}' not found in lyndb25 database.")

        project = response["results"][0]["properties"]
        return {
            "project_name": project.get("Navn", {}).get("title", [{}])[0].get("text", {}).get("content", "Unknown"),
            "project_manager": project.get("Prosjektleder", {}).get("people", [{}])[0].get("name", "Unknown"),
            "customer_id": (
                project.get("Kunde", {}).get("relation", [{}])[0].get("id", "Unknown")
                if project.get("Kunde", {}).get("relation", [])
                else "Unknown"
            ),
            "mva_rate": project.get("MVA", {}).get("select", {}).get("name", "25%")
        }
    except Exception as e:
        print(f"Error fetching project details: {e}")
        raise

# Helper function: Prepare draft invoice for Fiken
def send_to_fiken_draft(order_lines, customer_id, bank_account_code, project_manager, customer_project_manager, project_name):
    draft_url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/invoices/drafts"
    payload = {
        "type": "invoice",
        "issueDate": "2025-01-27",  # Replace with dynamic date if needed
        "daysUntilDueDate": 14,  # Invoice due in 14 days
        "customerId": customer_id,
        "lines": order_lines,
        "bankAccountCode": bank_account_code,
        "currency": "NOK",
        "cash": False,
        "ourReference": project_manager,
        "yourReference": customer_project_manager,
        "orderReference": project_name
    }
    print("Payload being sent to Fiken (draft):", payload)
    try:
        response = requests.post(draft_url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        print("Draft invoice successfully created in Fiken.")
        send_slack_message(f"✅ Draft invoice for project '{project_name}' created successfully.")
    except requests.exceptions.RequestException as e:
        error_message = f"❌ Failed to create draft invoice for project '{project_name}': {str(e)}"
        print(error_message)
        send_slack_message(error_message)

# Main route: Handle incoming webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        project_name = data.get("project_name")
        if not project_name:
            return jsonify({"error": "Project name not provided in the webhook payload."}), 400

        # Fetch project details
        project_details = fetch_project_details_from_notion(project_name)
        print("Fetched project details:", project_details)

        # Example order lines (replace with real logic to fetch from Notion or database)
        order_lines = [
            {
                "description": "Example item",
                "unitPrice": 50000,  # Price in øre (e.g., 500.00 NOK = 50000 øre)
                "vatType": "HIGH",  # Assuming HIGH VAT; adjust as necessary
                "quantity": 2
            }
        ]

        # Send to Fiken as a draft invoice
        send_to_fiken_draft(
            order_lines=order_lines,
            customer_id=project_details["customer_id"],
            bank_account_code="1920:10001",  # Replace with actual bank account code
            project_manager=project_details["project_manager"],
            customer_project_manager="Client Project Manager",  # Replace with actual data
            project_name=project_details["project_name"]
        )

        return jsonify({"message": f"Successfully processed project '{project_name}'."}), 200
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
