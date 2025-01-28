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
CUSTOMER_DB_ID = os.getenv("CUSTOMER_DB_ID")  # Notion Customer Database ID
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
def create_fiken_customer(name, email="default@example.com", org_number=None):
    """
    Create a new customer in Fiken and return the response.
    """
    try:
        url = f"https://api.fiken.no/api/v2/companies/{COMPANY_SLUG}/contacts"
        payload = {
            "name": name,
            "email": email,
            "customer": True,
        }
        if org_number:
            payload["organizationNumber"] = org_number

        print("Payload being sent to Fiken:", payload)  # Debug the payload

        response = requests.post(url, headers=fiken_headers, json=payload)

        # Check if the response is successful
        if response.status_code == 201:
            print("Customer created successfully in Fiken.")
            response_json = response.json()
            print("Response from Fiken:", response_json)

            # Check if the response contains contactId
            if "contactId" in response_json:
                return response_json  # Return the customer data with contactId
            else:
                print("Error: contactId not found in Fiken response.")
                return None
        else:
            print(f"Error from Fiken API: {response.status_code}, {response.text}")
            return None

    except requests.RequestException as e:
        print(f"Error creating customer in Fiken: {e}")
        return None

# Update Notion with contactId
def update_notion_customer(contact_id, notion_id):
    try:
        notion.pages.update(
            page_id=notion_id,
            properties={
                "contactId": {"number": contact_id}  # Assuming 'contactId' is a number property in Notion
            },
        )
        print(f"Updated Notion customer {notion_id} with contactId: {contact_id}")
    except Exception as e:
        print(f"Error updating Notion customer: {e}")

# Fetch customer from Notion by name
def fetch_customer_from_notion(customer_name):
    try:
        response = notion.databases.query(
            database_id=CUSTOMER_DB_ID,
            filter={
                "property": "Name",  # Adjust to match your Notion property name
                "title": {
                    "equals": customer_name
                }
            }
        )
        if response["results"]:
            return response["results"][0]
        return None
    except Exception as e:
        print(f"Error fetching customer from Notion: {e}")
        return None

# Match or create a customer in Fiken
def get_or_create_fiken_customer(customers, customer_name, email="default@example.com", org_number=None):
    for customer in customers:
        if customer["name"].lower() == customer_name.lower() or customer.get("email") == email:
            print(f"Matched customer in Fiken: {customer}")
            return customer

    # Create a new customer if no match is found
    print(f"No match found for customer '{customer_name}'. Creating a new customer.")
    new_customer = create_fiken_customer(name=customer_name, email=email, org_number=org_number)
    if new_customer:
        # If customer created successfully, update Notion with the new contactId
        notion_customer = fetch_customer_from_notion(customer_name)
        if notion_customer:
            update_notion_customer(new_customer["contactId"], notion_customer["id"])
    return new_customer

# Fetch project details from Notion
def fetch_project_details_from_notion(project_name):
    try:
        print(f"Fetching details for project: {project_name}")
        response = notion.databases.query(
            database_id=LYNDB25_ID,
            filter={
                "property": "Navn",  # Replace with your actual property name
                "title": {
                    "equals": project_name
                }
            }
        )
        print("Response from Notion API:", response)

        if not response["results"]:
            raise ValueError(f"Project '{project_name}' not found in lyndb25 database.")

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
            "customerId": customer_id,  # Use customerId (numeric)
            "lines": order_lines,
            "bankAccountCode": "1920:10001",
            "currency": "NOK",
            "cash": False,
            "ourReference": project_manager,
            "orderReference": project_name,
        }

        print("Payload being sent to Fiken (draft):", payload)  # Debug the payload

        response = requests.post(url, headers=fiken_headers, json=payload)

        # Check if the response is successful
        if response.status_code != 201:
            print(f"Error from Fiken API: {response.status_code}, {response.text}")
            return None

        print("Draft invoice created successfully:", response.json())
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

        # Match or create customer in Fiken
        customer = get_or_create_fiken_customer(
            customers=customers,
            customer_name=project_details["project_manager"],
            email="default@example.com"
        )
        if not customer:
            return jsonify({"error": "Failed to create or fetch customer."}), 500

        # Prepare draft invoice payload
        order_lines = [
            {"description": "Example Item", "unitPrice": 50000, "vatType": "HIGH", "quantity": 2}
        ]
        invoice_response = send_to_fiken_draft(
            order_lines=order_lines,
            customer_id=customer["contactId"],  # Use numeric contactId
            project_name=project_details["project_name"],
            project_manager=project_details["project_manager"],
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
