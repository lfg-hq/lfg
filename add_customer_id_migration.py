#!/usr/bin/env python
"""
Create a Django migration for adding stripe_customer_id field to UserCredit model
"""
import subprocess
import sys

def create_migration():
    try:
        # Create the migration
        result = subprocess.run([
            'python', 'manage.py', 'makemigrations', 'subscriptions',
            '--name', 'add_stripe_customer_id'
        ], capture_output=True, text=True, cwd='/home/jitinp/Projects/lfg')
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("✅ Migration created successfully!")
            
            # Run the migration
            result2 = subprocess.run([
                'python', 'manage.py', 'migrate'
            ], capture_output=True, text=True, cwd='/home/jitinp/Projects/lfg')
            
            print("MIGRATE STDOUT:", result2.stdout)
            if result2.stderr:
                print("MIGRATE STDERR:", result2.stderr)
                
            if result2.returncode == 0:
                print("✅ Migration applied successfully!")
            else:
                print("❌ Migration failed to apply")
        else:
            print("❌ Migration creation failed")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    create_migration()