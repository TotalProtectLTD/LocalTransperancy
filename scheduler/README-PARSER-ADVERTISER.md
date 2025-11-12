# parser_of_advertiser.py Scheduler with Overlap Prevention

## Overview

`parser_of_advertiser.py` is scheduled to run every 2 minutes but uses **PID-based locking** to prevent concurrent execution. This solves the problem of variable execution time (10 seconds to 30 minutes).

## How It Works

### The Problem
- Script execution time varies: **10 seconds to 30 minutes**
- We don't want multiple instances running at the same time
- But we want to run as frequently as possible when idle

### The Solution: PID-Based Locking

```
Cron Schedule: Every 2 minutes
    ↓
Wrapper Script Checks Lock
    ↓
Is another instance running?
    ├─ YES → Skip this execution (log message)
    └─ NO  → Acquire lock and run
```

**Key Features:**
1. **Non-blocking**: If script is running, new cron invocations skip immediately
2. **Stale lock detection**: Automatically cleans up if process died unexpectedly
3. **Safe**: Verifies PID actually belongs to parser_of_advertiser.py
4. **Automatic cleanup**: Lock is released when script finishes (even if crashed)

### Lock Files
- **Lock file**: `/tmp/parser_of_advertiser.lock`
- **PID file**: `/tmp/parser_of_advertiser.pid`

## Installation

```bash
cd /Users/rostoni/Projects/LocalTransperancy
./scheduler/install-parser-advertiser.sh
```

This will:
- Add parser_of_advertiser.py to crontab (every 2 minutes)
- Keep existing scheduled jobs (bigquery-advertisers, send-creatives)
- Create log directories

## Status & Monitoring

### Check Current Status

```bash
./scheduler/status-parser-advertiser.sh
```

Shows:
- Whether script is currently running (with PID)
- How long it's been running
- Last execution time
- Recent log entries

### View Logs

```bash
# Live log tail
tail -f ./scheduler/logs/parser-advertiser.log

# Error log
tail -f ./scheduler/logs/parser-advertiser-error.log

# Last 50 lines
tail -50 ./scheduler/logs/parser-advertiser.log
```

## Example Execution Flow

### Scenario 1: Quick Execution (10 seconds)

```
02:00 → Script starts (PID 12345), finishes in 10s
02:02 → Script starts (PID 12389), finishes in 10s  
02:04 → Script starts (PID 12401), finishes in 10s
```

**Result**: Runs every 2 minutes as scheduled

### Scenario 2: Long Execution (30 minutes)

```
02:00 → Script starts (PID 12345)
02:02 → Skipped (PID 12345 still running)
02:04 → Skipped (PID 12345 still running)
02:06 → Skipped (PID 12345 still running)
...
02:30 → Script finishes (PID 12345)
02:32 → Script starts (PID 12890)
```

**Result**: No overlap, resumes as soon as previous execution finishes

### Scenario 3: Crash Recovery

```
02:00 → Script starts (PID 12345)
02:05 → Script crashes (lock files remain)
02:06 → Detects stale lock, cleans up, starts new instance (PID 12456)
```

**Result**: Automatic recovery from crashes

## Log Format

### Standard Output (parser-advertiser.log)

```
[2025-11-06 16:30:00] Starting parser_of_advertiser.py (PID 12345)
[INFO] Visiting HTML for cookies | {"advertiser_id": "AR12345..."}
[INFO] [1] SearchCreatives - ads_daily=1234
[INFO] [2] Page collected +45 creatives (total 89)
[INFO] DB insert completed | {"input": 89, "new": 67, "duplicates": 22}
[2025-11-06 16:32:15] Finished with exit code: 0
```

### Skipped Execution

```
[2025-11-06 16:32:00] Another instance (PID 12345) is already running. Skipping.
```

## Configuration

### Change Execution Frequency

Edit crontab schedule in `install-parser-advertiser.sh`:

```bash
# Current: Every 2 minutes
*/2 * * * * ...

# Every 1 minute (more aggressive)
* * * * * ...

# Every 5 minutes (more conservative)
*/5 * * * * ...

# Every 10 minutes
*/10 * * * * ...
```

Then reinstall:
```bash
./scheduler/install-parser-advertiser.sh
```

### Disable Scheduler

```bash
# Remove from crontab manually
crontab -e
# Delete the parser-advertiser line

# Or reinstall without it
./scheduler/install-cron.sh
```

## Testing

Test the locking mechanism:

```bash
./scheduler/test-flock.sh
```

This simulates:
1. First instance running
2. Second instance trying to start (should skip)
3. Third instance after first completes (should run)

## Troubleshooting

### Script Always Skipping

```bash
# Check if there's a stuck process
./scheduler/status-parser-advertiser.sh

# If showing stale lock, manually clean up
rm -f /tmp/parser_of_advertiser.lock /tmp/parser_of_advertiser.pid
```

### Script Not Running at All

```bash
# Check if it's in crontab
crontab -l | grep parser-advertiser

# Check wrapper script is executable
ls -l ./scheduler/run-parser-advertiser.sh

# Test wrapper manually
./scheduler/run-parser-advertiser.sh
```

### Check Cron Execution

```bash
# macOS: Check system logs
log show --predicate 'process == "cron"' --last 1h

# Check if cron is running
ps aux | grep cron
```

## Performance Expectations

### With 2-Minute Schedule:

- **If avg execution = 10s**: ~30 runs/hour, ~720 runs/day
- **If avg execution = 5min**: ~12 runs/hour, ~288 runs/day
- **If avg execution = 30min**: ~2 runs/hour, ~48 runs/day

### Optimal Schedule:

The 2-minute schedule is optimal because:
1. Quick jobs run frequently (max 2-minute delay)
2. Long jobs never overlap
3. System resumes immediately when job finishes

## Integration with Other Schedulers

Current cron jobs:

```
1. bigquery_advertisers_postgres.py → Daily at 2:00 AM
2. send_incoming_creative.py → Every 4 minutes
3. parser_of_advertiser.py → Every 2 minutes (overlap-safe)
```

All jobs are independent and don't interfere with each other.

## See Also

- Main scheduler README: `./scheduler/README.md`
- Parser script: `parser_of_advertiser.py`
- Cron status: `./scheduler/status-cron.sh`


