import requests
import json
import pytd
import pandas as pd
from datetime import datetime
import os
import time

# === CONFIGURATION ===
YOTPO_CLIENT_SECRET = os.environ['YOTPO_CLIENT_SECRET']
YOTPO_STORE_ID = os.environ['YOTPO_STORE_ID']
YOTPO_BASE_URL = "https://api.yotpo.com/core/v3"

# TD_API_KEY = "${secret:td.apikey}"
TD_DATABASE = "raw_us_mavi"
TD_TABLE = "yotpo_customers"

MAX_RETRIES = 1
RETRY_DELAY_SEC = 2
BATCH_SIZE = 100_000


def get_access_token():
    url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/access_tokens"
    print(f"Requesting access token → {url}")
    res = requests.post(url, json={"secret": YOTPO_CLIENT_SECRET})
    res.raise_for_status()
    token = res.json()["access_token"]
    print("Access token received.")
    return token


def upload_to_treasure_data_pytd(customers):
    """Upload customers data to Treasure Data using pytd"""
    print(f"Uploading {len(customers)} records to Treasure Data")
    
    # Prepare data for upload
    records = []
    for c in customers:
        record = {
            "json_response": json.dumps(c, separators=(",", ":")),
            "time": int(datetime.utcnow().timestamp())
        }
        records.append(record)
    
    # Convert to DataFrame
    df = pd.DataFrame(records)
    
    # Initialize pytd client
    client = pytd.Client(
        apikey=TD_API_KEY,
        endpoint='https://api.treasuredata.com/',
        database=TD_DATABASE
    )
    
    # Upload data
    try:
        # Use load_table_from_dataframe for bulk import
        client.load_table_from_dataframe(
            df, 
            f"{TD_DATABASE}.{TD_TABLE}",
            if_exists='overwrite',
            writer='bulk_import'
        )
        print(f"Successfully uploaded {len(records)} records")
    except Exception as e:
        print(f"Upload failed: {e}")
        raise
    finally:
        client.close()


def fetch_and_ingest_paginated(token):
    page_info = None
    page_count = 0
    batch_count = 0
    buffer = []

    def flush_buffer():
        nonlocal buffer, batch_count
        if not buffer:
            return
        batch_count += 1
        print(f"Flushing batch {batch_count} with {len(buffer)} records")
        upload_to_treasure_data_pytd(buffer)
        buffer.clear()

    while True:
        if page_info:
            url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/customers?page_info={page_info}&include_custom_properties=true"
        else:
            url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/customers?limit=100&include_custom_properties=true"

        headers = {
            "accept": "application/json",
            "X-Yotpo-Token": token
        }

        print(f"Fetching page {page_count + 1} → {url}")

        for attempt in range(MAX_RETRIES + 1):
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                break
            if response.status_code == 400 and "no results found" in response.text.lower():
                print("No results found — stopping pagination.")
                flush_buffer()
                return
            print(f"Retry {attempt + 1}/{MAX_RETRIES} after error: {response.status_code}")
            time.sleep(RETRY_DELAY_SEC)
        else:
            print(f"Failed after retries: {response.text}")
            break

        data = response.json()
        customers = data.get("customers", [])
        next_page_info = data.get("pagination", {}).get("next_page_info")

        if not customers:
            print("No customers in this batch.")
            flush_buffer()
            break

        buffer.extend(customers)

        if len(buffer) >= BATCH_SIZE:
            flush_buffer()

        page_info = next_page_info
        page_count += 1

        if not page_info:
            break
        time.sleep(1)

    flush_buffer()
    print(f"Completed ingestion of {page_count} page(s), across {batch_count} bulk batches.")


def main():
    try:
        print("Script started via Digdag py> call")
        token = get_access_token()
        fetch_and_ingest_paginated(token)
    except Exception as e:
        print(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()