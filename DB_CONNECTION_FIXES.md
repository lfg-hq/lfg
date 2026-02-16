# Database Connection Leak Fixes

## Problem Summary

Your Django application was exhausting PostgreSQL database connections, resulting in:
```
django.db.utils.OperationalError: connection to server at "localhost" (::1), port 5432 failed: FATAL: sorry, too many clients already
```

## Root Causes Identified

### 1. **ASGI + `database_sync_to_async` Connection Leaks**
- **Issue**: WebSocket consumers (`chat/consumers.py` and `development/views_terminal.py`) use `@database_sync_to_async` decorators extensively (~40+ instances)
- **Problem**: In ASGI environments, Django's thread pool doesn't automatically close database connections after each operation
- **Impact**: Each WebSocket connection could leave multiple database connections open

### 2. **No Connection Lifecycle Management**
- **Issue**: Missing `close_old_connections()` calls in async code
- **Problem**: Stale connections accumulate over time
- **Impact**: Connection pool exhaustion during high traffic

### 3. **CONN_MAX_AGE Without Proper Limits**
- **Issue**: `CONN_MAX_AGE=600` (10 minutes) without connection pool limits
- **Problem**: Persistent connections are good for performance but amplify leaks
- **Impact**: Leaked connections stay open for 10 minutes each

## Fixes Applied

### 1. Database Settings Updates (`LFG/settings.py`)

```python
# Before
'CONN_MAX_AGE': 600

# After
'CONN_MAX_AGE': 300,  # Reduced to 5 minutes
'OPTIONS': {
    'connect_timeout': 10,
    'options': '-c statement_timeout=30000',  # 30 second query timeout
},
'CONN_HEALTH_CHECKS': False,  # Explicit connection management
```

**Benefits**:
- Reduced connection lifetime from 10 to 5 minutes
- Added query timeout to prevent runaway queries
- Explicit connection management instead of automatic health checks

### 2. WebSocket Consumer Fixes

#### **chat/consumers.py**
Added connection cleanup at critical lifecycle points:

```python
# On connect
async def connect(self):
    await database_sync_to_async(close_old_connections)()
    # ... rest of connection logic

# On disconnect
async def disconnect(self, close_code):
    # ... cleanup logic
    finally:
        await database_sync_to_async(close_old_connections)()

# On message receive
async def receive(self, text_data):
    await database_sync_to_async(close_old_connections)()
    # ... message handling

# Before and after AI generation
async def generate_ai_response(self, ...):
    await database_sync_to_async(close_old_connections)()
    # ... AI generation logic
    # After completion:
    await database_sync_to_async(close_old_connections)()
```

#### **development/views_terminal.py**
Applied same fixes to `TerminalConsumer`:
- Connection cleanup on connect/disconnect
- Periodic cleanup during message receive

**Benefits**:
- Automatic cleanup of stale connections
- Prevents connection accumulation during long-running WebSocket sessions
- Ensures connections are closed even when errors occur

## Additional Recommendations

### 1. Install PgBouncer (Recommended for Production)

PgBouncer is a lightweight connection pooler for PostgreSQL that sits between your application and database:

```bash
# Install PgBouncer
sudo apt-get install pgbouncer  # Ubuntu/Debian
# or
brew install pgbouncer  # macOS

# Configure /etc/pgbouncer/pgbouncer.ini
[databases]
lfg_prod = host=localhost port=5432 dbname=lfg_prod

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 100
default_pool_size = 20
reserve_pool_size = 5
reserve_pool_timeout = 3
```

Then update Django settings:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': '127.0.0.1',
        'PORT': '6432',  # PgBouncer port instead of 5432
        # ... other settings
    }
}
```

### 2. Monitor Connection Usage

Add monitoring to track database connections:

```python
# In a management command or monitoring script
from django.db import connection

def check_db_connections():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT count(*) as total,
                   count(*) FILTER (WHERE state = 'active') as active,
                   count(*) FILTER (WHERE state = 'idle') as idle
            FROM pg_stat_activity
            WHERE datname = current_database()
        """)
        stats = cursor.fetchone()
        print(f"Total: {stats[0]}, Active: {stats[1]}, Idle: {stats[2]}")
```

### 3. Increase PostgreSQL max_connections

Edit `postgresql.conf`:
```
max_connections = 200  # Increase from default 100
```

Then restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 4. Use Django-Q or Celery Connection Handling

Your Q_CLUSTER configuration should also handle connections properly:

```python
Q_CLUSTER = {
    # ... existing config
    'orm': 'default',
    'sync': False,
    # Add this:
    'catch_up': False,  # Don't try to catch up on missed tasks
    'max_attempts': 1,
}
```

## Testing the Fixes

### 1. Check Current Connection Count

```bash
# Before starting the app
psql -U postgres -d lfg_prod -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lfg_prod';"

# Start the app and monitor
watch -n 5 "psql -U postgres -d lfg_prod -c \"SELECT count(*) FROM pg_stat_activity WHERE datname='lfg_prod';\""
```

### 2. Stress Test WebSocket Connections

```python
# test_websocket_connections.py
import asyncio
import websockets

async def test_connection(url, num):
    async with websockets.connect(url) as ws:
        await ws.send('{"type": "test"}')
        response = await ws.recv()
        print(f"Connection {num}: {response}")
        await asyncio.sleep(30)  # Keep connection open

async def stress_test():
    url = "ws://localhost:8000/ws/chat/"
    tasks = [test_connection(url, i) for i in range(50)]
    await asyncio.gather(*tasks)

asyncio.run(stress_test())
```

### 3. Monitor Application Logs

Look for connection errors or warnings:
```bash
tail -f logs/app.log | grep -i "connection\|database"
```

## Expected Results

After these fixes:
- **Before**: Connections would accumulate and exhaust the pool within hours
- **After**: Connections should stay under control, typically 10-30 active connections
- **WebSocket sessions**: Should not leave connections open after disconnect
- **Long-running tasks**: Should periodically close stale connections

## Rollback Plan

If issues occur, you can rollback by:
1. Reverting `CONN_MAX_AGE` back to 600 or setting to 0 (no persistent connections)
2. Removing `close_old_connections()` calls if they cause performance issues
3. Setting `CONN_HEALTH_CHECKS=True` to let Django manage connections automatically

## Support Commands

```bash
# Kill all idle connections (emergency use only)
psql -U postgres -d lfg_prod -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND datname='lfg_prod' AND state_change < now() - interval '5 minutes';"

# View connection details
psql -U postgres -d lfg_prod -c "SELECT pid, usename, application_name, client_addr, state, state_change FROM pg_stat_activity WHERE datname='lfg_prod';"
```

## Performance Considerations

The fixes should have minimal performance impact:
- `close_old_connections()` is very fast (< 1ms)
- Called at strategic points (not in hot loops)
- Prevents performance degradation from connection exhaustion
- May slightly increase database connection overhead, but prevents complete failures

---

**Date Fixed**: 2025-11-12
**Files Modified**:
- `LFG/settings.py`
- `chat/consumers.py`
- `development/views_terminal.py`
