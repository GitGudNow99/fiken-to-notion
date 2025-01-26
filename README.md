# Fiken to Notion integration

This script integrates Fiken expenses with a Notion database by automatically syncing purchase data. Processed transactions are stored in a SQLite database for better scalability and reliability.

## Prerequisites

1. **Python**:
   - Python 3.8 or higher installed.
   - Install required libraries:
     ```sh
     pip install -r requirements.txt
     ```

2. **Environment file**:
   - Set up a `.env` file with your credentials.

## .env file configuration

Add your database and API credentials to a `.env` file:

```plaintext
FIKEN_API_TOKEN=your_fiken_api_token
COMPANY_SLUG=your_company_slug
NOTION_API_TOKEN=your_notion_api_token
DATABASE_ID=your_notion_database_id
SLACK_WEBHOOK_URL=your_slack_webhook_url  # Optional: for Slack notifications
```

## Setting up the Notion database

To integrate with Notion, you need to create a database in Notion with the following fields. Note that these fields are examples, and you can customize them as needed:

1. **Navn** (Title): This field will store the transaction ID.
2. **Leverandør** (Rich Text): This field will store the supplier name.
3. **Beløp ink. mva** (Number): This field will store the total amount including VAT.
4. **Formål** (Rich Text): This field will store the description of the purchase lines.
5. **Forfallsdato** (Date): This field will store the purchase date.

To create the database:
1. Open Notion and create a new database.
2. Add the fields mentioned above with the appropriate types.
3. Copy the database ID from the URL of your Notion database and add it to your `.env` file as `DATABASE_ID`.

## Running the script

1. Navigate to the script folder:
   ```sh
   cd /path/to/FikenToNotion
   ```

2. Run the script:
   ```sh
   python fiken_to_notion.py
   ```

## Setting up a service on Ubuntu

To run the script as a service on an Ubuntu server, follow these steps:

1. Create a service file:
   ```sh
   sudo nano /etc/systemd/system/fiken_to_notion.service
   ```

2. Add the following content to the service file:
   ```ini
   [Unit]
   Description=Fiken to Notion Integration Service
   After=network.target

   [Service]
   User=your_username
   WorkingDirectory=/path/to/FikenToNotion
   ExecStart=/usr/bin/python3 /path/to/FikenToNotion/polling.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. Reload the systemd manager configuration:
   ```sh
   sudo systemctl daemon-reload
   ```

4. Enable the service to start on boot:
   ```sh
   sudo systemctl enable fiken_to_notion.service
   ```

5. Start the service:
   ```sh
   sudo systemctl start fiken_to_notion.service
   ```

6. Check the status of the service:
   ```sh
   sudo systemctl status fiken_to_notion.service
   ```

## Handling Fiken API throttling

Fiken API has throttling limits to prevent abuse. The script handles this by adding a delay between API requests. Specifically, it waits for 1 second between each page of results when fetching purchases from Fiken. This helps to avoid hitting the rate limits imposed by Fiken.

## Avoiding duplicates with SQLite

Using Notion as the single source of truth can lead to duplicates if transactions are reprocessed. To avoid this, the script uses a SQLite database to keep track of processed transactions. Each transaction is hashed and stored in the database. Before syncing a transaction to Notion, the script checks if the transaction hash already exists in the SQLite database or in Notion. If it does, the transaction is skipped.

## Optional: Slack notifications

To receive notifications on Slack about the sync status, set up a Slack webhook and add the URL to your `.env` file as `SLACK_WEBHOOK_URL`. The script will send notifications for successful syncs and errors.

### Configuring Slack webhook

1. Go to the [Slack API: Incoming Webhooks](https://api.slack.com/messaging/webhooks) page.
2. Click on "Create a Slack App".
3. Follow the instructions to create a new app and add an Incoming Webhook to a channel.
4. Copy the webhook URL provided by Slack and add it to your `.env` file as `SLACK_WEBHOOK_URL`.

For detailed instructions, refer to the [Slack Incoming Webhooks documentation](https://api.slack.com/messaging/webhooks).

## Customizing the script

### For beginners

1. **Change the sync interval**:
   - In `polling.py`, you can change the interval at which the script checks for new transactions by modifying the line:
     ```python
     schedule.every(180).minutes.do(check_for_new_transactions)
     ```
     For example, to check every hour, change it to:
     ```python
     schedule.every().hour.do(check_for_new_transactions)
     ```

2. **Modify the Notion page properties**:
   - In `fiken_to_notion.py`, you can customize the properties of the Notion page created for each transaction. Look for the `create_notion_page` function and modify the `data` dictionary to include any additional properties you need.

3. **Add more fields to the database**:
   - If you want to store more information in the SQLite database, modify the `init_database` function in `fiken_to_notion.py` to add new columns to the `processed_transactions` table. Also, update the `save_processed_transaction` function to save the new data.

4. **Handle different API responses**:
   - If the Fiken API or Notion API responses change, you may need to update the functions that parse these responses. Look for the `fetch_fiken_purchases` and `fetch_existing_notion_entries` functions in `fiken_to_notion.py` and adjust the parsing logic as needed.

## Secure your credentials

- Do not share your `.env` file publicly. Add `.env` to your `.gitignore` file to exclude it from version control.

## Troubleshooting

### Common issues:

1. **API connection error**:
   - Ensure your API tokens are correct and the APIs are accessible.
   - Verify the `COMPANY_SLUG` and other settings in the `.env` file.

2. **Python dependency errors**:
   - Run `pip install -r requirements.txt` to install all required dependencies.

3. **Missing environment variables**:
   - Double-check your `.env` file is properly configured.

## Additional resources

- Notion API Documentation: https://developers.notion.com/
- Fiken API Documentation: https://fiken.no/api