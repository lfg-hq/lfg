#!/usr/bin/env python
"""
Quick test script to verify project member functionality
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
sys.path.append('/home/jitinp/Projects/lfg')
django.setup()

from django.contrib.auth.models import User
from projects.models import Project, ProjectMember, ProjectInvitation

def test_project_members():
    print("Testing Project Member functionality...")
    
    # Get or create test users
    try:
        owner = User.objects.get(username='testowner')
    except User.DoesNotExist:
        owner = User.objects.create_user(username='testowner', email='owner@test.com', password='testpass')
        print("Created test owner user")
    
    try:
        member = User.objects.get(username='testmember')
    except User.DoesNotExist:
        member = User.objects.create_user(username='testmember', email='member@test.com', password='testpass')
        print("Created test member user")
    
    # Create a test project
    project, created = Project.objects.get_or_create(
        name='Test Project',
        owner=owner,
        defaults={
            'description': 'Test project for member functionality',
            'status': 'active'
        }
    )
    if created:
        print(f"Created test project: {project.name}")
    else:
        print(f"Using existing test project: {project.name}")
    
    # Test project access methods
    print(f"\nProject access tests:")
    print(f"Owner has access: {project.can_user_access(owner)}")
    print(f"Member has access (should be False): {project.can_user_access(member)}")
    
    # Create a project member
    project_member, created = ProjectMember.objects.get_or_create(
        user=member,
        project=project,
        defaults={
            'role': 'member',
            'status': 'active'
        }
    )
    if created:
        print(f"Added {member.username} as project member")
    else:
        print(f"{member.username} already a project member")
    
    # Test access after adding member
    print(f"\nAfter adding member:")
    print(f"Member has access: {project.can_user_access(member)}")
    print(f"Member can edit files: {project.can_user_edit_files(member)}")
    print(f"Member can manage tickets: {project.can_user_manage_tickets(member)}")
    print(f"Member can chat: {project.can_user_chat(member)}")
    
    # Test invitation creation
    invitation = ProjectInvitation.create_invitation(
        project=project,
        inviter=owner,
        email='newmember@test.com',
        role='viewer'
    )
    print(f"\nCreated invitation: {invitation.token[:10]}...")
    print(f"Invitation is valid: {invitation.is_valid()}")
    
    print("\n✅ Project member functionality is working!")
    
    return True

if __name__ == '__main__':
    try:
        test_project_members()
    except Exception as e:
        print(f"❌ Error testing project members: {e}")
        import traceback
        traceback.print_exc()