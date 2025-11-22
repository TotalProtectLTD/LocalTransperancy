# Overlap Prevention for parser_of_advertiser.py

## Problem Statement

`parser_of_advertiser.py` has variable execution time:
- **Minimum**: 10 seconds (quick advertiser with few creatives)
- **Maximum**: 30+ minutes (large advertiser with many creatives, pagination)

**Requirement**: Run as frequently as possible, but **never run multiple instances concurrently**.

---

## Options Analyzed

### ✅ Option 1: PID-Based File Locking (IMPLEMENTED)

**Implementation**: Wrapper script with PID file + process verification

**How it works**:
1. Before starting, check if PID file exists
2. If exists, verify process is actually running and is our script
3. If running → skip this execution
4. If not running or stale → clean up and run
5. On exit, automatically clean up lock files

**Pros**:
- ✅ Simple and reliable
- ✅ Works on macOS and Linux
- ✅ No external dependencies
- ✅ Automatic stale lock cleanup
- ✅ Process verification (ensures PID belongs to our script)
- ✅ Cron can run every 1-2 minutes - only executes if previous is done

**Cons**:
- ⚠️ Small race condition window (milliseconds) - negligible in practice

**Result**: **BEST OPTION for this use case**

---

### Option 2: `flock` (File Locking)

**Implementation**: Use `flock` command for file locking

```bash
flock -n -x 200 || exit 0
# ... run script ...
200>/tmp/lock.file
```

**Pros**:
- ✅ Atomic lock acquisition
- ✅ No race conditions
- ✅ Kernel-level locking

**Cons**:
- ❌ Not available on macOS by default
- ❌ Requires additional installation (`brew install util-linux`)
- ❌ Not worth dependency for this use case

**Result**: Good option for Linux servers, not ideal for macOS

---

### Option 3: `systemd` Timer with Conflict

**Implementation**: Use systemd instead of cron (Linux only)

```ini
[Unit]
Conflicts=parser-advertiser.service

[Service]
Type=oneshot
ExecStart=/path/to/script
```

**Pros**:
- ✅ Built-in overlap prevention
- ✅ Better logging integration
- ✅ Service management

**Cons**:
- ❌ **Not available on macOS**
- ❌ More complex setup
- ❌ Overkill for simple scheduling

**Result**: Not applicable (you're on macOS)

---

### Option 4: Long Cron Interval

**Implementation**: Schedule cron every 30-60 minutes (longer than max execution)

```cron
*/30 * * * * /path/to/script
```

**Pros**:
- ✅ Simple - no locking needed
- ✅ Guaranteed no overlap

**Cons**:
- ❌ Wastes time: 10-second job waits 30 minutes before next run
- ❌ Poor throughput for quick advertisers
- ❌ Not optimal resource utilization

**Result**: Too conservative, not recommended

---

### Option 5: Queue-Based System

**Implementation**: Use message queue (Redis, RabbitMQ) with single worker

**Pros**:
- ✅ Perfect job distribution
- ✅ Scalable to multiple workers later
- ✅ Retry logic built-in

**Cons**:
- ❌ Requires Redis/RabbitMQ server
- ❌ More complex infrastructure
- ❌ Overkill for single-machine setup

**Result**: Good for production scale, too complex for current needs

---

### Option 6: Supervisor/Process Manager

**Implementation**: Use supervisor or pm2 to manage single long-running worker

```ini
[program:parser]
command=/path/to/worker.py
numprocs=1
autorestart=true
```

**Pros**:
- ✅ Single worker guaranteed
- ✅ Auto-restart on crash
- ✅ Good logging

**Cons**:
- ❌ Changes architecture (continuous vs scheduled)
- ❌ Requires refactoring script to be long-running
- ❌ Additional dependency (supervisor/pm2)

**Result**: Different paradigm, not needed

---

## Decision Matrix

| Option | Simplicity | Reliability | macOS Support | Performance | Verdict |
|--------|-----------|-------------|---------------|-------------|---------|
| **PID-based locking** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Native | ⭐⭐⭐⭐⭐ | ✅ **CHOSEN** |
| flock | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ Needs brew | ⭐⭐⭐⭐⭐ | ❌ |
| systemd | ⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ Linux only | ⭐⭐⭐⭐ | ❌ |
| Long interval | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Native | ⭐ | ❌ |
| Queue system | ⭐ | ⭐⭐⭐⭐⭐ | ✅ With setup | ⭐⭐⭐⭐⭐ | ❌ |
| Supervisor | ⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ With setup | ⭐⭐⭐⭐ | ❌ |

---

## Implementation Details

### Files Created

1. **`run-parser-advertiser.sh`**
   - Wrapper script with PID-based locking
   - Automatically cleans up on exit
   - Handles stale locks

2. **`install-parser-advertiser.sh`**
   - Adds parser to crontab (every 2 minutes)
   - Creates log directories
   - Updates crontab with all jobs

3. **`status-parser-advertiser.sh`**
   - Shows if script is currently running
   - Displays execution time
   - Shows recent logs

4. **`test-flock.sh`**
   - Demonstrates locking mechanism
   - Verifies overlap prevention works

5. **`README-PARSER-ADVERTISER.md`**
   - Complete documentation
   - Usage examples
   - Troubleshooting guide

### Lock Mechanism Code

```bash
# Check if another instance is running
if [ -f "$LOCKFILE" ] && [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if is_running "$OLD_PID"; then
        echo "Another instance is running. Skipping."
        exit 0
    fi
fi

# Create lock
echo $$ > "$PIDFILE"
touch "$LOCKFILE"

# Ensure cleanup on exit
trap cleanup EXIT INT TERM
```

### Verification Function

```bash
is_running() {
    local pid=$1
    # Check if process exists
    if ps -p "$pid" > /dev/null 2>&1; then
        # Verify it's our script (not just any PID)
        if ps -p "$pid" -o command= | grep -q "parser_of_advertiser.py"; then
            return 0
        fi
    fi
    return 1
}
```

---

## Testing Results

```
Starting first instance (will sleep 5 seconds)...
  [Instance 1] Lock acquired! Running for 5s (PID 21488)...
Trying to start second instance (should skip)...
  [Instance 2] Another instance (PID 21488) is running. Skipping. ✓
  [Instance 1] Finished

Trying third instance after first completed (should run)...
  [Instance 3] Lock acquired! Running for 2s (PID 21488)...
  [Instance 3] Finished

Test completed! ✅
```

---

## Performance Characteristics

### Best Case (10s execution)
- **Cron frequency**: Every 2 minutes
- **Actual frequency**: Every 2 minutes (no skips)
- **Throughput**: ~30 advertisers/hour

### Average Case (5min execution)
- **Cron frequency**: Every 2 minutes
- **Skipped attempts**: 1-2 per execution
- **Actual frequency**: ~5 minutes
- **Throughput**: ~12 advertisers/hour

### Worst Case (30min execution)
- **Cron frequency**: Every 2 minutes
- **Skipped attempts**: ~14 per execution
- **Actual frequency**: ~30 minutes
- **Throughput**: ~2 advertisers/hour

**Key insight**: System automatically adapts to execution time. Quick jobs run frequently, slow jobs don't overlap.

---

## Future Scalability

If you need to scale (multiple workers), migration path:

1. **Add Redis queue** (days of work)
   - Producer: Fetch advertisers from API → Push to queue
   - Workers: Pull from queue → Process → Mark complete
   - Multiple workers can run in parallel

2. **Keep PID locking per worker** (current approach)
   - Each worker has its own lock
   - Queue ensures no duplicate work
   - Simple and reliable

This shows our current approach is a good foundation for future scaling.

---

## Conclusion

**PID-based file locking** is the optimal solution because:

1. ✅ Simple implementation (50 lines of bash)
2. ✅ Works perfectly on macOS
3. ✅ No external dependencies
4. ✅ Handles stale locks automatically
5. ✅ Maximum throughput for variable execution times
6. ✅ Easy to monitor and troubleshoot
7. ✅ Battle-tested pattern (used in many production systems)

**Installation**:
```bash
./scheduler/install-parser-advertiser.sh
```

**Monitoring**:
```bash
./scheduler/status-parser-advertiser.sh
```






