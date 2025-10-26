# BigQuery Import Script Usage

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up credentials:**
   - Make sure your BigQuery credentials file exists at:
     `/Users/rostoni/Downloads/CursorTransperancy/backend/bigquery-credentials.json`
   - Or set `GOOGLE_APPLICATION_CREDENTIALS` environment variable

3. **Run the import:**
   ```bash
   # Import default file (October)
   python3 import_bigquery_data.py
   
   # Import specific file
   python3 import_bigquery_data.py "November"
   ```

## Configuration

The script uses these default settings:
- **Project ID**: `youtubeilike`
- **Bucket**: `youtubeilike-temp-exports`
- **Default File**: `October`
- **PostgreSQL**: `local_transparency` database

## What it does

1. Downloads CSV file from Google Cloud Storage bucket
2. Reads `creative_id` and `advertiser_id` columns
3. Imports data into PostgreSQL `creatives_fresh` table
4. Skips duplicate records (based on creative_id + advertiser_id)
5. Sets status to 'pending' for new records

## Output

The script will show:
- Download progress
- Import statistics (imported/skipped records)
- Final record count
- Any errors encountered

## Troubleshooting

- **Credentials not found**: Check the path in the script or set `GOOGLE_APPLICATION_CREDENTIALS`
- **File not found**: The script will list available files in the bucket
- **Database connection**: Make sure PostgreSQL is running and accessible
- **Missing columns**: Script expects `creative_id` and `advertiser_id` columns
