# parser_of_advertiser.py Scheduler - Quick Start

## 🚀 Install (1 Command)

```bash
cd /Users/rostoni/Projects/LocalTransperancy
./scheduler/install-parser-advertiser.sh
```

## 📊 Check Status

```bash
./scheduler/status-parser-advertiser.sh
```

## 📝 View Logs

```bash
# Live tail
tail -f ./scheduler/logs/parser-advertiser.log

# Last 50 lines
tail -50 ./scheduler/logs/parser-advertiser.log
```

## ⚙️ How It Works

```
Every 1 minute:
    ↓
Is script already running?
    ├─ YES → Skip (log message)
    └─ NO  → Run script
```

**Key Features:**
- ✅ Runs every 1 minute when idle
- ✅ Never overlaps (even if one run takes 30 minutes)
- ✅ Automatic stale lock cleanup
- ✅ Adapts to execution time

## 📈 Current Schedule

```
✓ bigquery_advertisers_postgres.py → Daily at 2:00 AM
✓ send_incoming_creative.py → Every 4 minutes
✓ parser_of_advertiser.py → Every 1 minute (overlap-safe)
```

## 📚 Full Documentation

- **Complete guide**: `./scheduler/README-PARSER-ADVERTISER.md`
- **Option analysis**: `./scheduler/OVERLAP_PREVENTION_ANALYSIS.md`
- **Main scheduler README**: `./scheduler/README.md`

## 🐛 Troubleshooting

### Script not running?
```bash
# Check crontab
crontab -l | grep parser

# Test manually
./scheduler/run-parser-advertiser.sh
```

### Stuck/stale lock?
```bash
# Check status
./scheduler/status-parser-advertiser.sh

# Manual cleanup
rm -f /tmp/parser_of_advertiser.lock /tmp/parser_of_advertiser.pid
```

## ✅ Done!

Your scheduler is ready. It will:
1. Fetch next advertiser from API
2. Collect all creatives
3. Insert into database
4. Update last_seen timestamps
5. Mark advertiser as completed
6. Repeat every 1 minute (when not busy)



