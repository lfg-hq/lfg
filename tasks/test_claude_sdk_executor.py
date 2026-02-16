#!/usr/bin/env python
"""
Test script for the Claude Agent SDK ticket executor.
This script demonstrates how to use the new implementation.
"""

import os
import sys
import django
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from tasks.claude_agent_ticket_executor import (
    TicketExecutor,
    execute_ticket_implementation_claude_sdk,
    batch_execute_tickets_claude_sdk_sync
)
from projects.models import Project, ProjectTicket

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_single_ticket_execution():
    """Test executing a single ticket."""
    print("\n" + "="*60)
    print("Testing Single Ticket Execution with Claude SDK")
    print("="*60)

    try:
        # Find a test ticket (you'll need to adjust these IDs)
        ticket = ProjectTicket.objects.filter(status='open', role='agent').first()

        if not ticket:
            print("No open agent tickets found. Please create a test ticket first.")
            return

        project = ticket.project
        conversation_id = 1  # Use a test conversation ID

        print(f"\nExecuting ticket #{ticket.id}: {ticket.name}")
        print(f"Project: {project.name}")
        print(f"Priority: {ticket.priority}")
        print(f"Description: {ticket.description[:100]}...")

        # Execute the ticket
        result = execute_ticket_implementation_claude_sdk(
            ticket_id=ticket.id,
            project_id=project.id,
            conversation_id=conversation_id,
            max_execution_time=120  # 2 minutes for testing
        )

        # Display results
        print(f"\nExecution completed with status: {result['status']}")

        if result['status'] == 'success':
            print(f"✅ Success!")
            print(f"  - Execution time: {result.get('execution_time', 'N/A')}")
            print(f"  - Files created: {len(result.get('files_created', []))}")
            print(f"  - Dependencies installed: {result.get('dependencies', [])}")
            print(f"  - Workspace: {result.get('workspace_id', 'N/A')}")
        elif result['status'] == 'failed':
            print(f"❌ Failed!")
            print(f"  - Error: {result.get('error', 'Unknown error')}")
            print(f"  - Execution time: {result.get('execution_time', 'N/A')}")
        else:
            print(f"⚠️ Error!")
            print(f"  - Error: {result.get('error', 'Unknown error')}")
            print(f"  - Retryable: {result.get('retryable', False)}")

        return result

    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}", exc_info=True)
        return None


def test_batch_execution():
    """Test executing multiple tickets in batch."""
    print("\n" + "="*60)
    print("Testing Batch Ticket Execution with Claude SDK")
    print("="*60)

    try:
        # Find multiple test tickets
        tickets = ProjectTicket.objects.filter(
            status='open',
            role='agent'
        ).order_by('priority')[:3]  # Get up to 3 tickets

        if not tickets:
            print("No open agent tickets found. Please create test tickets first.")
            return

        project = tickets[0].project
        conversation_id = 1  # Use a test conversation ID
        ticket_ids = [t.id for t in tickets]

        print(f"\nExecuting {len(tickets)} tickets:")
        for ticket in tickets:
            print(f"  - Ticket #{ticket.id}: {ticket.name} (Priority: {ticket.priority})")

        # Execute the batch
        result = batch_execute_tickets_claude_sdk_sync(
            ticket_ids=ticket_ids,
            project_id=project.id,
            conversation_id=conversation_id
        )

        # Display results
        print(f"\nBatch execution completed:")
        print(f"  - Status: {result['batch_status']}")
        print(f"  - Total tickets: {result['total_tickets']}")
        print(f"  - Completed: {result['completed_tickets']}")
        print(f"  - Failed: {result['failed_tickets']}")

        print("\nIndividual ticket results:")
        for ticket_result in result.get('results', []):
            ticket_id = ticket_result.get('ticket_id')
            status = ticket_result.get('status')
            print(f"  - Ticket #{ticket_id}: {status}")

        return result

    except Exception as e:
        logger.error(f"Batch test failed with error: {str(e)}", exc_info=True)
        return None


async def test_async_execution():
    """Test the async execution directly."""
    print("\n" + "="*60)
    print("Testing Async Ticket Execution with Claude SDK")
    print("="*60)

    try:
        # Find a test ticket
        ticket = await sync_to_async(
            ProjectTicket.objects.filter(status='open', role='agent').first
        )()

        if not ticket:
            print("No open agent tickets found.")
            return

        # Create executor
        executor = TicketExecutor(conversation_id=1)

        print(f"\nExecuting ticket #{ticket.id} asynchronously...")

        # Execute
        result = await executor.execute_ticket(
            ticket_id=ticket.id,
            project_id=ticket.project.id,
            max_execution_time=120
        )

        print(f"Async execution completed: {result['status']}")
        return result

    except Exception as e:
        logger.error(f"Async test failed: {str(e)}", exc_info=True)
        return None


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("#" + " Claude Agent SDK Ticket Executor Test Suite ".center(58) + "#")
    print("#"*60)

    # Test 1: Single ticket
    print("\n[Test 1/3] Single Ticket Execution")
    single_result = test_single_ticket_execution()

    # Test 2: Batch execution
    print("\n[Test 2/3] Batch Ticket Execution")
    batch_result = test_batch_execution()

    # Test 3: Async execution
    print("\n[Test 3/3] Async Ticket Execution")
    from asgiref.sync import sync_to_async
    async_result = asyncio.run(test_async_execution())

    # Summary
    print("\n" + "#"*60)
    print("# Test Summary")
    print("#"*60)

    tests_passed = 0
    tests_failed = 0

    if single_result:
        tests_passed += 1
        print("✅ Single ticket execution: PASSED")
    else:
        tests_failed += 1
        print("❌ Single ticket execution: FAILED")

    if batch_result:
        tests_passed += 1
        print("✅ Batch ticket execution: PASSED")
    else:
        tests_failed += 1
        print("❌ Batch ticket execution: FAILED")

    if async_result:
        tests_passed += 1
        print("✅ Async ticket execution: PASSED")
    else:
        tests_failed += 1
        print("❌ Async ticket execution: FAILED")

    print(f"\nTotal: {tests_passed} passed, {tests_failed} failed")
    print("#"*60)


if __name__ == "__main__":
    main()