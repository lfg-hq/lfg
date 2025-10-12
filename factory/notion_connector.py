"""
Notion API Integration Service

Provides functions to:
- Connect to Notion workspace
- Fetch pages and databases
- Search Notion content
- Retrieve page content for AI context
"""

import requests
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime


class NotionConnector:
    """Service for interacting with Notion API"""

    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"  # Notion API version

    def __init__(self, api_key: str):
        """
        Initialize Notion connector with API key

        Args:
            api_key: Notion integration token
        """
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION
        }

    def test_connection(self) -> Tuple[bool, Any]:
        """
        Test if the Notion API key is valid

        Returns:
            Tuple of (success: bool, data/error: Any)
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/users/me",
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return True, data
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                error_data = response.json()
                return False, error_data.get("message", f"HTTP Error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"

    def search_pages(self, query: str = "", page_size: int = 10) -> Tuple[bool, Any]:
        """
        Search for pages and databases in Notion workspace

        Args:
            query: Search query string (empty string returns all accessible pages)
            page_size: Number of results to return (max 100)

        Returns:
            Tuple of (success: bool, results: List[Dict] or error: str)
        """
        try:
            payload = {
                "page_size": min(page_size, 100),
                "filter": {
                    "property": "object",
                    "value": "page"
                }
            }

            # Only add query if it's not empty
            if query:
                payload["query"] = query

            response = requests.post(
                f"{self.BASE_URL}/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                results = self._format_search_results(data.get("results", []))
                return True, results
            else:
                error_data = response.json()
                return False, error_data.get("message", f"HTTP Error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            return False, f"Search error: {str(e)}"

    def list_all_pages(self, page_size: int = 100) -> Tuple[bool, Any]:
        """
        List all accessible pages in the workspace (no query filter)

        Args:
            page_size: Number of results to return (max 100)

        Returns:
            Tuple of (success: bool, results: List[Dict] or error: str)
        """
        return self.search_pages(query="", page_size=page_size)

    def get_page_content(self, page_id: str) -> Tuple[bool, Any]:
        """
        Retrieve full content of a Notion page including all blocks

        Args:
            page_id: Notion page ID

        Returns:
            Tuple of (success: bool, content: Dict or error: str)
        """
        try:
            # Get page metadata
            page_response = requests.get(
                f"{self.BASE_URL}/pages/{page_id}",
                headers=self.headers,
                timeout=10
            )

            if page_response.status_code != 200:
                error_data = page_response.json()
                return False, error_data.get("message", f"HTTP Error: {page_response.status_code}")

            page_data = page_response.json()

            # Get page blocks (content)
            blocks_response = requests.get(
                f"{self.BASE_URL}/blocks/{page_id}/children",
                headers=self.headers,
                timeout=10
            )

            if blocks_response.status_code != 200:
                error_data = blocks_response.json()
                return False, error_data.get("message", f"HTTP Error: {blocks_response.status_code}")

            blocks_data = blocks_response.json()

            # Format the page content
            formatted_content = self._format_page_content(page_data, blocks_data.get("results", []))
            return True, formatted_content

        except requests.exceptions.RequestException as e:
            return False, f"Error retrieving page: {str(e)}"

    def list_databases(self, page_size: int = 10) -> Tuple[bool, Any]:
        """
        List all accessible databases in the workspace

        Args:
            page_size: Number of results to return (max 100)

        Returns:
            Tuple of (success: bool, databases: List[Dict] or error: str)
        """
        try:
            payload = {
                "page_size": min(page_size, 100),
                "filter": {
                    "property": "object",
                    "value": "database"
                }
            }

            response = requests.post(
                f"{self.BASE_URL}/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                databases = self._format_databases(data.get("results", []))
                return True, databases
            else:
                error_data = response.json()
                return False, error_data.get("message", f"HTTP Error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            return False, f"Error listing databases: {str(e)}"

    def query_database(self, database_id: str, page_size: int = 10) -> Tuple[bool, Any]:
        """
        Query a specific database and retrieve its entries

        Args:
            database_id: Notion database ID
            page_size: Number of results to return (max 100)

        Returns:
            Tuple of (success: bool, entries: List[Dict] or error: str)
        """
        try:
            payload = {
                "page_size": min(page_size, 100)
            }

            response = requests.post(
                f"{self.BASE_URL}/databases/{database_id}/query",
                headers=self.headers,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                entries = self._format_database_entries(data.get("results", []))
                return True, entries
            else:
                error_data = response.json()
                return False, error_data.get("message", f"HTTP Error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            return False, f"Error querying database: {str(e)}"

    def _format_search_results(self, results: List[Dict]) -> List[Dict]:
        """Format search results for easier consumption"""
        formatted = []
        for item in results:
            formatted_item = {
                "id": item.get("id"),
                "type": item.get("object"),
                "title": self._extract_title(item),
                "url": item.get("url"),
                "created_time": item.get("created_time"),
                "last_edited_time": item.get("last_edited_time")
            }
            formatted.append(formatted_item)
        return formatted

    def _format_databases(self, databases: List[Dict]) -> List[Dict]:
        """Format database list for easier consumption"""
        formatted = []
        for db in databases:
            formatted_db = {
                "id": db.get("id"),
                "title": self._extract_title(db),
                "url": db.get("url"),
                "created_time": db.get("created_time"),
                "last_edited_time": db.get("last_edited_time"),
                "properties": list(db.get("properties", {}).keys())
            }
            formatted.append(formatted_db)
        return formatted

    def _format_database_entries(self, entries: List[Dict]) -> List[Dict]:
        """Format database entries for easier consumption"""
        formatted = []
        for entry in entries:
            formatted_entry = {
                "id": entry.get("id"),
                "title": self._extract_title(entry),
                "url": entry.get("url"),
                "properties": self._extract_properties(entry.get("properties", {})),
                "created_time": entry.get("created_time"),
                "last_edited_time": entry.get("last_edited_time")
            }
            formatted.append(formatted_entry)
        return formatted

    def _format_page_content(self, page_data: Dict, blocks: List[Dict]) -> Dict:
        """Format page content with metadata and text content"""
        return {
            "id": page_data.get("id"),
            "title": self._extract_title(page_data),
            "url": page_data.get("url"),
            "created_time": page_data.get("created_time"),
            "last_edited_time": page_data.get("last_edited_time"),
            "properties": self._extract_properties(page_data.get("properties", {})),
            "content": self._extract_block_text(blocks),
            "raw_blocks": blocks
        }

    def _extract_title(self, item: Dict) -> str:
        """Extract title from Notion object"""
        # Try properties first (for pages in databases)
        if "properties" in item:
            for prop_name, prop_value in item["properties"].items():
                if prop_value.get("type") == "title":
                    title_array = prop_value.get("title", [])
                    if title_array:
                        return "".join([t.get("plain_text", "") for t in title_array])

        # Try direct title property (for databases)
        if "title" in item:
            title_array = item["title"]
            if isinstance(title_array, list) and title_array:
                return "".join([t.get("plain_text", "") for t in title_array])

        return "Untitled"

    def _extract_properties(self, properties: Dict) -> Dict:
        """Extract and simplify properties from Notion object"""
        simplified = {}
        for prop_name, prop_value in properties.items():
            prop_type = prop_value.get("type")

            if prop_type == "title":
                title_array = prop_value.get("title", [])
                simplified[prop_name] = "".join([t.get("plain_text", "") for t in title_array])
            elif prop_type == "rich_text":
                text_array = prop_value.get("rich_text", [])
                simplified[prop_name] = "".join([t.get("plain_text", "") for t in text_array])
            elif prop_type == "number":
                simplified[prop_name] = prop_value.get("number")
            elif prop_type == "select":
                select_obj = prop_value.get("select")
                simplified[prop_name] = select_obj.get("name") if select_obj else None
            elif prop_type == "multi_select":
                multi_select = prop_value.get("multi_select", [])
                simplified[prop_name] = [item.get("name") for item in multi_select]
            elif prop_type == "date":
                date_obj = prop_value.get("date")
                simplified[prop_name] = date_obj.get("start") if date_obj else None
            elif prop_type == "checkbox":
                simplified[prop_name] = prop_value.get("checkbox")
            elif prop_type == "url":
                simplified[prop_name] = prop_value.get("url")
            elif prop_type == "email":
                simplified[prop_name] = prop_value.get("email")
            elif prop_type == "phone_number":
                simplified[prop_name] = prop_value.get("phone_number")
            else:
                # For other types, store the type
                simplified[prop_name] = f"[{prop_type}]"

        return simplified

    def _extract_block_text(self, blocks: List[Dict]) -> str:
        """Extract plain text from blocks"""
        text_parts = []

        for block in blocks:
            block_type = block.get("type")
            block_data = block.get(block_type, {})

            if "rich_text" in block_data:
                text_array = block_data["rich_text"]
                text = "".join([t.get("plain_text", "") for t in text_array])
                if text:
                    text_parts.append(text)
            elif "text" in block_data:
                text_array = block_data["text"]
                text = "".join([t.get("plain_text", "") for t in text_array]) if isinstance(text_array, list) else str(text_array)
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)
