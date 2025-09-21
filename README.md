# Custom Connectors

A collection of custom data connectors for various APIs and services.

## Yotpo Loyalty Profiles Connector

Fetches customer loyalty profile data from the Yotpo API and ingests it into Treasure Data.

### Features

- **Parallel Processing**: Fetches API data and uploads to TD concurrently for optimal performance
- **Rate Limiting**: Respects API limits with configurable request rate controls
- **Retry Logic**: Robust error handling with exponential backoff
- **Comprehensive Logging**: Detailed logging for monitoring and debugging
- **Data Validation**: Input validation and error detection for reliable data processing

### Usage

#### Environment Variables

Set the following environment variables:

```bash
export YOTPO_CLIENT_SECRET="your_client_secret"
export YOTPO_STORE_ID="your_store_id"
export TD_API_KEY="your_td_api_key"
```

#### Running the Script

```bash
cd yotpo-loyalty-profiles/python
python -m yotpo.main
```

#### Digdag Workflow

The connector can be run as a Digdag workflow:

```bash
digdag run yotpo_python_script.dig
```

### Configuration

Key configuration parameters in `main.py`:

- `REQUESTS_PER_SECOND`: API rate limit (default: 4.5)
- `BATCH_SIZE`: Records per TD upload batch (default: 100,000)
- `UPLOAD_WORKERS`: Parallel upload threads (default: 2)
- `MAX_RETRIES`: Request retry attempts (default: 3)

### Output

Data is stored in Treasure Data with the following schema:
- `json_response`: Raw JSON customer data from Yotpo
- `time`: Unix timestamp of ingestion

### Error Handling

The script handles various error conditions:
- Network timeouts and connection errors
- API rate limiting (429 responses)
- Invalid JSON responses
- TD upload failures

Check logs for detailed error information and troubleshooting guidance.
