"""
Async Ticket Executor with per-project semaphores.

Guarantees:
- Sequential execution within each project (via Semaphore(1) per project)
- Parallel execution across different projects (via asyncio)
- Efficient I/O-bound handling (async/await for API calls, SSH, etc.)

Usage:
    from tasks.async_executor import get_executor

    executor = get_executor()
    result = await executor.execute_ticket(ticket_id, project_id, conversation_id)
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class AsyncTicketExecutor:
    """
    Manages concurrent ticket execution with per-project serialization.

    Architecture:
    - Global semaphore limits total concurrent executions (prevents overload)
    - Per-project semaphore (limit=1) ensures sequential execution within project
    - ThreadPoolExecutor runs sync code in background threads
    """

    def __init__(self, max_concurrent_projects: int = 200):
        """
        Initialize the executor.

        Args:
            max_concurrent_projects: Maximum projects executing simultaneously
        """
        self.max_concurrent = max_concurrent_projects
        self.project_semaphores: Dict[int, asyncio.Semaphore] = {}
        self.global_semaphore = asyncio.Semaphore(max_concurrent_projects)
        self._lock = asyncio.Lock()
        self._thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_projects)

        logger.info(f"[EXECUTOR] Initialized with max_concurrent={max_concurrent_projects}")

    async def get_project_semaphore(self, project_id: int) -> asyncio.Semaphore:
        """
        Get or create a semaphore for a project.

        Each project gets a Semaphore(1), meaning only ONE ticket
        can execute at a time for that project.
        """
        async with self._lock:
            if project_id not in self.project_semaphores:
                self.project_semaphores[project_id] = asyncio.Semaphore(1)
                logger.debug(f"[EXECUTOR] Created semaphore for project {project_id}")
            return self.project_semaphores[project_id]

    async def execute_ticket(
        self,
        ticket_id: int,
        project_id: int,
        conversation_id: int
    ) -> Dict[str, Any]:
        """
        Execute a single ticket with project-level serialization.

        This method:
        1. Acquires global semaphore (limits total concurrent)
        2. Acquires project semaphore (ensures only 1 per project)
        3. Runs the sync execute_ticket_implementation in thread pool
        4. Returns result

        Args:
            ticket_id: The ticket to execute
            project_id: The project database ID
            conversation_id: The conversation ID for notifications

        Returns:
            Dict with execution result
        """
        from tasks.dispatch import update_ticket_queue_status

        project_sem = await self.get_project_semaphore(project_id)

        async with self.global_semaphore:  # Limit total concurrent
            async with project_sem:  # Only 1 per project at a time
                logger.info(
                    f"[EXECUTOR] Starting ticket #{ticket_id} "
                    f"(project={project_id}, conv={conversation_id})"
                )

                # Update status to executing
                try:
                    update_ticket_queue_status(ticket_id, 'executing')
                except Exception as e:
                    logger.warning(f"[EXECUTOR] Failed to update queue status: {e}")

                try:
                    # Import here to avoid circular imports
                    from tasks.task_definitions import execute_ticket_implementation

                    # Run sync function in thread pool (doesn't block event loop)
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        self._thread_pool,
                        execute_ticket_implementation,
                        ticket_id,
                        project_id,
                        conversation_id
                    )

                    logger.info(
                        f"[EXECUTOR] Completed ticket #{ticket_id}: "
                        f"status={result.get('status')}"
                    )
                    return result

                except Exception as e:
                    logger.error(
                        f"[EXECUTOR] Error executing ticket #{ticket_id}: {e}",
                        exc_info=True
                    )
                    return {
                        'status': 'error',
                        'ticket_id': ticket_id,
                        'error': str(e)
                    }
                finally:
                    # Update status to not queued
                    try:
                        update_ticket_queue_status(ticket_id, 'none')
                    except Exception as e:
                        logger.warning(f"[EXECUTOR] Failed to clear queue status: {e}")

    async def execute_project_batch(
        self,
        project_id: int,
        ticket_ids: List[int],
        conversation_id: int
    ) -> Dict[str, Any]:
        """
        Execute all tickets for a project sequentially.

        Tickets are processed one-by-one in order. If a ticket fails with
        'error' status, execution stops (remaining tickets are skipped).

        Args:
            project_id: The project database ID
            ticket_ids: List of ticket IDs to execute in order
            conversation_id: The conversation ID for notifications

        Returns:
            Dict with batch results
        """
        logger.info(
            f"[EXECUTOR] Starting batch for project {project_id}: "
            f"{len(ticket_ids)} tickets"
        )

        results = []
        completed = 0

        for i, ticket_id in enumerate(ticket_ids):
            logger.info(
                f"[EXECUTOR] Project {project_id}: "
                f"ticket {i+1}/{len(ticket_ids)} (#{ticket_id})"
            )

            result = await self.execute_ticket(ticket_id, project_id, conversation_id)
            results.append(result)

            if result.get('status') == 'success':
                completed += 1
            elif result.get('status') == 'error':
                # Stop on error - remaining tickets are skipped
                logger.warning(
                    f"[EXECUTOR] Project {project_id}: stopping batch due to error "
                    f"on ticket #{ticket_id}"
                )
                break

        batch_result = {
            'project_id': project_id,
            'total': len(ticket_ids),
            'completed': completed,
            'failed': len(results) - completed,
            'skipped': len(ticket_ids) - len(results),
            'results': results
        }

        logger.info(
            f"[EXECUTOR] Batch complete for project {project_id}: "
            f"{completed}/{len(ticket_ids)} succeeded"
        )

        return batch_result

    async def execute_multi_project(
        self,
        project_batches: Dict[int, Dict]
    ) -> Dict[int, Any]:
        """
        Execute tickets for multiple projects in parallel.

        Each project's tickets run sequentially (due to per-project semaphore),
        but different projects run in parallel.

        Args:
            project_batches: Dict mapping project_id to batch config:
                {
                    project_id: {
                        'ticket_ids': [1, 2, 3],
                        'conversation_id': 100
                    },
                    ...
                }

        Returns:
            Dict mapping project_id to batch result
        """
        logger.info(
            f"[EXECUTOR] Starting multi-project execution: "
            f"{len(project_batches)} projects"
        )

        # Create tasks for all projects
        tasks = []
        for project_id, batch in project_batches.items():
            task = asyncio.create_task(
                self.execute_project_batch(
                    project_id,
                    batch['ticket_ids'],
                    batch['conversation_id']
                ),
                name=f"project_{project_id}"
            )
            tasks.append((project_id, task))

        # Wait for all projects to complete
        results = {}
        for project_id, task in tasks:
            try:
                results[project_id] = await task
            except Exception as e:
                logger.error(
                    f"[EXECUTOR] Project {project_id} failed: {e}",
                    exc_info=True
                )
                results[project_id] = {
                    'status': 'error',
                    'project_id': project_id,
                    'error': str(e)
                }

        # Summary
        total_completed = sum(r.get('completed', 0) for r in results.values())
        total_tickets = sum(r.get('total', 0) for r in results.values())

        logger.info(
            f"[EXECUTOR] Multi-project complete: "
            f"{len(results)} projects, {total_completed}/{total_tickets} tickets"
        )

        return results

    def cleanup_project(self, project_id: int):
        """
        Remove semaphore for a completed project.

        Call this after a project batch completes to free memory.
        """
        removed = self.project_semaphores.pop(project_id, None)
        if removed:
            logger.debug(f"[EXECUTOR] Cleaned up semaphore for project {project_id}")

    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            'max_concurrent': self.max_concurrent,
            'active_projects': len(self.project_semaphores),
            'project_ids': list(self.project_semaphores.keys())
        }

    async def shutdown(self):
        """Graceful shutdown - wait for running tasks and cleanup."""
        logger.info("[EXECUTOR] Shutting down...")
        self._thread_pool.shutdown(wait=True)
        self.project_semaphores.clear()
        logger.info("[EXECUTOR] Shutdown complete")


# Global executor instance (singleton)
_executor: Optional[AsyncTicketExecutor] = None


def get_executor(max_concurrent: int = 200) -> AsyncTicketExecutor:
    """
    Get the global executor instance.

    Creates the executor on first call with specified max_concurrent.
    Subsequent calls return the same instance.

    Args:
        max_concurrent: Max concurrent projects (only used on first call)

    Returns:
        AsyncTicketExecutor instance
    """
    global _executor
    if _executor is None:
        from django.conf import settings

        # Try to get from settings, fall back to parameter
        executor_config = getattr(settings, 'ASYNC_EXECUTOR', {})
        max_projects = executor_config.get('max_concurrent_projects', max_concurrent)

        _executor = AsyncTicketExecutor(max_concurrent_projects=max_projects)
    return _executor


def reset_executor():
    """Reset the global executor (mainly for testing)."""
    global _executor
    if _executor:
        asyncio.run(_executor.shutdown())
    _executor = None
