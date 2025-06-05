#!/usr/bin/env python3
"""
Django-Q Test Script

This script tests Django-Q functionality to ensure the timer issue is resolved.
"""

import os
import sys
import time
import django
from pathlib import Path

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from django_q.tasks import async_task, result, fetch
from django_q.models import Task
from tasks.task_manager import TaskManager


def simple_test_task(message: str, delay: int = 1) -> dict:
    """A simple test task that can be used to verify Django-Q functionality"""
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Test task started: {message}")
    
    # Simulate some work
    time.sleep(delay)
    
    result = {
        'status': 'success',
        'message': message,
        'timestamp': time.time(),
        'delay': delay
    }
    
    logger.info(f"Test task completed: {result}")
    return result


def test_direct_async_task():
    """Test Django-Q using direct async_task function"""
    print("🧪 Testing direct async_task...")
    
    try:
        # Submit a simple task
        task_id = async_task(
            'test_django_q.simple_test_task',
            'Hello from direct async_task!',
            1,
            timeout=30
        )
        
        print(f"📝 Submitted task with ID: {task_id}")
        
        # Wait for result
        print("⏳ Waiting for task result...")
        task_result = None
        for i in range(10):  # Wait up to 10 seconds
            task_result = result(task_id)
            if task_result is not None:
                break
            time.sleep(1)
            print(f"   ... waiting ({i+1}/10)")
        
        if task_result:
            print(f"✅ Task completed successfully!")
            print(f"📊 Result: {task_result}")
            return True
        else:
            print("❌ Task did not complete within timeout")
            
            # Check task status
            task_obj = fetch(task_id)
            if task_obj:
                print(f"📋 Task status: success={task_obj.success}")
                print(f"📋 Task result: {task_obj.result}")
            
            return False
            
    except Exception as e:
        print(f"❌ Error in direct async_task test: {e}")
        return False


def test_task_manager():
    """Test Django-Q using TaskManager wrapper"""
    print("\n🧪 Testing TaskManager wrapper...")
    
    try:
        # Submit a task using TaskManager
        task_id = TaskManager.publish_task(
            'test_django_q.simple_test_task',
            'Hello from TaskManager!',
            2,
            task_name="TaskManager Test"
        )
        
        print(f"📝 Submitted task with ID: {task_id}")
        
        # Check task status
        print("⏳ Waiting for task result...")
        task_result = None
        for i in range(12):  # Wait up to 12 seconds (task takes 2 seconds)
            status = TaskManager.get_task_status(task_id)
            if status and status.get('success') is not None:
                task_result = status.get('result')
                break
            time.sleep(1)
            print(f"   ... waiting ({i+1}/12)")
        
        if task_result:
            print(f"✅ Task completed successfully!")
            print(f"📊 Result: {task_result}")
            return True
        else:
            print("❌ Task did not complete within timeout")
            return False
            
    except Exception as e:
        print(f"❌ Error in TaskManager test: {e}")
        return False


def test_queue_statistics():
    """Test queue statistics functionality"""
    print("\n📊 Testing queue statistics...")
    
    try:
        stats = TaskManager.get_task_statistics()
        
        print(f"📈 Queue statistics:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        # Get running tasks
        running = TaskManager.get_running_tasks()
        print(f"🏃 Currently running tasks: {len(running)}")
        
        # Get failed tasks from last 24h
        failed = TaskManager.get_failed_tasks(hours=24)
        print(f"❌ Failed tasks (24h): {len(failed)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error getting queue statistics: {e}")
        return False


def check_django_q_status():
    """Check the overall status of Django-Q"""
    print("🔍 Checking Django-Q status...")
    
    try:
        from django.conf import settings
        q_config = getattr(settings, 'Q_CLUSTER', {})
        
        print(f"⚙️  Configuration:")
        print(f"   Name: {q_config.get('name', 'default')}")
        print(f"   Workers: {q_config.get('workers', 'N/A')}")
        print(f"   Timeout: {q_config.get('timeout', 'N/A')}")
        print(f"   Broker: {'Redis' if 'redis' in q_config else 'ORM' if 'orm' in q_config else 'Unknown'}")
        
        # Check recent tasks
        recent_tasks = Task.objects.all().order_by('-id')[:5]
        print(f"\n📋 Recent tasks ({len(recent_tasks)}):")
        for task in recent_tasks:
            status = "✅ Success" if task.success else "❌ Failed" if task.stopped else "⏳ Running"
            print(f"   {task.id}: {task.name} - {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking Django-Q status: {e}")
        return False


def main():
    print("🧪 Django-Q Test Suite")
    print("=" * 50)
    
    # Check status first
    if not check_django_q_status():
        print("❌ Django-Q status check failed")
        return False
    
    # Test queue statistics
    if not test_queue_statistics():
        print("❌ Queue statistics test failed")
        return False
    
    # Test direct async_task
    test1_success = test_direct_async_task()
    
    # Test TaskManager
    test2_success = test_task_manager()
    
    # Final summary
    print("\n📋 Test Results Summary:")
    print("=" * 30)
    print(f"Direct async_task: {'✅ PASS' if test1_success else '❌ FAIL'}")
    print(f"TaskManager:       {'✅ PASS' if test2_success else '❌ FAIL'}")
    
    overall_success = test1_success and test2_success
    
    if overall_success:
        print("\n🎉 All tests passed! Django-Q is working correctly.")
        print("\n💡 The timer value issue appears to be resolved.")
    else:
        print("\n❌ Some tests failed. Django-Q may still have issues.")
        print("\n🔧 Try running the restart_django_q.py script again.")
    
    return overall_success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {e}")
        sys.exit(1) 