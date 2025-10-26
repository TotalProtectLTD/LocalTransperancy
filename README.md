# Local Transparency

A Python-based local client that helps the server Transparency project execute parsing tasks and upload data to server databases. This project scrapes Google Ads Transparency Center to extract YouTube videos, App Store IDs, and creative metadata.

## Project Overview

**Local Transparency** runs on localhost and performs:
- Parsing Google Ads Transparency Center creative pages
- Extracting YouTube video IDs and App Store IDs from creatives
- Bandwidth-optimized scraping (49-59% traffic reduction)
- Concurrent stress testing with worker pools
- Real creative detection (filtering out Google's decoy/noise videos)

## System Requirements

### Required
- **Python**: 3.7 or higher
- **PostgreSQL**: 12.0 or higher (recommended: 18)
- **Operating System**: macOS, Linux, or Windows
- **Internet Connection**: Required for scraping

### Recommended
- **RAM**: 4GB minimum, 8GB recommended (8GB+ recommended for large datasets)
- **Storage**: 1GB free space for dependencies and database

## Installation Instructions

### Step 1: Check Python Version

```bash
python3 --version
```

You should see Python 3.7 or higher. If not, install Python from:
- macOS: `brew install python3` (using Homebrew)
- Linux: `sudo apt install python3 python3-pip`
- Windows: Download from [python.org](https://www.python.org/downloads/)

### Step 2: Install PostgreSQL Database

Install PostgreSQL on your system:

```bash
# macOS (using Homebrew - installs PostgreSQL 18)
brew install postgresql@18
brew services start postgresql@18

# Linux (Ubuntu/Debian)
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# For detailed setup instructions, see DATABASE_SETUP.md
```

Create database and user:

```bash
psql postgres
```

```sql
CREATE DATABASE local_transparency;
CREATE USER transparency_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE local_transparency TO transparency_user;
\q
```

**For complete PostgreSQL setup guide, see `DATABASE_SETUP.md`**

### Step 3: Install Python Dependencies

Navigate to the project directory:

```bash
cd /Users/rostoni/Downloads/LocalTransperancy
```

Install required packages:

```bash
pip3 install -r requirements.txt
```

This will install:
- **playwright**: Browser automation library
- **httpx**: Async HTTP client for API requests
- **psycopg2-binary**: PostgreSQL adapter for Python
- **mitmproxy** (optional): For accurate traffic measurement

### Step 4: Install Browser (Chromium)

After installing playwright, you need to download the Chromium browser:

```bash
playwright install chromium
```

This downloads the Chromium browser binary (~300MB) required for web scraping.

### Step 5: Verify Installation

Test that everything is installed correctly:

```bash
python3 google_ads_transparency_scraper.py --help
```

You should see the help message with usage instructions.

## Project Files

### Main Files
- **`google_ads_transparency_scraper.py`**: Main scraper for single URL processing
- **`stress_test_scraper.py`**: Concurrent stress tester for batch processing
- **`requirements.txt`**: Python package dependencies
- **`README.md`**: This file
- **`DATABASE_SETUP.md`**: PostgreSQL installation and configuration guide

### Generated Files (created during usage)
- **`debug/`**: Debug output folder (created when using debug flags)
- **`creatives_stress_test.db`**: SQLite database for stress test results (legacy)
- **`stress_test_results.txt`**: Log file for stress test runs
- **PostgreSQL database**: Primary database for production use

## Usage

### Basic Usage - Single URL

Scrape a single creative page:

```bash
python3 google_ads_transparency_scraper.py "https://adstransparency.google.com/advertiser/AR.../creative/CR...?region=anywhere&platform=YOUTUBE"
```

### With Proxy (for traffic measurement)

```bash
python3 google_ads_transparency_scraper.py "URL" --proxy
```

### With External Proxy (IPRoyal, etc.)

```bash
python3 google_ads_transparency_scraper.py "URL" \\
    --proxy-server "us10.4g.iproyal.com:8022" \\
    --proxy-username "YOUR_USER" \\
    --proxy-password "YOUR_PASS"
```

### Debug Mode

Save debug files for App Store ID extraction:

```bash
python3 google_ads_transparency_scraper.py "URL" --debug-extra-information
```

Save ALL content.js + API responses:

```bash
python3 google_ads_transparency_scraper.py "URL" --debug-content
```

### Output to JSON

```bash
python3 google_ads_transparency_scraper.py "URL" --json output.json
```

### Stress Testing - Multiple URLs

Process multiple URLs concurrently from database:

```bash
# Process all pending URLs with 10 concurrent workers
python3 stress_test_scraper.py --max-concurrent 10

# Process 100 URLs with 20 concurrent workers
python3 stress_test_scraper.py --max-concurrent 20 --max-urls 100

# Without proxy (direct connection)
python3 stress_test_scraper.py --max-concurrent 10 --no-proxy
```

## Features

### Real Video Detection (100% accuracy)
- **API-based method** (primary): Uses GetCreativeById API response
- **Frequency-based fallback**: Counts creative ID frequency in content.js requests
- Filters out Google's noise/decoy videos

### Bandwidth Optimization (49-59% reduction)
- Blocks images, fonts, CSS
- Blocks analytics, ads, tracking
- Optional proxy for accurate measurement
- All requests use same proxy (consistent routing)

### Data Extraction
- YouTube video IDs (filtered by real creative ID)
- App Store IDs (filtered by real creative ID)
- Creative metadata
- Ignores decoy/noise creatives

## Optional: mitmproxy for Traffic Measurement

If you want accurate traffic measurement (not required for basic usage):

### Install mitmproxy

```bash
# macOS
brew install mitmproxy

# Linux
pip3 install mitmproxy

# Windows
pip3 install mitmproxy
```

### Use with --proxy flag

```bash
python3 google_ads_transparency_scraper.py "URL" --proxy
```

This routes all requests through mitmproxy for accurate bandwidth tracking.

## Troubleshooting

### "playwright not installed" error

```bash
pip3 install playwright
playwright install chromium
```

### "httpx not installed" error

```bash
pip3 install httpx
```

### Browser download fails

Try manual installation:

```bash
playwright install chromium --force
```

### Permission denied errors

On macOS/Linux, you may need to make scripts executable:

```bash
chmod +x google_ads_transparency_scraper.py
chmod +x stress_test_scraper.py
```

### Port 8080 already in use (when using --proxy)

Change mitmproxy port or stop other services using port 8080:

```bash
# Find process using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>
```

## Database Setup

### PostgreSQL (Recommended for Production)

The Local Transparency project uses PostgreSQL for storing scraping results and managing data.

**See `DATABASE_SETUP.md` for complete PostgreSQL setup instructions**, including:
- Installation on macOS, Linux, Windows
- Database and user creation
- Table schema with indexes
- Python connection examples
- Backup and maintenance

Quick schema overview:

```sql
CREATE TABLE creatives (
    id SERIAL PRIMARY KEY,
    creative_id TEXT UNIQUE NOT NULL,
    advertiser_id TEXT,
    url TEXT,
    status TEXT DEFAULT 'pending',
    video_count INTEGER,
    video_ids JSONB,  -- JSON array for PostgreSQL
    appstore_id TEXT,
    scraped_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Status values:**
- `pending`: Not yet processed
- `processing`: Currently being processed
- `completed`: Successfully scraped
- `failed`: Failed (permanent error)

### SQLite (Legacy, for Testing)

The stress test scraper can also use SQLite for quick testing. See `stress_test_scraper.py` for SQLite schema.

## Performance Tips

### For Single URL Processing
- Use `--noblock` flag to disable resource blocking if you need full page content
- Use external proxy for better performance than mitmproxy

### For Batch Processing (Stress Testing)
- Start with low concurrency (10 workers) and increase gradually
- Use `--max-urls` to test with a small batch first
- Monitor system resources (CPU, memory, network)
- Use `--no-proxy` for fastest performance (if you don't need proxy)

## Project Structure

```
LocalTransperancy/
├── google_ads_transparency_scraper.py  # Main scraper
├── stress_test_scraper.py              # Concurrent stress tester
├── requirements.txt                     # Python dependencies
├── README.md                            # This file
├── debug/                               # Debug output (created on demand)
├── creatives_stress_test.db            # SQLite database (created on demand)
└── stress_test_results.txt             # Log file (created on demand)
```

## Exit Codes

- **0**: Success
- **1**: General error (exception, keyboard interrupt)
- **2**: Scraping validation failed (incomplete data)

## Support

For issues or questions:
1. Check this README for troubleshooting
2. Verify all dependencies are installed correctly
3. Test with a single URL first before batch processing
4. Use debug flags (`--debug-content`) to inspect scraping details

## License

Internal Use - Ad Transparency Investigation Team

## Version

- **google_ads_transparency_scraper.py**: v1.0 Production (2025-10-23)
- **stress_test_scraper.py**: Continuous Worker Pool Pattern

---

**Author**: Ad Transparency Investigation Team  
**Date**: October 2025

