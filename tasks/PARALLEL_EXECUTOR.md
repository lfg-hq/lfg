# Parallel Ticket Execution System

## Overview

This system enables **100+ concurrent project executions** while maintaining **sequential ticket execution within each project**. It uses a hybrid async approach with Redis for multi-machine distribution.

## Architecture

```
                         REDIS QUEUE (Shared)
    ┌─────────────────────────────────────────────────────────────┐
    │  Tasks: [(proj_1, [t1,t2]), (proj_2, [t3,t4]), ...]        │
    └───────────────────────────┬─────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
         ┌────────────┐  ┌────────────┐  ┌────────────┐
         │ Machine 1  │  │ Machine 2  │  │ Machine N  │
         │            │  │            │  │            │
         │ Async      │  │ Async      │  │ Async      │
         │ Executor   │  │ Executor   │  │ Executor   │
         │            │  │            │  │            │
         │ Semaphore  │  │ Semaphore  │  │ Semaphore  │
         │ per project│  │ per project│  │ per project│
         └────────────┘  └────────────┘  └────────────┘

         Each machine: 100+ concurrent projects, ~1-2GB RAM
```

## Key Guarantees

| Requirement | Mechanism |
|-------------|-----------|
| Sequential within project | `asyncio.Semaphore(1)` per project_id |
| Parallel across projects | `asyncio.gather()` runs all concurrently |
| Multi-machine scaling | Redis queue for task distribution |
| No duplicate project execution | Redis distributed lock at dispatch time |

## How It Works

### Execution Timeline Example

```
Time →  0s      10s     20s     30s     40s     50s     60s
        │       │       │       │       │       │       │
Proj 1: ████████████████████████████████████████████████████
        │Ticket1 (30s)  │Ticket2 (20s)  │Ticket3 (10s) │
        │               │               │              │
Proj 2: ████████████████████████████████
        │Ticket4 (20s)  │Ticket5 (15s)  │
        │               │               │
Proj 3: ████████████████████████████████████████████
        │Ticket6 (25s)          │Ticket7 (20s)      │

✓ Projects run in PARALLEL (all start at 0s)
✓ Tickets within each project run SEQUENTIALLY (T2 waits for T1)
```

### Execution Flow

```
1. API receives ticket execution request
   ↓
2. dispatch_tickets() pushes to Redis queue
   ↓
3. ExecutorService.run() pops from queue (any machine)
   ↓
4. Acquires distributed lock for project
   ↓
5. AsyncTicketExecutor.execute_project_batch()
   ↓
6. For each ticket: acquire project semaphore (ensures sequential)
   ↓
7. Calls original execute_ticket_implementation() in thread pool
   ↓
8. Releases semaphore, moves to next ticket
   ↓
9. Releases distributed lock when batch complete
```

## Components

### 1. AsyncTicketExecutor (`async_executor.py`)

Core executor with per-project semaphores:

```python
from tasks.async_executor import get_executor

executor = get_executor()

# Execute single ticket (with project serialization)
result = await executor.execute_ticket(ticket_id, project_id, conversation_id)

# Execute batch for one project (sequential)
result = await executor.execute_project_batch(project_id, ticket_ids, conversation_id)

# Execute multiple projects in parallel
results = await executor.execute_multi_project({
    project_id_1: {'ticket_ids': [1, 2, 3], 'conversation_id': 100},
    project_id_2: {'ticket_ids': [4, 5], 'conversation_id': 101},
})
```

### 2. ExecutorService (`executor_service.py`)

Long-running Redis consumer:

```bash
# Start the executor service
python manage.py run_executor
```

The service:
- Connects to Redis and listens for tasks
- Acquires distributed locks before execution
- Processes tasks via AsyncTicketExecutor
- Handles graceful shutdown on SIGTERM/SIGINT

### 3. Dispatch Utilities (`dispatch.py`)

Queue management functions:

```python
from tasks.dispatch import (
    dispatch_tickets,
    remove_from_queue,
    get_queue_length,
    get_executing_projects,
    get_project_queue_info
)

# Queue tickets for execution
dispatch_tickets(project_id=1, ticket_ids=[1, 2, 3], conversation_id=100)

# Check queue status
length = get_queue_length()
executing = get_executing_projects()

# Remove ticket from queue
removed = remove_from_queue(project_id=1, ticket_id=2)
```

## Configuration

### Environment Variables

```bash
# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Executor settings
MAX_CONCURRENT_PROJECTS=200
```

### Django Settings

```python
# In LFG/settings.py
ASYNC_EXECUTOR = {
    'max_concurrent_projects': int(os.getenv('MAX_CONCURRENT_PROJECTS', 200)),
    'redis': {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', 6379)),
        'db': int(os.getenv('REDIS_DB', 0)),
        'password': os.getenv('REDIS_PASSWORD', None),
    }
}
```

## Deployment

### Single Machine

```bash
# Start the executor service
python manage.py run_executor
```

### Multi-Machine (Bare Metal)

1. Install the application on each machine
2. Configure Redis connection to shared Redis server
3. Start the executor service on each machine

```bash
# Machine 1
MAX_CONCURRENT_PROJECTS=200 python manage.py run_executor

# Machine 2
MAX_CONCURRENT_PROJECTS=200 python manage.py run_executor

# Machine 3
MAX_CONCURRENT_PROJECTS=200 python manage.py run_executor
```

Each machine automatically pulls from the shared Redis queue.

### Systemd Service

Create `/etc/systemd/system/lfg-executor.service`:

```ini
[Unit]
Description=LFG Async Ticket Executor
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/app
Environment="MAX_CONCURRENT_PROJECTS=200"
ExecStart=/app/venv/bin/python manage.py run_executor
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable lfg-executor
sudo systemctl start lfg-executor
```

## Resource Requirements

| Component | RAM | CPU | Notes |
|-----------|-----|-----|-------|
| Executor Service | 1-2 GB | 2 cores | Per machine, handles 200 projects |
| Redis | 2-4 GB | 2 cores | Shared, handles queue + locks |
| PostgreSQL | 8-16 GB | 4 cores | Shared database |

**Scaling:**
- 100 concurrent projects: ~2GB RAM (single machine)
- 500 concurrent projects: 3 machines × 2GB = ~6GB total
- 1000 concurrent projects: 5 machines × 2GB = ~10GB total

## Queue Status UI

The ticket list shows queue status for each ticket:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TICKET                           STATUS    QUEUE          PRIORITY   ACTIONS │
├──────────────────────────────────────────────────────────────────────────────┤
│ Project Setup & Configuration    Done      -              High               │
│ UI Polish & Responsiveness       Open      ⏳ Queued (#3)  Low       [Cancel]│
│ New Feature Implementation       Open      🔄 Executing    High      [Stop]  │
│ Bug Fix Task                     Open      -              Medium    [Queue]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Queue Status Values

- `-` or empty: Not queued
- `⏳ Queued (#N)`: In queue at position N
- `🔄 Executing`: Currently being processed

### API Endpoints

```bash
# Queue a ticket
POST /api/projects/{project_id}/tickets/{ticket_id}/queue-execution/

# Cancel a queued ticket
POST /api/projects/{project_id}/tickets/{ticket_id}/cancel-queue/

# Get queue status for a project
GET /api/projects/{project_id}/tickets/queue-status/?project_id={id}

# Get executor status (admin)
GET /api/executor/status/
```

## Monitoring

### Check Executor Status

```python
from tasks.dispatch import get_queue_length, get_executing_projects

print(f"Queue length: {get_queue_length()}")
print(f"Executing projects: {get_executing_projects()}")
```

### Redis Keys

```bash
# List all keys
redis-cli KEYS "lfg:*"

# Check queue length
redis-cli LLEN "lfg:ticket_execution_queue"

# Check executing projects
redis-cli KEYS "lfg:project_executing:*"

# View queue contents
redis-cli LRANGE "lfg:ticket_execution_queue" 0 -1
```

## Troubleshooting

### Stuck Project Lock

If a project lock is stuck (executor crashed), force release it:

```python
from tasks.dispatch import get_redis_client

client = get_redis_client()
client.delete(f"lfg:project_executing:{project_id}")
```

### Clear All Queued Tasks

```bash
redis-cli DEL "lfg:ticket_execution_queue"
```

### Check Executor Logs

```bash
# Systemd logs
journalctl -u lfg-executor -f

# Or if running directly
python manage.py run_executor 2>&1 | tee executor.log
```

## Files

| File | Description |
|------|-------------|
| `tasks/async_executor.py` | Core async executor with semaphores |
| `tasks/executor_service.py` | Redis consumer service |
| `tasks/dispatch.py` | Task dispatch + queue management |
| `tasks/management/commands/run_executor.py` | Django management command |
| `tasks/views.py` | Monitoring API endpoints |
| `tasks/PARALLEL_EXECUTOR.md` | This documentation |

## Unchanged Files

The following files remain **unchanged**:
- `tasks/task_definitions.py` - Original execution functions
- `tasks/task_manager.py` - Django-Q task manager (still available for other tasks)
