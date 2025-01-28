from flask import Flask, request, jsonify
import requests
from notion_client import Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN")
COMPANY_SLUG = os.getenv("COMPANY_SLUG")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
LYNDB25_ID = os.getenv("LYNDB25_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

fiken_headers = {
    "Authorization": f"Bearer {FIKEN_API_TOKEN}",
    "Content-Type": "application/json",
}

# Initialize Flask and Notion Client
app = Flask(__name__)
notion = Client(auth=NOTION_API_TOKEN)

# Fetch customers from Fiken
def fetch_fiken_customers():
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        response = requests.get(url, headers=fiken_headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching customers from Fiken: {e}")
        return []

# Create a new customer in Fiken
def create_fiken_customer(name, email, org_number=None):
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        payload = {
            "name": name,
            "email": email,
            "customer": True,
        }
        if org_number:
            payload["organizationNumber"] = org_number
        response = requests.post(url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error creating customer in Fiken: {e}")
        return None

# Fetch project details from Notion
def fetch_project_details_from_notion(project_name):
    """
    Fetch project details from the Notion database.
    """
    try:
        print(f"Fetching details for project: {project_name}")

        # Correct filter for 'title' type
        response = notion.databases.query(
            database_id=LYNDB25_ID,
            filter={
                "property": "Navn",
                "title": {
                    "equals": project_name
                }
            }
        )
        print("Response from Notion API:", response)

        if not response["results"]:
            raise ValueError(f"Project '{project_name}' not found in lyndb25 database.")

        # Extract project details
        project = response["results"][0]["properties"]
        return {
            "project_name": project["Navn"]["title"][0]["text"]["content"],
            "project_manager": project["Prosjektleder"]["people"][0]["name"],
            "customer_id": project["Kunde"]["relation"][0]["id"],
            "mva_rate": int(project.get("MVA", {}).get("select", {}).get("name", "25%").replace("%", ""))
        }
    except Exception as e:
        print(f"Error fetching project details from Notion: {e}")
        raise

# Send draft invoice to Fiken
def send_to_fiken_draft(order_lines, customer_id, project_name, project_manager):
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/invoices/drafts"
        payload = {
            "type": "invoice",
            "issueDate": "2025-01-28",
            "daysUntilDueDate": 14,
            "customerId": customer_id,
            "lines": order_lines,
            "bankAccountCode": "1920:10001",
            "currency": "NOK",
            "cash": False,
            "ourReference": project_manager,
            "orderReference": project_name,
        }
        print("Payload being sent to Fiken (draft):", payload)
        response = requests.post(url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error creating draft invoice in Fiken: {e}")
        return None

# Webhook handler
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.json
    project_name = data.get("project_name")
    if not project_name:
        return jsonify({"error": "Project name is required."}), 400

    try:
        # Fetch project details from Notion
        project_details = fetch_project_details_from_notion(project_name)
        print("Fetched project details:", project_details)

        # Fetch customers from Fiken
        customers = fetch_fiken_customers()
        if not customers:
            return jsonify({"error": "Failed to fetch customers from Fiken."}), 500

        # Match or create customer
        customer = next(
            (cust for cust in customers if cust["id"] == project_details["customer_id"]), None
        )
        if not customer:
            customer = create_fiken_customer(
                name=project_details["project_name"],
                email="default@example.com",  # Replace with actual email if available
            )
        if not customer:
            return jsonify({"error": "Failed to create or fetch customer."}), 500

        # Prepare draft invoice payload
        order_lines = [
            {"description": "Example Item", "unitPrice": 50000, "vatType": "HIGH", "quantity": 2}
        ]
        invoice_response = send_to_fiken_draft(
            order_lines,
            customer["contactId"],
            project_details["project_name"],
            project_details["project_manager"],
        )
        if not invoice_response:
            return jsonify({"error": "Failed to create draft invoice."}), 500

        return jsonify({"message": f"Draft invoice for project '{project_name}' created successfully."}), 200
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
