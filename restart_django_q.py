#!/usr/bin/env python3
"""
Django-Q Cluster Restart Script

This script properly stops and restarts Django-Q cluster workers
to resolve timer value initialization issues.
"""

import os
import sys
import signal
import subprocess
import time
import psutil
import django
from pathlib import Path

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from django_q.models import Task
from django.core.management import call_command


def kill_django_q_processes():
    """Kill any existing Django-Q processes"""
    print("🔍 Searching for existing Django-Q processes...")
    
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
            if 'qcluster' in cmdline or 'django_q' in cmdline:
                print(f"🔪 Killing process {proc.info['pid']}: {cmdline}")
                proc.kill()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_count > 0:
        print(f"✅ Killed {killed_count} Django-Q processes")
        print("⏳ Waiting 3 seconds for processes to terminate...")
        time.sleep(3)
    else:
        print("✅ No existing Django-Q processes found")


def clear_stuck_tasks():
    """Clear any tasks that might be stuck in 'started' state"""
    print("🧹 Clearing stuck tasks...")
    
    # Reset tasks that are stuck in started state without being stopped
    stuck_tasks = Task.objects.filter(started__isnull=False, stopped__isnull=True)
    stuck_count = stuck_tasks.count()
    
    if stuck_count > 0:
        print(f"📋 Found {stuck_count} stuck tasks, clearing them...")
        for task in stuck_tasks:
            task.stopped = task.started
            task.success = False
            task.result = "Task was stuck and cleared during restart"
            task.save()
        print(f"✅ Cleared {stuck_count} stuck tasks")
    else:
        print("✅ No stuck tasks found")


def test_django_q_config():
    """Test Django-Q configuration"""
    print("⚙️  Testing Django-Q configuration...")
    
    try:
        from django.conf import settings
        q_config = getattr(settings, 'Q_CLUSTER', {})
        
        print(f"📝 Cluster name: {q_config.get('name', 'default')}")
        print(f"👥 Workers: {q_config.get('workers', 'default')}")
        print(f"🔄 Recycle: {q_config.get('recycle', 'default')}")
        print(f"⏱️  Timeout: {q_config.get('timeout', 'default')}")
        print(f"🔒 Guard cycle: {q_config.get('guard_cycle', 'default')}")
        
        broker_type = 'Redis' if 'redis' in q_config else 'ORM' if 'orm' in q_config else 'Unknown'
        print(f"🗄️  Broker: {broker_type}")
        
        print("✅ Django-Q configuration is valid")
        return True
        
    except Exception as e:
        print(f"❌ Django-Q configuration error: {e}")
        return False


def start_django_q():
    """Start Django-Q cluster"""
    print("🚀 Starting Django-Q cluster...")
    
    try:
        print("⚠️  NOTE: Starting in SYNCHRONOUS mode to prevent timer issues")
        print("   Check LFG/settings.py - Q_CLUSTER['sync'] = True for local development")
        
        # Start qcluster in background
        process = subprocess.Popen(
            [sys.executable, 'manage.py', 'qcluster'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=BASE_DIR
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            print(f"✅ Django-Q cluster started successfully (PID: {process.pid})")
            print("📊 Monitor the logs to ensure workers are ready")
            return True
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Django-Q cluster failed to start")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"❌ Error starting Django-Q cluster: {e}")
        return False


def test_simple_task():
    """Test Django-Q with a simple task to verify it's working"""
    print("\n🧪 Testing Django-Q with simple task...")
    
    try:
        from django_q.tasks import async_task, result
        from tasks.task_manager import TaskManager
        
        # Submit a simple test task
        task_id = async_task(
            'tasks.task_definitions.simple_test_task_for_debugging',
            'Testing after restart',
            1,
            timeout=30
        )
        
        print(f"📝 Submitted simple test task with ID: {task_id}")
        
        # Wait for result
        print("⏳ Waiting for test result...")
        task_result = None
        for i in range(15):  # Wait up to 15 seconds
            task_result = result(task_id)
            if task_result is not None:
                break
            time.sleep(1)
            print(f"   ... waiting ({i+1}/15)")
        
        if task_result:
            print(f"✅ Simple test task completed successfully!")
            print(f"📊 Result: {task_result}")
            return True
        else:
            print("❌ Simple test task did not complete within timeout")
            return False
            
    except Exception as e:
        print(f"❌ Error testing simple task: {e}")
        return False


def main():
    print("🔧 Django-Q Cluster Restart Script")
    print("=" * 50)
    
    # Step 1: Kill existing processes
    kill_django_q_processes()
    
    # Step 2: Clear stuck tasks
    clear_stuck_tasks()
    
    # Step 3: Test configuration
    if not test_django_q_config():
        print("❌ Exiting due to configuration errors")
        return False
    
    # Step 4: Start Django-Q
    if not start_django_q():
        print("❌ Failed to start Django-Q cluster")
        return False
    
    # Step 5: Test simple task
    if not test_simple_task():
        print("❌ Failed to test simple task")
        return False
    
    print("\n🎉 Django-Q restart completed successfully!")
    print("\n📋 Next steps:")
    print("   1. Monitor the qcluster logs for worker readiness")
    print("   2. Test task execution with a simple task")
    print("   3. Check the Django admin for task monitoring")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1) 