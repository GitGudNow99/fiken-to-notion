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

# Helper functions
def send_slack_message(message):
    """
    Send a message to Slack.
    """
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Slack message: {e}")

def fetch_project_details_from_notion(project_name):
    """
    Fetch specific project details from the lyndb25 Notion database.
    """
    response = notion.databases.query(database_id=LYNDB25_ID, filter={
        "property": "Navn",
        "title": {
            "equals": project_name
        }
    })
    if not response["results"]:
        raise ValueError(f"Project '{project_name}' not found in lyndb25 database.")

    project = response["results"][0]["properties"]

    return {
        "project_name": project["Navn"]["title"][0]["text"]["content"],
        "project_manager": project["Prosjektleder"]["people"][0]["name"],
        "customer_id": project["Kunde"]["relation"][0]["id"],
        "mva_rate": project["MVA"]["number"] or 25  # Default to 25% if not provided
    }

def fetch_customer_details_from_notion(customer_id):
    """
    Fetch customer details from the Notion customer database.
    """
    response = notion.databases.query(database_id=CUSTOMER_DB_ID, filter={
        "property": "ID",
        "text": {
            "equals": customer_id
        }
    })
    if not response["results"]:
        raise ValueError(f"Customer '{customer_id}' not found in customer database.")

    customer = response["results"][0]["properties"]

    return {
        "name": customer["Kundenavn"]["title"][0]["text"]["content"],
        "organizationNumber": customer["Org.nr."]["number"],
        "email": customer["E-post"]["email"],
        "customer_project_manager": customer["Kontaktperson"]["people"][0]["name"]
    }

def fetch_entries_from_notion(database_id, project_name, entry_type):
    """
    Fetch entries (timeføring or utstyrsleie) from Notion for a specific project.
    """
    response = notion.databases.query(database_id=database_id, filter={
        "property": "Project",
        "relation": {
            "contains": project_name
        }
    })
    entries = []

    for item in response["results"]:
        properties = item["properties"]
        if entry_type == "timeføring":
            entries.append({
                "description": properties["Beskrivelse"]["title"][0]["text"]["content"],
                "unit_price": properties["Veil timespris"]["number"],
                "discount": properties["Rabatt (%)"]["number"] or 0,
                "quantity": properties["Timer"]["number"],
                "total_price": properties["Totalt"]["number"],
                "date": properties["Dato"]["date"]["start"]
            })
        elif entry_type == "utstyrsleie":
            entries.append({
                "description": properties["Utstyr"]["title"][0]["text"]["content"],
                "unit_price": properties["Pris (veil)"]["number"],
                "discount": properties["Rabatt"]["number"] or 0,
                "days_used": properties["Bruksdager"]["number"],
                "quantity": properties["Antall"]["number"]
            })

    return entries

def prepare_order_lines(time_entries, equipment_entries, mva_rate):
    """
    Prepare invoice order lines.
    """
    order_lines = []

    for entry in time_entries:
        if "unit_price" in entry and entry["unit_price"] > 0:
            net_price = entry["unit_price"] * (1 - (entry["discount"] / 100))
            order_lines.append({
                "description": entry["description"],
                "unitPrice": int(net_price * 100),  # Convert to cents
                "vatType": "HIGH",  # Assuming HIGH VAT; adjust as necessary
                "quantity": entry.get("quantity", 1)
            })

    for entry in equipment_entries:
        if "unit_price" in entry and entry["unit_price"] > 0:
            net_price = entry["unit_price"] * (1 - (entry["discount"] / 100))
            order_lines.append({
                "description": entry["description"],
                "unitPrice": int(net_price * 100),  # Convert to cents
                "vatType": "HIGH",  # Assuming HIGH VAT; adjust as necessary
                "quantity": entry.get("quantity", 1) * entry.get("days_used", 1)
            })

    return order_lines

def send_to_fiken_draft(order_lines, customer_id, bank_account_code, project_manager, customer_project_manager, project_name):
    """
    Send draft invoice to Fiken.
    """
    draft_url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/invoices/drafts"
    payload = {
        "type": "invoice",  # Type is required. Adjust if needed.
        "issueDate": "2025-01-27",
        "daysUntilDueDate": 14,  # Number of days after issueDate for dueDate
        "customerId": customer_id,
        "lines": order_lines,
        "bankAccountCode": bank_account_code,
        "currency": "NOK",
        "cash": False,
        "ourReference": project_manager,  # Name of project manager from lyndb25
        "yourReference": customer_project_manager,  # Name of customer's project manager
        "orderReference": project_name  # Name of the project
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

def handle_webhook(data):
    """
    Process webhook data and create a draft invoice.
    """
    project_name = data.get("project_name")
    if not project_name:
        raise ValueError("Project name not provided in the webhook payload.")

    mva_rate = 25
    bank_account_code = "1920:10001"

    # Fetch project details from lyndb25
    project_details = fetch_project_details_from_notion(project_name)

    # Fetch customer details
    customer_details = fetch_customer_details_from_notion(project_details["customer_id"])

    # Fetch timeføring and utstyrsleie entries
    time_entries = fetch_entries_from_notion(TIMEFØRING_DB_ID, project_details["project_name"], "timeføring")
    equipment_entries = fetch_entries_from_notion(UTSTYRSLEIE_DB_ID, project_details["project_name"], "utstyrsleie")

    # Prepare Fiken draft invoice
    customer_id = customer_details["organizationNumber"]
    project_manager = project_details["project_manager"]
    customer_project_manager = customer_details["customer_project_manager"]
    project_name = project_details["project_name"]

    order_lines = prepare_order_lines(time_entries, equipment_entries, mva_rate)
    send_to_fiken_draft(order_lines, customer_id, bank_account_code, project_manager, customer_project_manager, project_name)

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle incoming webhook requests from Notion.
    """
    try:
        data = request.json
        handle_webhook(data)
        return jsonify({"message": "Webhook processed successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)