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
    """
    Send a message to Slack.
    """
    if not SLACK_WEBHOOK_URL:
        print("No Slack webhook URL configured.")
        return

    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Slack message: {e}")

# Helper function: Fetch project details
def fetch_project_details_from_notion(project_name):
    """
    Fetch specific project details from the lyndb25 Notion database.
    """
    try:
        print(f"Fetching project details for: {project_name}")
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

        project = response["results"][0]["properties"]

        return {
            "project_name": project.get("Navn", {}).get("title", [{}])[0].get("text", {}).get("content", "Unknown"),
            "project_manager": project.get("Prosjektleder", {}).get("people", [{}])[0].get("name", "Unknown"),
            "customer_id": (
                project.get("Kunde", {}).get("relation", [{}])[0].get("id", "Unknown")
                if project.get("Kunde", {}).get("relation", [])
                else "Unknown"
            ),
            "mva_rate": project.get("MVA", {}).get("select", {}).get("name", "25%")  # Handle select type correctly
        }
    except Exception as e:
        print(f"Error fetching project details: {e}")
        raise

# Main route: Handle incoming webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle incoming webhook requests from Notion.
    """
    try:
        data = request.json
        project_name = data.get("project_name")
        if not project_name:
            return jsonify({"error": "Project name not provided in the webhook payload."}), 400

        # Fetch project details
        project_details = fetch_project_details_from_notion(project_name)
        print("Fetched project details:", project_details)

        # Example response for successful processing
        return jsonify({"message": f"Successfully processed project '{project_name}'."}), 200
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
