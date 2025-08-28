#!/usr/bin/env python
"""
Create a Django migration for adding stripe_customer_id field to UserCredit model
"""
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

def create_migration():
    try:
        # Create the migration
        result = subprocess.run([
            'python', 'manage.py', 'makemigrations', 'subscriptions',
            '--name', 'add_stripe_customer_id'
        ], capture_output=True, text=True, cwd='/home/jitinp/Projects/lfg')
        
        logger.info("STDOUT: %s", result.stdout)
        if result.stderr:
            logger.error("STDERR: %s", result.stderr)
        
        if result.returncode == 0:
            logger.info("✅ Migration created successfully!")
            
            # Run the migration
            result2 = subprocess.run([
                'python', 'manage.py', 'migrate'
            ], capture_output=True, text=True, cwd='/home/jitinp/Projects/lfg')
            
            logger.info("MIGRATE STDOUT: %s", result2.stdout)
            if result2.stderr:
                logger.error("MIGRATE STDERR: %s", result2.stderr)
                
            if result2.returncode == 0:
                logger.info("✅ Migration applied successfully!")
            else:
                logger.error("❌ Migration failed to apply")
        else:
            logger.error("❌ Migration creation failed")
            
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    create_migration()