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
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

fiken_headers = {
    'Authorization': f'Bearer {FIKEN_API_TOKEN}',
    'Content-Type': 'application/json'
}

notion = Client(auth=NOTION_API_TOKEN)
app = Flask(__name__)

# Helper function: Fetch customers from Fiken
def fetch_fiken_customers():
    """
    Fetch all customers from Fiken API.
    """
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        response = requests.get(url, headers=fiken_headers)
        response.raise_for_status()
        customers = response.json()
        print("Fetched customers from Fiken:", customers)
        return customers
    except requests.exceptions.RequestException as e:
        print(f"Error fetching customers from Fiken: {e}")
        return []

# Helper function: Create a new customer in Fiken
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
        print("Fiken API Response Status Code:", response.status_code)
        print("Fiken API Response Content:", response.text)
        response.raise_for_status()
        customer = response.json()
        print("Created customer in Fiken:", customer)
        return customer
    except requests.exceptions.RequestException as e:
        print(f"Error creating customer in Fiken: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print("Error Response Content:", e.response.text)
        return None
# Helper function: Match or create a customer
def get_or_create_fiken_customer(customers, customer_name, email, organization_number=None):
    """
    Match an existing customer or create a new one in Fiken.
    """
    for customer in customers:
        if customer["name"].lower() == customer_name.lower():
            print(f"Matched customer: {customer}")
            return customer

    print(f"No match found for customer '{customer_name}'. Creating a new customer.")
    new_customer = create_fiken_customer(customer_name, email, organization_number)
    return new_customer

# Helper function: Send draft invoice to Fiken
def send_to_fiken_draft(order_lines, customer_id, bank_account_code, project_manager, project_name):
    """
    Create a draft invoice in Fiken.
    """
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
    try:
        response = requests.post(draft_url, headers=fiken_headers, json=payload)
        response.raise_for_status()
        print("Draft invoice successfully created in Fiken.")
    except requests.exceptions.RequestException as e:
        print(f"Error creating draft invoice in Fiken: {e}")
        if e.response is not None:
            print("Response content:", e.response.text)

# Main function: Handle the full process
def create_draft_invoice(project_name, customer_name, email, organization_number=None):
    """
    Handle the process of creating a draft invoice.
    """
    # Fetch customers from Fiken
    customers = fetch_fiken_customers()
    if not customers:
        return {"error": "Failed to fetch customers from Fiken."}, 500

    # Match or create the customer
    matched_customer = get_or_create_fiken_customer(customers, customer_name, email, organization_number)
    if not matched_customer:
        return {"error": f"Failed to create or fetch customer '{customer_name}'."}, 500

    # Prepare the invoice payload
    customer_id = matched_customer["id"]
    order_lines = [
        {
            "description": "Example item",
            "unitPrice": 50000,  # Price in øre (e.g., 500.00 NOK = 50000 øre)
            "vatType": "HIGH",
            "quantity": 2
        }
    ]

    # Send the draft invoice to Fiken
    send_to_fiken_draft(
        order_lines=order_lines,
        customer_id=customer_id,
        bank_account_code="1920:10001",
        project_manager="Maksymilian Lucow",  # Replace with project manager's name dynamically
        project_name=project_name
    )

    return {"message": f"Draft invoice for project '{project_name}' created successfully."}, 200

# Flask route: Handle incoming webhook
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

        # Process draft invoice creation
        result, status = create_draft_invoice(project_name, customer_name, email, organization_number)
        return jsonify(result), status
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
