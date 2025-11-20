# macOS Scheduler for bigquery_advertisers_postgres.py

This directory contains a launchd-based scheduler that automatically runs `bigquery_advertisers_postgres.py` daily on macOS.

## Overview

The scheduler uses macOS's built-in `launchd` system to:
- Run the script daily at 2:00 AM (configurable)
- Automatically survive Mac restarts
- Capture detailed logs for monitoring
- Provide a master summary log with essential information

## Quick Start

1. **Install the scheduler:**
   ```bash
   ./scheduler/install.sh
   ```

2. **Check status:**
   ```bash
   ./scheduler/status.sh
   ```

3. **View logs:**
   ```bash
   ./scheduler/view.sh          # Detailed logs
   ./scheduler/view-master.sh    # Master summary (essential info only)
   ```

## Files

### Launch Agent
- `com.localtransparency.bigquery-advertisers.plist` - launchd configuration file

### Management Scripts
- `install.sh` - Install and load the launch agent
- `uninstall.sh` - Remove the launch agent
- `status.sh` - Check if agent is loaded and show next run time
- `view.sh` - View recent detailed logs
- `view-master.sh` - View master summary log
- `summarize.sh` - Parse detailed logs and update master.log
- `cleanup-logs.sh` - Remove old log files

### Logs
- `logs/bigquery-advertisers.log` - Standard output (detailed logs)
- `logs/bigquery-advertisers-error.log` - Standard error (error messages)
- `logs/master.log` - Essential summary (date, status, key metrics)

## Usage

### Installation

```bash
./scheduler/install.sh
```

This will:
- Copy the plist file to `~/Library/LaunchAgents/`
- Create the logs directory
- Load the launch agent
- Verify installation

### Checking Status

```bash
./scheduler/status.sh
```

Output example:
```
✅ Agent is loaded
📅 Schedule: Daily at 2:00 AM
🕐 Last run: 2025-11-05 02:15:23
✅ Last run: SUCCESS
```

### Viewing Logs

**Detailed logs:**
```bash
./scheduler/view.sh
# Or specify number of lines:
./scheduler/view.sh 50
```

Shows last 30 lines (or specified number) with color-coded output:
- Green for success messages
- Red for errors

**Master summary log:**
```bash
./scheduler/view-master.sh
# Or specify number of entries:
./scheduler/view-master.sh 50
```

Shows essential information only:
```
2025-11-05 02:00:15 | SUCCESS | New advertisers: 2,123,456 | Duration: 523s
2025-11-04 02:00:12 | SUCCESS | New advertisers: 1,987,654 | Duration: 498s
2025-11-03 02:00:18 | FAIL    | Error: Connection timeout
```

### Updating Master Log

The master log can be updated manually by parsing the detailed logs:

```bash
./scheduler/summarize.sh
```

This script:
- Parses `logs/bigquery-advertisers.log`
- Extracts execution timestamp, status, rows inserted, and duration
- Appends a one-line summary to `logs/master.log`

**Note:** The master log is not automatically updated. Run `summarize.sh` after each execution to keep it current, or integrate it into your workflow.

### Uninstallation

```bash
./scheduler/uninstall.sh
```

This will:
- Unload the launch agent
- Remove the plist file
- Optionally remove log files (prompts for confirmation)

## Schedule Configuration

The default schedule is **daily at 2:00 AM**.

To change the schedule:

1. Edit `scheduler/com.localtransparency.bigquery-advertisers.plist`
2. Modify the `StartCalendarInterval` section:
   ```xml
   <key>StartCalendarInterval</key>
   <dict>
       <key>Hour</key>
       <integer>2</integer>  <!-- Change hour (0-23) -->
       <key>Minute</key>
       <integer>0</integer>   <!-- Change minute (0-59) -->
   </dict>
   ```
3. Run `./scheduler/install.sh` again to reload

## Log Management

### Automatic Rotation

launchd automatically rotates logs when they reach approximately 1MB:
- Old logs are compressed and archived
- Recent logs remain accessible
- No manual intervention needed

### Manual Cleanup

To remove old log files:

```bash
./scheduler/cleanup-logs.sh
# Or specify days to keep:
./scheduler/cleanup-logs.sh 60  # Keep logs from last 60 days
```

Default: Removes logs older than 30 days.

## What Logs Contain

### Detailed Logs (`bigquery-advertisers.log`)

Contains full output from the script:
- BigQuery query execution progress
- GCS export/download stats (file size, duration, speed)
- PostgreSQL import progress (rows loaded, inserted, skipped)
- Final table statistics (total advertisers, with/without country)
- Cost information ($0.00 for public datasets)
- Error messages if any

Example entries:
```
✓ Query executed and export completed successfully
  File Size:   45.2 MB
  Duration:    245.3 seconds
  Cost:        $0.00 (FREE!)

✅ Import Complete
  Rows loaded:       3,456,789
  Rows inserted:     2,123,456
  Rows skipped:      1,333,333 (duplicates)
  Duration:          523.4s (8.7 min)
```

### Master Summary Log (`master.log`)

Contains one-line summaries per execution:
- Date and time
- Status (SUCCESS/FAIL)
- Key metrics (new advertisers count, duration)
- Error messages (if failed)

Example format:
```
2025-11-05 02:00:15 | SUCCESS | New advertisers: 2,123,456 | Duration: 523s
2025-11-04 02:00:12 | SUCCESS | New advertisers: 1,987,654 | Duration: 498s
2025-11-03 02:00:18 | FAIL    | Error: BigQuery connection timeout
```

## Troubleshooting

### Agent Not Running

**Check if agent is loaded:**
```bash
launchctl list | grep bigquery-advertisers
```

**If not loaded, reinstall:**
```bash
./scheduler/install.sh
```

### No Logs Appearing

**Check if logs directory exists:**
```bash
ls -la scheduler/logs/
```

**Check if script ran:**
```bash
./scheduler/status.sh
```

**Manually test the script:**
```bash
python3 bigquery_advertisers_postgres.py
```

### Agent Not Surviving Restart

launchd should automatically reload agents after restart. If not:
1. Check if plist file exists: `ls ~/Library/LaunchAgents/com.localtransparency.bigquery-advertisers.plist`
2. Check if agent is loaded: `launchctl list | grep bigquery-advertisers`
3. Reinstall if needed: `./scheduler/install.sh`

### Viewing launchd Logs

launchd also maintains its own logs:
```bash
# View system logs for the agent
log show --predicate 'subsystem == "com.apple.launchd"' --last 1h | grep bigquery-advertisers
```

## How It Works

1. **launchd** is macOS's native job scheduler (similar to cron, but more powerful)
2. The **plist file** defines when and how to run the script
3. **Launch Agents** run in user context (no sudo required)
4. Logs are automatically captured to files
5. The agent survives system restarts automatically

## Integration with Workflow

This scheduler is part of the Local Transparency project's automated data pipeline:

1. **Daily at 2:00 AM:** `bigquery_advertisers_postgres.py` runs
   - Queries BigQuery for advertiser data
   - Exports to GCS
   - Downloads and imports to PostgreSQL
   - Updates advertiser database

2. **Monitoring:** Use `view-master.sh` during the day to check:
   - Last execution status
   - Number of new advertisers added
   - Any errors that occurred

3. **Troubleshooting:** Use `view.sh` for detailed logs if issues occur

## send_incoming_creative.py Scheduler

The scheduler also includes support for `send_incoming_creative.py` which runs every 30 seconds.

### Quick Start

1. **Install the scheduler:**
   ```bash
   ./scheduler/install-send-creatives.sh
   ```

2. **Check status:**
   ```bash
   ./scheduler/status-send-creatives.sh
   ```

3. **View logs:**
   ```bash
   ./scheduler/view-send-creatives.sh          # Detailed logs
   ./scheduler/view-master-send-creatives.sh  # Master summary
   ```

### Schedule

- **Frequency:** Every 30 seconds
- **Arguments:** `--limit 10`
- **First run:** 30 seconds after installation

### Management Scripts

- `install-send-creatives.sh` - Install and load the launch agent
- `uninstall-send-creatives.sh` - Remove the launch agent
- `status-send-creatives.sh` - Check if agent is loaded
- `view-send-creatives.sh` - View recent detailed logs
- `view-master-send-creatives.sh` - View master summary log
- `summarize-send-creatives.sh` - Parse detailed logs and update master.log

### Master Log Format

Example format:
```
2025-11-05 14:00:15 | SUCCESS | Processed: 10 | Success: 10 | Failed: 0
2025-11-05 14:10:12 | SUCCESS | Processed: 10 | Success: 8 | Failed: 2
2025-11-05 14:20:18 | SUCCESS | No eligible rows to send
```

### What Logs Contain

From `send_incoming_creative.py` output:
- Per-row processing: `✓ id=123 -> synced` or `✗ id=456 -> sync_failed`
- Summary: `Done. Success: 10, Failed: 2`
- "✓ No eligible rows to send" if no rows available
- Error messages for failed rows
- Network/API errors

## See Also

- Main project documentation: `../README.md`
- Database setup: `../docs/DATABASE_SETUP.md`
- BigQuery script documentation: `../bigquery_advertisers_postgres.py` (header comments)
- Scheduler overview: `../docs/SCHEDULER.md`

