import requests
import json
import pytd
import pandas as pd
from datetime import datetime
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# === CONFIGURATION ===
YOTPO_CLIENT_SECRET = os.environ['YOTPO_CLIENT_SECRET']
YOTPO_STORE_ID = os.environ['YOTPO_STORE_ID']
YOTPO_BASE_URL = "https://api.yotpo.com/core/v3"

TD_API_KEY = os.environ['TD_API_KEY']
TD_DATABASE = "raw_us_mavi"
TD_TABLE = "yotpo_customers"

# Performance settings
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2
BATCH_SIZE = 100_000
REQUEST_TIMEOUT = 30
REQUESTS_PER_SECOND = 4.5  # Stay under 5 req/sec limit

# Threading settings
UPLOAD_WORKERS = 2  # Number of parallel uploads to TD

# Rate limiting variables
last_request_time = 0
rate_limit_lock = threading.Lock()


def rate_limit_wait():
    """Simple rate limiter - ensures we don't exceed requests per second"""
    global last_request_time
    min_interval = 1.0 / REQUESTS_PER_SECOND
    
    with rate_limit_lock:
        now = time.time()
        time_since_last = now - last_request_time
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        last_request_time = time.time()


def get_access_token():
    """Get access token"""
    url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/access_tokens"
    print(f"Requesting access token → {url}")
    
    try:
        res = requests.post(url, json={"secret": YOTPO_CLIENT_SECRET}, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        token = res.json()["access_token"]
        print("Access token received.")
        return token
    except requests.exceptions.RequestException as e:
        print(f"Failed to get access token: {e}")
        raise


def upload_batch_to_td(customers, batch_num):
    """Upload a batch of customers to Treasure Data"""
    print(f"[Upload] Starting batch {batch_num} with {len(customers)} records")
    
    records = []
    for c in customers:
        record = {
            "json_response": json.dumps(c, separators=(",", ":")),
            "time": int(datetime.utcnow().timestamp())
        }
        records.append(record)
    
    df = pd.DataFrame(records)
    
    client = pytd.Client(
        apikey=TD_API_KEY,
        endpoint='https://api.treasuredata.com/',
        database=TD_DATABASE
    )
    
    try:
        client.load_table_from_dataframe(
            df, 
            f"{TD_DATABASE}.{TD_TABLE}",
            if_exists='append',
            writer='bulk_import'
        )
        print(f"[Upload] Completed batch {batch_num}")
        return True
    except Exception as e:
        print(f"[Upload] Failed batch {batch_num}: {e}")
        raise
    finally:
        client.close()


def fetch_page_with_retry(url, headers):
    """Fetch a single page with retry logic"""
    for attempt in range(MAX_RETRIES + 1):
        # Rate limiting
        rate_limit_wait()
        
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                # Check if response is JSON
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    print(f"WARNING: Non-JSON response (attempt {attempt + 1})")
                    print(f"Content-Type: {content_type}")
                    print(f"Response preview: {response.text[:500]}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                        continue
                    return None
                
                # Check response size
                response_size = len(response.text)
                if response_size > 1000000:  # 1MB
                    print(f"WARNING: Large response size: {response_size} bytes")
                
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    print(f"JSON decode error on attempt {attempt + 1}: {e}")
                    print(f"Error type: {type(e).__name__}")
                    print(f"Response size: {len(response.text)} bytes")
                    
                    # More detailed error analysis
                    error_pos = getattr(e, 'pos', -1)
                    if error_pos > 0:
                        # Show context around error
                        start = max(0, error_pos - 100)
                        end = min(len(response.text), error_pos + 100)
                        print(f"Context around position {error_pos}:")
                        print(f"...{repr(response.text[start:end])}...")
                    else:
                        # Show beginning and end of response
                        print(f"Response start: {repr(response.text[:200])}")
                        print(f"Response end: {repr(response.text[-200:])}")
                    
                    # Check for common issues
                    if response.text.strip().startswith('<'):
                        print("ERROR: Response appears to be HTML/XML instead of JSON")
                    elif 'rate limit' in response.text.lower():
                        print("ERROR: Possible rate limit message in response")
                    elif response.text.strip() == '':
                        print("ERROR: Empty response body")
                    elif error_pos > 0 and error_pos == len(response.text) - 1:
                        print("ERROR: Response appears to be truncated")
                    
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                        continue
                    return None
                    
            elif response.status_code == 400 and "no results found" in response.text.lower():
                return {"customers": [], "pagination": {}}
                
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', RETRY_DELAY_SEC * 2))
                print(f"Rate limit hit, waiting {retry_after} seconds")
                time.sleep(retry_after)
                continue
                
            else:
                print(f"HTTP {response.status_code} (attempt {attempt + 1})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                    continue
                    
        except requests.exceptions.Timeout:
            print(f"Request timeout (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e} (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                continue
    
    print(f"Failed after {MAX_RETRIES + 1} attempts")
    return None


def fetch_and_ingest_parallel(token):
    """Main function to fetch pages and upload in parallel"""
    # Setup thread pool for uploads
    upload_executor = ThreadPoolExecutor(max_workers=UPLOAD_WORKERS)
    upload_futures = []
    
    # Data tracking
    page_count = 0
    batch_count = 0
    total_customers = 0
    customer_buffer = []
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    # API headers
    headers = {
        "accept": "application/json",
        "X-Yotpo-Token": token
    }
    
    # Start fetching pages
    page_info = None
    
    try:
        while True:
            # Build URL
            if page_info:
                url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/customers?page_info={page_info}&include_custom_properties=true&expand=loyalty"
            else:
                url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/customers?limit=100&include_custom_properties=true&expand=loyalty"
            
            print(f"Fetching page {page_count + 1}")
            
            # Fetch page
            data = fetch_page_with_retry(url, headers)
            
            if not data:
                consecutive_errors += 1
                print(f"Failed to fetch page (consecutive errors: {consecutive_errors})")
                
                if consecutive_errors >= max_consecutive_errors:
                    print(f"Too many consecutive errors ({consecutive_errors}), stopping fetch")
                    break
                
                # Try to continue with next page if possible
                if page_info:
                    print("WARNING: Skipping failed page, data may be incomplete")
                    # This is a workaround - we don't know the next page_info
                    # so we'll stop here to avoid infinite loop
                    break
                else:
                    print("Failed on first page, cannot continue")
                    break
            else:
                consecutive_errors = 0  # Reset on success
            
            # Extract data
            customers = data.get("customers", [])
            next_page_info = data.get("pagination", {}).get("next_page_info")
            
            if not customers:
                print("No customers in response")
                break
                
            # Add to buffer
            customer_buffer.extend(customers)
            page_count += 1
            total_customers += len(customers)
            print(f"Page {page_count}: {len(customers)} customers (Total: {total_customers})")
            
            # Check if we need to upload a batch
            while len(customer_buffer) >= BATCH_SIZE:
                batch_count += 1
                batch_data = customer_buffer[:BATCH_SIZE]
                customer_buffer = customer_buffer[BATCH_SIZE:]
                
                # Submit upload in background
                print(f"Submitting batch {batch_count} for upload")
                future = upload_executor.submit(upload_batch_to_td, batch_data, batch_count)
                upload_futures.append(future)
                
                # Clean up completed uploads
                upload_futures = [f for f in upload_futures if not f.done()]
                
                # If too many uploads queued, wait for one to complete
                if len(upload_futures) >= 3:
                    print(f"Upload queue full ({len(upload_futures)}), waiting...")
                    # Wait for at least one to complete
                    for future in as_completed(upload_futures):
                        future.result()  # This will raise exception if upload failed
                        upload_futures.remove(future)
                        break
            
            # Check for next page
            if not next_page_info:
                print("No more pages")
                break
                
            page_info = next_page_info
            
        # Upload any remaining data
        if customer_buffer:
            batch_count += 1
            print(f"Submitting final batch {batch_count} with {len(customer_buffer)} records")
            future = upload_executor.submit(upload_batch_to_td, customer_buffer, batch_count)
            upload_futures.append(future)
        
        # Wait for all uploads to complete
        print("Waiting for all uploads to complete...")
        for future in as_completed(upload_futures):
            try:
                future.result()
            except Exception as e:
                print(f"Upload error: {e}")
                raise
                
    finally:
        upload_executor.shutdown(wait=True)
    
    print(f"\nCompleted:")
    print(f"- Pages: {page_count}")
    print(f"- Customers: {total_customers}")
    print(f"- Batches: {batch_count}")
    
    if consecutive_errors > 0:
        print(f"\nWARNING: Completed with {consecutive_errors} consecutive errors")
        print("Some data may be missing due to failed pages")


def main():
    """Main entry point"""
    try:
        print("Yotpo parallel ingestion script started")
        print(f"Configuration: STORE_ID={YOTPO_STORE_ID}, DATABASE={TD_DATABASE}, TABLE={TD_TABLE}")
        print(f"Performance: {REQUESTS_PER_SECOND} req/sec, {UPLOAD_WORKERS} upload workers")
        
        start_time = time.time()
        
        # Get access token
        token = get_access_token()
        
        # Run parallel processing
        fetch_and_ingest_parallel(token)
        
        elapsed_time = time.time() - start_time
        print(f"\nScript completed in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        print(f"Fatal error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
