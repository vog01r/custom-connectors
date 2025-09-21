import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import pytd
import requests

# === CONFIGURATION ===
# Environment variables - validate early
YOTPO_CLIENT_SECRET = os.environ.get('YOTPO_CLIENT_SECRET')
YOTPO_STORE_ID = os.environ.get('YOTPO_STORE_ID')
TD_API_KEY = os.environ.get('TD_API_KEY')

if not all([YOTPO_CLIENT_SECRET, YOTPO_STORE_ID, TD_API_KEY]):
    raise ValueError("Missing required environment variables: YOTPO_CLIENT_SECRET, YOTPO_STORE_ID, TD_API_KEY")

# API Configuration
YOTPO_BASE_URL = "https://api.yotpo.com/core/v3"
TD_DATABASE = "raw_us_mavi"
TD_TABLE = "yotpo_customers"

# Performance settings
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2
BATCH_SIZE = 100_000
REQUEST_TIMEOUT = 30
REQUESTS_PER_SECOND = 4.5  # Stay under 5 req/sec limit
MAX_CONSECUTIVE_ERRORS = 3

# Threading settings
UPLOAD_WORKERS = 2  # Number of parallel uploads to TD

# Rate limiting variables
_last_request_time = 0.0
_rate_limit_lock = threading.Lock()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def rate_limit_wait() -> None:
    """Simple rate limiter - ensures we don't exceed requests per second.
    
    Implements a basic rate limiting mechanism to respect API rate limits.
    Uses a global lock to ensure thread safety in parallel execution.
    """
    global _last_request_time
    min_interval = 1.0 / REQUESTS_PER_SECOND
    
    with _rate_limit_lock:
        now = time.time()
        time_since_last = now - _last_request_time
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        _last_request_time = time.time()


def get_access_token() -> str:
    """Get access token from Yotpo API.
    
    Returns:
        str: The access token for API authentication.
        
    Raises:
        requests.exceptions.RequestException: If the API request fails.
        KeyError: If the response doesn't contain an access token.
    """
    if not YOTPO_CLIENT_SECRET or not YOTPO_STORE_ID:
        raise ValueError("YOTPO_CLIENT_SECRET and YOTPO_STORE_ID must be set")
        
    url = f"{YOTPO_BASE_URL}/stores/{YOTPO_STORE_ID}/access_tokens"
    logger.info(f"Requesting access token from {url}")
    
    try:
        response = requests.post(
            url, 
            json={"secret": YOTPO_CLIENT_SECRET}, 
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        if "access_token" not in data:
            raise KeyError("Access token not found in response")
            
        token = data["access_token"]
        logger.info("Access token received successfully")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get access token: {e}")
        raise


def upload_batch_to_td(customers: List[Dict[str, Any]], batch_num: int) -> bool:
    """Upload a batch of customers to Treasure Data.
    
    Args:
        customers: List of customer data dictionaries.
        batch_num: Batch number for logging purposes.
        
    Returns:
        bool: True if upload was successful.
        
    Raises:
        Exception: If the upload fails after retries.
    """
    if not customers:
        logger.warning(f"Batch {batch_num}: No customers to upload")
        return True
        
    logger.info(f"Starting upload of batch {batch_num} with {len(customers)} records")
    
    # Prepare records for TD
    records = [
        {
            "json_response": json.dumps(customer, separators=(",", ":")),
            "time": int(datetime.utcnow().timestamp())
        }
        for customer in customers
    ]
    
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
        logger.info(f"Successfully uploaded batch {batch_num}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload batch {batch_num}: {e}")
        raise
    finally:
        client.close()


def _validate_json_response(response: requests.Response, attempt: int) -> Optional[Dict[str, Any]]:
    """Validate and parse JSON response with detailed error logging."""
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' not in content_type:
        logger.warning(f"Non-JSON response (attempt {attempt + 1}): {content_type}")
        logger.debug(f"Response preview: {response.text[:500]}")
        return None
    
    # Check response size
    response_size = len(response.text)
    if response_size > 1_000_000:  # 1MB
        logger.warning(f"Large response size: {response_size} bytes")
    
    try:
        return response.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error (attempt {attempt + 1}): {e}")
        logger.debug(f"Response size: {len(response.text)} bytes")
        
        # Detailed error analysis for debugging
        error_pos = getattr(e, 'pos', -1)
        if error_pos > 0:
            start = max(0, error_pos - 100)
            end = min(len(response.text), error_pos + 100)
            logger.debug(f"Context around position {error_pos}: {repr(response.text[start:end])}")
        else:
            logger.debug(f"Response start: {repr(response.text[:200])}")
            logger.debug(f"Response end: {repr(response.text[-200:])}")
        
        # Check for common issues
        text = response.text.strip()
        if text.startswith('<'):
            logger.error("Response appears to be HTML/XML instead of JSON")
        elif 'rate limit' in text.lower():
            logger.error("Possible rate limit message in response")
        elif not text:
            logger.error("Empty response body")
        elif error_pos > 0 and error_pos == len(response.text) - 1:
            logger.error("Response appears to be truncated")
        
        return None


def fetch_page_with_retry(url: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Fetch a single page with retry logic and comprehensive error handling.
    
    Args:
        url: The API URL to fetch.
        headers: HTTP headers for the request.
        
    Returns:
        Dict containing the API response, or None if all retries failed.
    """
    for attempt in range(MAX_RETRIES + 1):
        rate_limit_wait()
        
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                return _validate_json_response(response, attempt)
                
            elif response.status_code == 400 and "no results found" in response.text.lower():
                logger.info("API returned 'no results found' - treating as empty result")
                return {"customers": [], "pagination": {}}
                
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', RETRY_DELAY_SEC * 2))
                logger.warning(f"Rate limit hit, waiting {retry_after} seconds")
                time.sleep(retry_after)
                continue
                
            else:
                logger.warning(f"HTTP {response.status_code} (attempt {attempt + 1})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                    continue
                    
        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout (attempt {attempt + 1})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error: {e} (attempt {attempt + 1})")
        
        # Common retry logic for all exceptions
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC * (attempt + 1))
            continue
    
    logger.error(f"Failed to fetch page after {MAX_RETRIES + 1} attempts")
    return None


def fetch_and_ingest_parallel(token: str) -> None:
    """Main function to fetch customer pages and upload to TD in parallel.
    
    Args:
        token: Yotpo API access token.
        
    Raises:
        Exception: If critical errors occur during processing.
    """
    if not token:
        raise ValueError("Access token is required")
        
    # Setup thread pool for uploads
    upload_executor = ThreadPoolExecutor(max_workers=UPLOAD_WORKERS)
    upload_futures = []
    
    # Data tracking
    page_count = 0
    batch_count = 0
    total_customers = 0
    customer_buffer = []
    consecutive_errors = 0
    
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
            
            logger.info(f"Fetching page {page_count + 1}")
            
            # Fetch page
            data = fetch_page_with_retry(url, headers)
            
            if not data:
                consecutive_errors += 1
                logger.warning(f"Failed to fetch page (consecutive errors: {consecutive_errors})")
                
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping fetch")
                    break
                
                # Try to continue with next page if possible
                if page_info:
                    logger.warning("Skipping failed page, data may be incomplete")
                    # Cannot continue without knowing next page_info
                    break
                else:
                    logger.error("Failed on first page, cannot continue")
                    break
            else:
                consecutive_errors = 0  # Reset on success
            
            # Extract data
            customers = data.get("customers", [])
            next_page_info = data.get("pagination", {}).get("next_page_info")
            
            if not customers:
                logger.info("No customers in response - reached end of data")
                break
                
            # Add to buffer
            customer_buffer.extend(customers)
            page_count += 1
            total_customers += len(customers)
            logger.info(f"Page {page_count}: {len(customers)} customers (Total: {total_customers})")
            
            # Check if we need to upload a batch
            while len(customer_buffer) >= BATCH_SIZE:
                batch_count += 1
                batch_data = customer_buffer[:BATCH_SIZE]
                customer_buffer = customer_buffer[BATCH_SIZE:]
                
                # Submit upload in background
                logger.info(f"Submitting batch {batch_count} for upload")
                future = upload_executor.submit(upload_batch_to_td, batch_data, batch_count)
                upload_futures.append(future)
                
                # Clean up completed uploads
                upload_futures = [f for f in upload_futures if not f.done()]
                
                # If too many uploads queued, wait for one to complete
                if len(upload_futures) >= 3:
                    logger.info(f"Upload queue full ({len(upload_futures)}), waiting...")
                    # Wait for at least one to complete
                    for future in as_completed(upload_futures):
                        future.result()  # This will raise exception if upload failed
                        upload_futures.remove(future)
                        break
            
            # Check for next page
            if not next_page_info:
                logger.info("No more pages available")
                break
                
            page_info = next_page_info
            
        # Upload any remaining data
        if customer_buffer:
            batch_count += 1
            logger.info(f"Submitting final batch {batch_count} with {len(customer_buffer)} records")
            future = upload_executor.submit(upload_batch_to_td, customer_buffer, batch_count)
            upload_futures.append(future)
        
        # Wait for all uploads to complete
        logger.info("Waiting for all uploads to complete...")
        for future in as_completed(upload_futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Upload error: {e}")
                raise
                
    finally:
        upload_executor.shutdown(wait=True)
    
    logger.info(f"Processing completed:")
    logger.info(f"- Pages processed: {page_count}")
    logger.info(f"- Total customers: {total_customers}")
    logger.info(f"- Batches uploaded: {batch_count}")
    
    if consecutive_errors > 0:
        logger.warning(f"Completed with {consecutive_errors} consecutive errors")
        logger.warning("Some data may be missing due to failed pages")


def main() -> None:
    """Main entry point for the Yotpo customer data ingestion script.
    
    This function orchestrates the entire process:
    1. Validates configuration
    2. Gets API access token
    3. Fetches customer data from Yotpo API
    4. Uploads data to Treasure Data in parallel batches
    
    Raises:
        Exception: If any critical error occurs during processing.
    """
    try:
        logger.info("Yotpo parallel ingestion script started")
        logger.info(f"Configuration: STORE_ID={YOTPO_STORE_ID}, DATABASE={TD_DATABASE}, TABLE={TD_TABLE}")
        logger.info(f"Performance: {REQUESTS_PER_SECOND} req/sec, {UPLOAD_WORKERS} upload workers")
        
        start_time = time.time()
        
        # Get access token
        token = get_access_token()
        
        # Run parallel processing
        fetch_and_ingest_parallel(token)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Script completed successfully in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Fatal error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
