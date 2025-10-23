import requests
from datetime import datetime
from django.utils import timezone
from .models import ProjectChecklist


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

    def get_all_issues(self, limit=50, team_id=None):
        """
        Get all issues accessible to the user

        Args:
            limit: Maximum number of issues to return (default 50, max 250)
            team_id: Optional team ID to filter issues by team

        Returns:
            Tuple of (success: bool, issues: List[Dict] or error: str)
        """
        query = """
        query Issues($first: Int!, $teamId: ID) {
            issues(first: $first, filter: { team: { id: { eq: $teamId } } }) {
                nodes {
                    id
                    identifier
                    title
                    description
                    priority
                    state {
                        name
                        type
                    }
                    assignee {
                        id
                        name
                        email
                    }
                    project {
                        id
                        name
                    }
                    team {
                        id
                        name
                        key
                    }
                    createdAt
                    updatedAt
                    dueDate
                    url
                }
            }
        }
        """

        # If no team_id, use a simpler query without team filter
        if not team_id:
            query = """
            query Issues($first: Int!) {
                issues(first: $first) {
                    nodes {
                        id
                        identifier
                        title
                        description
                        priority
                        state {
                            name
                            type
                        }
                        assignee {
                            id
                            name
                            email
                        }
                        project {
                            id
                            name
                        }
                        team {
                            id
                            name
                            key
                        }
                        createdAt
                        updatedAt
                        dueDate
                        url
                    }
                }
            }
            """

        variables = {"first": min(limit, 250)}
        if team_id:
            variables["teamId"] = team_id

        try:
            response = requests.post(
                self.BASE_URL,
                json={
                    "query": query,
                    "variables": variables
                },
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    return False, data["errors"][0].get("message", "Unknown error")

                if "data" in data and "issues" in data["data"]:
                    issues = data["data"]["issues"]["nodes"]
                    return True, issues
                return False, "No issues data in response"
            else:
                return False, f"HTTP Error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Request error: {str(e)}"

    def get_issue_by_identifier(self, identifier):
        """
        Get detailed information for a specific Linear issue by identifier

        Args:
            identifier: Linear issue identifier (e.g., "PED-8")

        Returns:
            Tuple of (success: bool, issue: Dict or error: str)
        """
        # First, search for the issue to get its UUID
        search_query = """
        query SearchIssue($filter: String!) {
            issues(filter: { searchableContent: { contains: $filter } }, first: 1) {
                nodes {
                    id
                    identifier
                }
            }
        }
        """

        # If the identifier looks like a UUID, query directly
        # Otherwise, search for it first
        if len(identifier) > 30:  # UUID is longer than identifier
            issue_uuid = identifier
        else:
            # Search for the issue by identifier
            try:
                response = requests.post(
                    self.BASE_URL,
                    json={
                        "query": search_query,
                        "variables": {"filter": identifier}
                    },
                    headers=self.headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    if "errors" in data:
                        return False, data["errors"][0].get("message", "Unknown error")

                    issues = data.get("data", {}).get("issues", {}).get("nodes", [])
                    # Find exact match
                    matching_issue = None
                    for issue in issues:
                        if issue.get("identifier") == identifier.upper():
                            matching_issue = issue
                            break

                    if not matching_issue:
                        return False, f"Issue with identifier '{identifier}' not found"

                    issue_uuid = matching_issue.get("id")
                else:
                    return False, f"Search failed: HTTP {response.status_code}"
            except requests.exceptions.RequestException as e:
                return False, f"Search error: {str(e)}"

        # Now get the detailed issue information
        query = """
        query Issue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                priority
                priorityLabel
                estimate
                state {
                    name
                    type
                    color
                }
                assignee {
                    id
                    name
                    email
                }
                creator {
                    id
                    name
                    email
                }
                project {
                    id
                    name
                }
                team {
                    id
                    name
                    key
                }
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
                comments {
                    nodes {
                        id
                        body
                        user {
                            name
                        }
                        createdAt
                    }
                }
                createdAt
                updatedAt
                completedAt
                dueDate
                url
                parent {
                    id
                    identifier
                    title
                }
                children {
                    nodes {
                        id
                        identifier
                        title
                    }
                }
            }
        }
        """

        try:
            response = requests.post(
                self.BASE_URL,
                json={
                    "query": query,
                    "variables": {"id": issue_uuid}
                },
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    return False, data["errors"][0].get("message", "Unknown error")

                if "data" in data and "issue" in data["data"]:
                    issue = data["data"]["issue"]
                    return True, issue
                return False, "No issue data in response"
            else:
                return False, f"HTTP Error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Request error: {str(e)}"

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
            # Skip if already synced and sync is disabled for this item
            if item.linear_issue_id and not item.linear_sync_enabled:
                continue
                
            success, result = self.sync_checklist_item(
                item, 
                project.linear_team_id,
                project.linear_project_id
            )
            
            if success:
                if item.linear_issue_id:
                    results["updated"] += 1
                else:
                    results["created"] += 1
            else:
                results["errors"].append({
                    "ticket": item.name,
                    "error": result
                })
        
        return True, results
    
    def sync_checklist_item(self, checklist_item, team_id, project_id=None):
        """Sync a single checklist item to Linear as an issue"""
        # If item already has a Linear issue, update it instead
        if checklist_item.linear_issue_id:
            return self.update_checklist_item(checklist_item, team_id, project_id)
        
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
        
        # Prepare issue data with all fields
        description = checklist_item.description
        
        # Add Component Specifications
        if checklist_item.component_specs:
            description += "\n\n## Component Specifications\n"
            if isinstance(checklist_item.component_specs, dict):
                for key, value in checklist_item.component_specs.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.component_specs)
        
        # Add Acceptance Criteria
        if checklist_item.acceptance_criteria:
            description += "\n\n## Acceptance Criteria\n"
            if isinstance(checklist_item.acceptance_criteria, list):
                for idx, criteria in enumerate(checklist_item.acceptance_criteria, 1):
                    description += f"{idx}. {criteria}\n"
            else:
                description += str(checklist_item.acceptance_criteria)
        
        # Add UI Requirements
        if checklist_item.ui_requirements:
            description += "\n\n## UI Requirements\n"
            if isinstance(checklist_item.ui_requirements, dict):
                for key, value in checklist_item.ui_requirements.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.ui_requirements)
        
        # Add Additional Details
        if checklist_item.details:
            description += "\n\n## Additional Details\n"
            if isinstance(checklist_item.details, dict):
                for key, value in checklist_item.details.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.details)
        
        # Add Dependencies
        if checklist_item.dependencies:
            description += "\n\n## Dependencies\n"
            if isinstance(checklist_item.dependencies, list):
                for dep in checklist_item.dependencies:
                    description += f"- {dep}\n"
            else:
                description += str(checklist_item.dependencies)
        
        # Add Metadata
        description += f"\n\n## Metadata\n"
        description += f"**Complexity**: {checklist_item.complexity}\n"
        description += f"**Role**: {checklist_item.role}\n"
        description += f"**Requires Worktree**: {'Yes' if checklist_item.requires_worktree else 'No'}\n"
        
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
                issue = data["data"]["issueCreate"]["issue"]
                
                # Update the checklist item with Linear issue information
                checklist_item.linear_issue_id = issue["id"]
                checklist_item.linear_issue_url = issue.get("url", "")
                checklist_item.linear_synced_at = timezone.now()
                checklist_item.save()
                
                return True, issue
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        
        return False, f"HTTP Error: {response.status_code}"
    
    def update_checklist_item(self, checklist_item, team_id, project_id=None):
        """Update an existing Linear issue from a checklist item"""
        # Map checklist priority to Linear priority
        priority_map = {
            'High': 1,    # Urgent
            'Medium': 2,  # High  
            'Low': 3      # Normal
        }
        
        # Prepare updated description with all fields
        description = checklist_item.description
        
        # Add Component Specifications
        if checklist_item.component_specs:
            description += "\n\n## Component Specifications\n"
            if isinstance(checklist_item.component_specs, dict):
                for key, value in checklist_item.component_specs.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.component_specs)
        
        # Add Acceptance Criteria
        if checklist_item.acceptance_criteria:
            description += "\n\n## Acceptance Criteria\n"
            if isinstance(checklist_item.acceptance_criteria, list):
                for idx, criteria in enumerate(checklist_item.acceptance_criteria, 1):
                    description += f"{idx}. {criteria}\n"
            else:
                description += str(checklist_item.acceptance_criteria)
        
        # Add UI Requirements
        if checklist_item.ui_requirements:
            description += "\n\n## UI Requirements\n"
            if isinstance(checklist_item.ui_requirements, dict):
                for key, value in checklist_item.ui_requirements.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.ui_requirements)
        
        # Add Additional Details
        if checklist_item.details:
            description += "\n\n## Additional Details\n"
            if isinstance(checklist_item.details, dict):
                for key, value in checklist_item.details.items():
                    description += f"**{key}**: {value}\n"
            else:
                description += str(checklist_item.details)
        
        # Add Dependencies
        if checklist_item.dependencies:
            description += "\n\n## Dependencies\n"
            if isinstance(checklist_item.dependencies, list):
                for dep in checklist_item.dependencies:
                    description += f"- {dep}\n"
            else:
                description += str(checklist_item.dependencies)
        
        # Add Metadata
        description += f"\n\n## Metadata\n"
        description += f"**Complexity**: {checklist_item.complexity}\n"
        description += f"**Role**: {checklist_item.role}\n"
        description += f"**Requires Worktree**: {'Yes' if checklist_item.requires_worktree else 'No'}\n"
        
        # Update the issue
        query = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
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
        
        update_data = {
            "title": checklist_item.name,
            "description": description,
            "priority": priority_map.get(checklist_item.priority, 3),
        }
        
        response = requests.post(
            self.BASE_URL,
            json={
                "query": query,
                "variables": {
                    "id": checklist_item.linear_issue_id,
                    "input": update_data
                }
            },
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]["issueUpdate"]["success"]:
                # Update sync timestamp
                checklist_item.linear_synced_at = timezone.now()
                checklist_item.save()
                
                return True, data["data"]["issueUpdate"]["issue"]
            elif "errors" in data:
                return False, data["errors"][0].get("message", "Unknown error")
        
        return False, f"HTTP Error: {response.status_code}"