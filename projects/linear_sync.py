import requests
from datetime import datetime
from django.utils import timezone
from .models import ProjectTickets


class LinearSyncService:
    """Service for syncing tickets with Linear"""
    
    BASE_URL = "https://api.linear.app/graphql"
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
    
    def test_connection(self):
        """Test if the Linear API key is valid"""
        query = """
        query Me {
            viewer {
                id
                name
                email
            }
        }
        """
        
        response = requests.post(
            self.BASE_URL,
            json={"query": query},
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
            return True, data.get("data", {}).get("viewer", {})
        return False, f"HTTP Error: {response.status_code}"
    
    def get_teams(self):
        """Get all teams accessible with this API key"""
        query = """
        query Teams {
            teams {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        
        response = requests.post(
            self.BASE_URL,
            json={"query": query},
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                return data["data"]["teams"]["nodes"]
        return []
    
    def get_projects(self, team_id):
        """Get all projects for a specific team"""
        query = """
        query Projects($teamId: String!) {
            team(id: $teamId) {
                projects {
                    nodes {
                        id
                        name
                        key
                        state
                    }
                }
            }
        }
        """
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": query,
                "variables": {"teamId": team_id}
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["team"]:
                return data["data"]["team"]["projects"]["nodes"]
        return []
    
    def create_project(self, team_id, name, description=""):
        """Create a new Linear project"""
        mutation = """
        mutation CreateProject($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project {
                    id
                    name
                    key
                    description
                }
            }
        }
        """
        
        variables = {
            "input": {
                "teamIds": [team_id],
                "name": name,
                "description": description
            }
        }
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": mutation,
                "variables": variables
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["projectCreate"]["success"]:
                return True, data["data"]["projectCreate"]["project"]
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        return False, f"HTTP Error: {response.status_code}"
    
    def create_issue(self, ticket, team_id, project_id=None):
        """Create a new Linear issue from a ProjectTicket"""
        # Map priority
        priority_map = {
            'HIGH': 1,
            'MEDIUM': 2,
            'LOW': 3
        }
        linear_priority = priority_map.get(ticket.priority, 3)
        
        # Build description with details
        description = f"{ticket.description}\n\n"
        if ticket.details:
            description += f"**Details:**\n{ticket.details}\n\n"
        if ticket.acceptance_criteria:
            description += f"**Acceptance Criteria:**\n{ticket.acceptance_criteria}\n\n"
        
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                    priority
                    assignee {
                        id
                        name
                    }
                }
            }
        }
        """
        
        variables = {
            "input": {
                "teamId": team_id,
                "title": ticket.title,
                "description": description,
                "priority": linear_priority
            }
        }
        
        if project_id:
            variables["input"]["projectId"] = project_id
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": mutation,
                "variables": variables
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["issueCreate"]["success"]:
                issue = data["data"]["issueCreate"]["issue"]
                # Update ticket with Linear info
                ticket.linear_issue_id = issue["id"]
                ticket.linear_issue_url = issue["url"]
                ticket.linear_state = issue["state"]["name"]
                ticket.linear_priority = issue["priority"]
                if issue.get("assignee"):
                    ticket.linear_assignee_id = issue["assignee"]["id"]
                ticket.linear_synced_at = timezone.now()
                ticket.save()
                return True, issue
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        return False, f"HTTP Error: {response.status_code}"
    
    def update_issue(self, ticket):
        """Update an existing Linear issue from a ProjectTicket"""
        if not ticket.linear_issue_id:
            return False, "Ticket has no Linear issue ID"
        
        # Build updated description
        description = f"{ticket.description}\n\n"
        if ticket.details:
            description += f"**Details:**\n{ticket.details}\n\n"
        if ticket.acceptance_criteria:
            description += f"**Acceptance Criteria:**\n{ticket.acceptance_criteria}\n\n"
        
        # Map priority
        priority_map = {
            'HIGH': 1,
            'MEDIUM': 2,
            'LOW': 3
        }
        linear_priority = priority_map.get(ticket.priority, 3)
        
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                    priority
                    assignee {
                        id
                        name
                    }
                }
            }
        }
        """
        
        variables = {
            "id": ticket.linear_issue_id,
            "input": {
                "title": ticket.title,
                "description": description,
                "priority": linear_priority
            }
        }
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": mutation,
                "variables": variables
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["issueUpdate"]["success"]:
                issue = data["data"]["issueUpdate"]["issue"]
                # Update ticket with latest Linear info
                ticket.linear_issue_url = issue["url"]
                ticket.linear_state = issue["state"]["name"]
                ticket.linear_priority = issue["priority"]
                if issue.get("assignee"):
                    ticket.linear_assignee_id = issue["assignee"]["id"]
                ticket.linear_synced_at = timezone.now()
                ticket.save()
                return True, issue
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        return False, f"HTTP Error: {response.status_code}"
    
    def sync_ticket(self, ticket, team_id, project_id=None):
        """Sync a ticket with Linear - create or update as needed"""
        if ticket.linear_issue_id:
            # Update existing issue
            return self.update_issue(ticket)
        else:
            # Create new issue
            return self.create_issue(ticket, team_id, project_id)
    
    def sync_all_tickets(self, project):
        """Sync all checklist items for a project with Linear"""
        if not project.linear_sync_enabled or not project.linear_team_id:
            return False, "Linear sync not enabled or team ID not set"
        
        results = {
            "created": 0,
            "updated": 0,
            "errors": []
        }
        
        # Get all checklist items to sync
        checklist_items = project.checklist.exclude(status='done')
        
        for item in checklist_items:
            success, result = self.sync_checklist_item(
                item, 
                project.linear_team_id,
                project.linear_project_id
            )
            
            if success:
                results["created"] += 1
            else:
                results["errors"].append({
                    "ticket": item.name,
                    "error": result
                })
        
        return True, results
    
    def sync_checklist_item(self, checklist_item, team_id, project_id=None):
        """Sync a single checklist item to Linear as an issue"""
        # Map checklist priority to Linear priority
        priority_map = {
            'High': 1,    # Urgent
            'Medium': 2,  # High  
            'Low': 3      # Normal
        }
        
        # Map checklist status to Linear state
        state_map = {
            'open': 'backlog',
            'in_progress': 'started',
            'done': 'completed',
            'failed': 'canceled',
            'blocked': 'backlog'
        }
        
        # Prepare issue data
        description = checklist_item.description
        if checklist_item.details:
            description += "\n\n## Details\n" + str(checklist_item.details)
        
        issue_data = {
            "title": checklist_item.name,
            "description": description,
            "teamId": team_id,
            "priority": priority_map.get(checklist_item.priority, 3),
            "stateId": None  # Will be set based on state
        }
        
        if project_id:
            issue_data["projectId"] = project_id
        
        # Create the issue
        query = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                }
            }
        }
        """
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": query,
                "variables": {"input": issue_data}
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["issueCreate"]["success"]:
                return True, data["data"]["issueCreate"]["issue"]
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        
        return False, f"HTTP Error: {response.status_code}"