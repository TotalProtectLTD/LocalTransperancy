# Automated Scheduling

The Local Transparency project includes automated scheduling for daily data pipeline tasks using macOS's built-in `launchd` system.

## Overview

The scheduler automatically runs data import scripts on a daily basis, ensuring your database stays up-to-date without manual intervention.

## Scheduled Scripts

### bigquery_advertisers_postgres.py

**Schedule:** Daily at 2:00 AM

**What it does:**
- Queries Google BigQuery public dataset for advertiser information
- Exports data to Google Cloud Storage (GCS)
- Downloads CSV file locally
- Imports data into PostgreSQL `advertisers` table
- Handles deduplication and data normalization

**Typical execution time:** 8-14 minutes for 3.5M+ rows

**Logs:** Available in `scheduler/logs/`

### send_incoming_creative.py

**Schedule:** Every 1 minute

**What it does:**
- Selects up to 30 eligible creatives from PostgreSQL `creatives_fresh` table
- Sends them to the admin API at https://magictransparency.com/api/new-creative
- Marks successful rows as synced
- Marks failed rows with error messages

**Arguments:** `--limit 30`

**First execution:** 1 minute after installation

**Logs:** Available in `scheduler/logs/`

## Setup

See the [Scheduler README](../scheduler/README.md) for complete setup instructions.

Quick start:
```bash
# Install bigquery-advertisers scheduler (daily at 2 AM)
./scheduler/install.sh

# Install send-creatives scheduler (every 1 minute via cron)
# Note: Cron is configured via install-cron.sh or install-bigquery-creatives.sh
```

## Monitoring

### During the Day

Check the master summary log for quick status:
```bash
./scheduler/view-master.sh
```

Shows essential information:
- Date and time of last execution
- Success/failure status
- Number of new advertisers added
- Duration

### Detailed Logs

For troubleshooting or detailed information:
```bash
./scheduler/view.sh
```

Shows full execution output with color-coded success/error messages.

## Workflow Integration

The scheduler is part of the automated data pipeline:

```
Daily Schedule (2:00 AM)
    ↓
bigquery_advertisers_postgres.py
    ↓
BigQuery → GCS → PostgreSQL
    ↓
Advertiser database updated
    ↓
Logs captured for monitoring
```

## Status Checking

Check if the schedulers are running:
```bash
# Check bigquery-advertisers scheduler
./scheduler/status.sh

# Check send-creatives scheduler
./scheduler/status-send-creatives.sh
```

This shows:
- Whether the agent is loaded
- Next scheduled run time (or interval)
- Last execution status

## Configuration

The schedule can be customized by editing the plist file. See [Scheduler README](../scheduler/README.md#schedule-configuration) for details.

## Troubleshooting

If the scheduler isn't working:

1. Check status: `./scheduler/status.sh`
2. View logs: `./scheduler/view.sh`
3. Reinstall if needed: `./scheduler/uninstall.sh` then `./scheduler/install.sh`
4. Test script manually: `python3 bigquery_advertisers_postgres.py`

For more troubleshooting tips, see the [Scheduler README](../scheduler/README.md#troubleshooting).

## Additional Scripts

Additional scripts can be scheduled using the same pattern:
- `bigquery_creatives_postgres.py` - Daily creative imports

See the scheduler directory for examples and templates.

## Documentation

- **Scheduler README:** `scheduler/README.md` - Complete scheduler documentation
- **Script Documentation:** See header comments in each script file
- **Database Setup:** `docs/DATABASE_SETUP.md`

