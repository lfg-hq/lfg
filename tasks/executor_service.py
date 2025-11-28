"""
Redis-backed Executor Service.

Long-running service that:
1. Consumes ticket execution tasks from Redis queue
2. Acquires distributed locks to prevent duplicate execution
3. Runs tasks via AsyncTicketExecutor
4. Handles graceful shutdown

Usage:
    python manage.py run_executor

Or programmatically:
    from tasks.executor_service import main
    asyncio.run(main())
"""
import asyncio
import json
import logging
import signal
import os
from typing import Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)

# Redis queue and lock keys
QUEUE_KEY = "lfg:ticket_execution_queue"
LOCK_PREFIX = "lfg:project_executing:"
LOCK_TTL = 7200  # 2 hours


class ExecutorService:
    """
    Long-running service that consumes ticket execution tasks from Redis.

    Features:
    - Distributed locking prevents same project executing on multiple machines
    - Graceful shutdown on SIGTERM/SIGINT
    - Automatic reconnection on Redis failures
    - Concurrent task processing with back-pressure
    """

    def __init__(self, max_concurrent_tasks: int = 50):
        """
        Initialize the executor service.

        Args:
            max_concurrent_tasks: Max tasks processing simultaneously
        """
        self.redis = None
        self.executor = None
        self.running = True
        self.max_concurrent_tasks = max_concurrent_tasks
        self._active_tasks: Set[asyncio.Task] = set()
        self._task_semaphore = asyncio.Semaphore(max_concurrent_tasks)

        logger.info(
            f"[SERVICE] Initialized with max_concurrent_tasks={max_concurrent_tasks}"
        )

    async def connect(self):
        """Connect to Redis."""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            logger.error(
                "[SERVICE] redis.asyncio not available. "
                "Install with: pip install redis[hiredis]"
            )
            raise

        # Get Redis config from Django settings
        import django
        django.setup()

        from django.conf import settings

        redis_config = getattr(settings, 'Q_CLUSTER', {}).get('redis', {})

        host = redis_config.get('host', 'localhost')
        port = redis_config.get('port', 6379)
        db = redis_config.get('db', 0)
        password = redis_config.get('password')

        # Build URL
        if password:
            redis_url = f"redis://:{password}@{host}:{port}/{db}"
        else:
            redis_url = f"redis://{host}:{port}/{db}"

        self.redis = await aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )

        # Test connection
        await self.redis.ping()
        logger.info(f"[SERVICE] Connected to Redis at {host}:{port}/{db}")

        # Initialize executor
        from tasks.async_executor import get_executor
        self.executor = get_executor()

    async def acquire_project_lock(self, project_id: int) -> bool:
        """
        Acquire distributed lock for project execution.

        Uses Redis SETNX for atomic lock acquisition with TTL.

        Returns:
            True if lock acquired, False if project already locked
        """
        lock_key = f"{LOCK_PREFIX}{project_id}"
        lock_value = f"{os.getpid()}:{datetime.now().isoformat()}"

        acquired = await self.redis.set(
            lock_key,
            lock_value,
            nx=True,  # Only set if not exists
            ex=LOCK_TTL  # Auto-expire after 2 hours
        )

        if acquired:
            logger.info(f"[SERVICE] Acquired lock for project {project_id}")
        else:
            logger.debug(f"[SERVICE] Project {project_id} already locked")

        return bool(acquired)

    async def release_project_lock(self, project_id: int):
        """Release distributed lock for project."""
        lock_key = f"{LOCK_PREFIX}{project_id}"
        await self.redis.delete(lock_key)
        logger.info(f"[SERVICE] Released lock for project {project_id}")

    async def extend_project_lock(self, project_id: int):
        """Extend lock TTL for long-running executions."""
        lock_key = f"{LOCK_PREFIX}{project_id}"
        await self.redis.expire(lock_key, LOCK_TTL)
        logger.debug(f"[SERVICE] Extended lock for project {project_id}")

    async def process_task(self, task_data: dict):
        """
        Process a single task from the queue.

        Args:
            task_data: Dict with project_id, ticket_ids, conversation_id
        """
        project_id = task_data['project_id']
        ticket_ids = task_data['ticket_ids']
        conversation_id = task_data.get('conversation_id')

        logger.info(
            f"[SERVICE] Processing task: project={project_id}, "
            f"tickets={ticket_ids}"
        )

        # Acquire distributed lock
        if not await self.acquire_project_lock(project_id):
            # Project is being executed elsewhere - requeue
            logger.warning(
                f"[SERVICE] Project {project_id} locked, requeueing task"
            )
            await self.redis.rpush(QUEUE_KEY, json.dumps(task_data))
            await asyncio.sleep(5)  # Wait before retry
            return

        try:
            # Execute the batch
            result = await self.executor.execute_project_batch(
                project_id,
                ticket_ids,
                conversation_id
            )

            # Log result
            completed = result.get('completed', 0)
            total = result.get('total', 0)
            logger.info(
                f"[SERVICE] Project {project_id} completed: "
                f"{completed}/{total} tickets succeeded"
            )

        except Exception as e:
            logger.error(
                f"[SERVICE] Error processing project {project_id}: {e}",
                exc_info=True
            )
        finally:
            # Always release lock
            await self.release_project_lock(project_id)
            # Cleanup executor resources for this project
            self.executor.cleanup_project(project_id)

    async def _task_wrapper(self, task_data: dict):
        """Wrapper to handle task completion and semaphore release."""
        try:
            async with self._task_semaphore:
                await self.process_task(task_data)
        except Exception as e:
            logger.error(f"[SERVICE] Task wrapper error: {e}", exc_info=True)

    async def run(self):
        """
        Main service loop - consume tasks from Redis queue.

        Runs until shutdown is requested via SIGTERM/SIGINT.
        """
        await self.connect()

        logger.info("[SERVICE] Executor service started, waiting for tasks...")
        logger.info(f"[SERVICE] Queue key: {QUEUE_KEY}")

        consecutive_errors = 0
        max_consecutive_errors = 10

        while self.running:
            try:
                # Blocking pop with timeout (allows checking self.running)
                result = await self.redis.blpop(QUEUE_KEY, timeout=5)

                if result:
                    _, task_json = result
                    consecutive_errors = 0  # Reset error count

                    try:
                        task_data = json.loads(task_json)

                        # Validate task data
                        if not task_data.get('project_id') or not task_data.get('ticket_ids'):
                            logger.warning(
                                f"[SERVICE] Invalid task data: {task_data}"
                            )
                            continue

                        # Process in background (with semaphore for back-pressure)
                        task = asyncio.create_task(
                            self._task_wrapper(task_data),
                            name=f"project_{task_data['project_id']}"
                        )
                        self._active_tasks.add(task)
                        task.add_done_callback(self._active_tasks.discard)

                    except json.JSONDecodeError as e:
                        logger.error(f"[SERVICE] Invalid JSON in queue: {e}")

            except asyncio.CancelledError:
                logger.info("[SERVICE] Shutdown requested via cancel")
                break

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"[SERVICE] Error in main loop ({consecutive_errors}): {e}",
                    exc_info=True
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"[SERVICE] Too many consecutive errors, stopping"
                    )
                    break

                # Exponential backoff
                await asyncio.sleep(min(2 ** consecutive_errors, 60))

        await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown - wait for active tasks and cleanup."""
        logger.info("[SERVICE] Shutting down...")
        self.running = False

        # Wait for active tasks to complete (with timeout)
        if self._active_tasks:
            logger.info(
                f"[SERVICE] Waiting for {len(self._active_tasks)} active tasks..."
            )
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=300  # 5 minute timeout
                )
            except asyncio.TimeoutError:
                logger.warning("[SERVICE] Timeout waiting for tasks, forcing shutdown")
                for task in self._active_tasks:
                    task.cancel()

        # Close Redis connection
        if self.redis:
            await self.redis.close()
            logger.info("[SERVICE] Redis connection closed")

        # Shutdown executor
        if self.executor:
            await self.executor.shutdown()

        logger.info("[SERVICE] Shutdown complete")

    def request_shutdown(self):
        """Request graceful shutdown (called from signal handler)."""
        logger.info("[SERVICE] Shutdown requested")
        self.running = False


async def main():
    """Entry point for executor service."""
    # Setup Django
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
    django.setup()

    service = ExecutorService()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        service.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Run the service
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
