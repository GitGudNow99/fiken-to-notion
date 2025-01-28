from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Fiken and Notion configuration
FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN")
COMPANY_SLUG = os.getenv("COMPANY_SLUG")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
LYNDB25_ID = os.getenv("LYNDB25_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

fiken_headers = {
    'Authorization': f'Bearer {FIKEN_API_TOKEN}',
    'Content-Type': 'application/json'
}

app = Flask(__name__)

# Fetch customers from Fiken
def fetch_fiken_customers():
    """
    Fetch all customers from Fiken API.
    """
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        response = requests.get(url, headers=fiken_headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching customers from Fiken: {e}")
        return []

# Create a new customer in Fiken
def create_fiken_customer(customer_name, email, organization_number=None):
    """
    Create a new customer in Fiken.
    """
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        payload = {
            "name": customer_name,
            "email": email,
            "type": "customer"
        }
        if organization_number:
            payload["organizationNumber"] = organization_number

        print("Creating customer in Fiken:", payload)
        response = requests.post(url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating customer in Fiken: {e}")
        return None

# Match or create a customer in Fiken
def get_or_create_fiken_customer(customers, customer_name, email, organization_number=None):
    """
    Match an existing customer by name or create a new one in Fiken.
    """
    for customer in customers:
        if customer["name"].lower() == customer_name.lower():
            print(f"Matched customer: {customer}")
            return customer

    print(f"No match found for customer '{customer_name}'. Creating a new customer.")
    return create_fiken_customer(customer_name, email, organization_number)

# Send draft invoice to Fiken
def send_to_fiken_draft(order_lines, customer_id, bank_account_code, project_manager, project_name):
    """
    Create a draft invoice in Fiken.
    """
    try:
        draft_url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/invoices/drafts"
        payload = {
            "type": "invoice",
            "issueDate": "2025-01-27",
            "daysUntilDueDate": 14,
            "customerId": customer_id,
            "lines": order_lines,
            "bankAccountCode": bank_account_code,
            "currency": "NOK",
            "cash": False,
            "ourReference": project_manager,
            "orderReference": project_name
        }
        print("Payload being sent to Fiken (draft):", payload)
        response = requests.post(draft_url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        print("Draft invoice successfully created in Fiken.")
    except requests.exceptions.RequestException as e:
        print(f"Error creating draft invoice in Fiken: {e}")
        if e.response is not None:
            print("Error Response Content:", e.response.text)

# Create draft invoice process
def create_draft_invoice(project_name, customer_name, email, organization_number=None):
    """
    Handle the process of creating a draft invoice.
    """
    customers = fetch_fiken_customers()
    if not customers:
        return {"error": "Failed to fetch customers from Fiken."}, 500

    matched_customer = get_or_create_fiken_customer(customers, customer_name, email, organization_number)
    if not matched_customer:
        return {"error": f"Failed to create or fetch customer '{customer_name}'."}, 500

    customer_id = matched_customer["contactId"]
    order_lines = [
        {
            "description": "Example item",
            "unitPrice": 50000,  # Price in øre (e.g., 500.00 NOK = 50000 øre)
            "vatType": "HIGH",
            "quantity": 2
        }
    ]

    send_to_fiken_draft(
        order_lines=order_lines,
        customer_id=customer_id,
        bank_account_code="1920:10001",
        project_manager="Maksymilian Lucow",
        project_name=project_name
    )

    return {"message": f"Draft invoice for project '{project_name}' created successfully."}, 200

# Webhook route
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle incoming webhook requests.
    """
    try:
        data = request.json
        project_name = data.get("project_name")
        customer_name = data.get("customer_name")
        email = data.get("email")
        organization_number = data.get("organization_number")

        if not project_name or not customer_name or not email:
            return jsonify({"error": "Project name, customer name, and email are required."}), 400

        result, status = create_draft_invoice(project_name, customer_name, email, organization_number)
        return jsonify(result), status
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
