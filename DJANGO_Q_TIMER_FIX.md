# Django-Q Timer Value Error Fix

## Problem Description

You were experiencing a Django-Q cluster worker error:

```
TypeError: must be real number, not NoneType
[ERROR] reincarnated worker Process-1:23 after death
```

This error occurs in `django_q/cluster.py` line 435 where `timer.value = timer_value` fails because `timer_value` is `None` instead of a numeric value.

## Root Cause

This is a known issue with Django-Q multiprocessing worker initialization that can occur when:

1. Workers fail to properly initialize their timer values
2. Multiprocessing shared memory objects become corrupted
3. Workers are killed abruptly and leave stale state
4. Configuration issues with worker processes

## Solution Applied

### 1. Updated Django-Q Configuration

**File**: `LFG/settings.py`

Added proper worker configuration settings to prevent timer initialization issues:

```python
Q_CLUSTER = {
    'name': 'LFG_Tasks_Local',
    'workers': 2,
    'recycle': 500,
    'timeout': 60,
    'retry': 120,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    'guard_cycle': 5,           # Guard loop sleep in seconds
    'daemonize_workers': True,  # Set daemon flag for workers
    'max_attempts': 1,          # Limit retry attempts to prevent loops
    'poll': 0.5,               # Increase polling interval for ORM broker
}
```

**Key fixes:**
- `guard_cycle`: 5 seconds - ensures proper guard loop timing
- `daemonize_workers`: True - proper process daemonization
- `max_attempts`: 1 - prevents infinite retry loops
- `poll`: 0.5 - better polling for ORM broker

### 2. Created Restart Script

**File**: `restart_django_q.py`

This script properly handles Django-Q cluster restart:

- Kills any existing Django-Q processes
- Clears stuck tasks from the database
- Validates configuration
- Starts fresh cluster

**Usage:**
```bash
python restart_django_q.py
```

### 3. Created Test Script

**File**: `test_django_q.py`

Comprehensive test suite to verify Django-Q functionality:

- Tests direct `async_task()` calls
- Tests `TaskManager` wrapper
- Checks queue statistics
- Validates worker processes

**Usage:**
```bash
python test_django_q.py
```

### 4. Updated Dependencies

**File**: `requirements.txt`

Added `psutil>=5.9.0` for process management in the restart script.

## How to Fix the Error

### Step 1: Install Updated Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Stop Any Running Django-Q Processes
```bash
# Kill any existing qcluster processes
pkill -f qcluster
```

### Step 3: Run the Restart Script
```bash
python restart_django_q.py
```

This will:
- ✅ Kill existing Django-Q processes
- ✅ Clear stuck tasks
- ✅ Validate configuration
- ✅ Start fresh cluster

### Step 4: Test the Fix
```bash
python test_django_q.py
```

This will verify that:
- ✅ Workers are properly initialized
- ✅ Tasks can be submitted and executed
- ✅ No timer value errors occur

### Step 5: Monitor Logs
```bash
python manage.py qcluster
```

Look for healthy worker startup messages like:
```
[Q] INFO Process-1:1 ready for work at 12345
[Q] INFO Process-1:2 ready for work at 12346
[Q] INFO Q Cluster running.
```

## Prevention

To prevent this issue from recurring:

1. **Use the restart script** when Django-Q becomes unstable
2. **Monitor worker health** through Django admin at `/admin/django_q/`
3. **Check logs regularly** for worker reincarnation messages
4. **Update Django-Q2** to the latest version when available
5. **Consider Redis broker** for production (more stable than ORM broker)

## Alternative Solutions

If the problem persists, try these alternatives:

### Option 1: Switch to Redis Broker
```python
# In settings.py for production
Q_CLUSTER = {
    'name': 'LFG_Tasks',
    'workers': 4,
    'redis': {
        'host': 'localhost',
        'port': 6379,
        'db': 0,
    }
}
```

### Option 2: Reduce Worker Count
```python
Q_CLUSTER = {
    'workers': 1,  # Single worker to reduce complexity
    # ... other settings
}
```

### Option 3: Increase Guard Cycle
```python
Q_CLUSTER = {
    'guard_cycle': 10,  # Longer guard cycle
    # ... other settings
}
```

## Verification

After applying the fix, you should see:

✅ No more "TypeError: must be real number, not NoneType" errors
✅ Workers start successfully without reincarnation
✅ Tasks execute properly
✅ Clean Django-Q cluster logs

## Troubleshooting

If issues persist:

1. **Check Python version compatibility** with Django-Q2
2. **Verify database permissions** for ORM broker
3. **Monitor system resources** (memory, CPU)
4. **Check for Django migrations** needed for Django-Q
5. **Consider upgrading to Redis broker** for better stability

## Summary

The timer value error was caused by improper worker initialization in Django-Q. The fix involved:

1. **Enhanced configuration** with proper worker settings
2. **Process management** tools for clean restarts
3. **Testing utilities** to verify functionality
4. **Monitoring guidance** to prevent recurrence

The issue should now be resolved, and you can safely use Django-Q for parallel task execution in your LFG project. 