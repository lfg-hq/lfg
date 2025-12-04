# Design Canvas Architecture

## Overview

The Design Canvas is a Figma-like feature flow visualization system that allows users to:
1. Generate design previews for features with multiple screens
2. View and navigate between screens in a canvas interface
3. Edit designs using AI-powered chat
4. Compose pages with common elements (header, footer, sidebar)

## Architecture

### Key Concepts

1. **Page Content Partials**: Each page stores only its main content (no header/footer/sidebar)
2. **Common Elements**: Shared components (header, footer, sidebar) stored separately and composed at render time
3. **Composition**: When rendering, common elements are combined with page content based on position and applicability rules

### Data Model

#### ProjectDesignFeature Model (`projects/models.py`)

```python
class ProjectDesignFeature(models.Model):
    project = models.ForeignKey(Project, ...)
    conversation = models.ForeignKey('chat.Conversation', ...)  # Links to chat conversation
    feature_name = models.CharField(max_length=255)  # Unique per project
    feature_description = models.TextField()
    explainer = models.TextField()

    # Design data
    css_style = models.TextField()  # Shared CSS for all elements
    common_elements = models.JSONField(default=list)  # Header, footer, sidebar, etc.
    pages = models.JSONField(default=list)  # Page content partials
    entry_page_id = models.CharField(max_length=100)
    feature_connections = models.JSONField(default=list)  # Cross-feature navigation
    canvas_position = models.JSONField(default=dict)  # {x, y} position on canvas
```

#### Common Elements Structure

```json
{
    "element_id": "main-header",
    "element_type": "header",  // header, footer, sidebar, nav, logo, banner, breadcrumb, toolbar
    "element_name": "Main Header",
    "html_content": "<header>...</header>",
    "position": "top",  // top, bottom, left, right, fixed-top, fixed-bottom
    "applies_to": ["all"],  // or specific page_ids like ["dashboard", "settings"]
    "exclude_from": ["login"]  // pages to exclude this element from
}
```

#### Page Structure

```json
{
    "page_id": "dashboard",
    "page_name": "Dashboard",
    "page_type": "screen",  // screen, modal, drawer, popup, toast
    "html_content": "<main>...</main>",  // Main content ONLY, no header/footer
    "include_common_elements": true,
    "navigates_to": [
        {
            "target_page_id": "settings",
            "trigger": "Click Settings button",
            "condition": "optional condition"
        }
    ]
}
```

## Files Modified

### Backend

| File | Changes |
|------|---------|
| `projects/models.py` | Added `common_elements` JSONField to `ProjectDesignFeature` |
| `projects/views.py` | Updated `design_features_api` to return common_elements; Updated `design_chat_api` to handle editing both page content and common elements; Added `_compose_page_html()` helper |
| `projects/urls.py` | Added `design_chat_api` endpoint |
| `factory/ai_tools.py` | Added `edit_design_screen_anthropic` tool with `edit_target` and `element_id` fields; Created `tools_design_chat` array |
| `factory/ai_functions.py` | Updated `generate_design_preview()` to extract, sanitize, and save `common_elements` |

### Frontend

| File | Changes |
|------|---------|
| `static/js/design/design_canvas.js` | Added `composePageHtml()` method; Updated thumbnail/preview rendering to use composed HTML; Updated `updateScreenCard()` to handle both page and common element updates |
| `static/css/design/design_canvas.css` | Added styles for AI chat success/error states, disabled states |

### Migrations

- `projects/migrations/0039_add_common_elements_to_design_feature.py`

## API Endpoints

### GET `/projects/<project_id>/api/design-features/`

Returns all design features for a project.

**Response:**
```json
{
    "success": true,
    "features": [
        {
            "feature_id": 123,
            "feature_name": "Authentication",
            "feature_description": "...",
            "css_style": "...",
            "common_elements": [...],
            "pages": [...],
            "entry_page_id": "login",
            "feature_connections": [...],
            "canvas_position": {"x": 100, "y": 100}
        }
    ]
}
```

### POST `/projects/<project_id>/api/design-chat/`

AI-powered design editing endpoint.

**Request:**
```json
{
    "feature_id": 123,
    "page_id": "dashboard",
    "message": "Make the header background blue"
}
```

**Response:**
```json
{
    "success": true,
    "updated_html": "<header>...</header>",
    "updated_css": "...",  // optional
    "composed_html": "...",  // full page with common elements
    "edit_target": "common_element",  // or "page_content"
    "element_id": "main-header",  // only if edit_target is "common_element"
    "change_summary": "Changed header background to blue",
    "assistant_message": "..."
}
```

## Tool Definitions

### generate_design_preview (for AI generation)

Located in `factory/ai_tools.py`. Used when AI generates new design previews.

Key parameters:
- `feature_name`, `feature_description`, `explainer`
- `css_style` - shared CSS
- `common_elements` - array of header/footer/sidebar definitions
- `pages` - array of page content partials (main content only)
- `entry_page_id`
- `feature_connections`

### edit_design_screen (for AI editing)

Located in `factory/ai_tools.py` as `edit_design_screen_anthropic` (Anthropic native format).

Key parameters:
- `edit_target`: "page_content" or "common_element"
- `element_id`: Required when edit_target is "common_element"
- `updated_html`: The updated HTML content
- `updated_css`: Optional CSS updates
- `change_summary`: Brief description of changes

## HTML Composition Logic

### Backend (`_compose_page_html` in views.py)

```python
def _compose_page_html(page, common_elements, page_id):
    # 1. Filter applicable elements (applies_to/exclude_from)
    # 2. Sort by position (top -> left/right -> bottom)
    # 3. Compose:
    #    - Top elements (header, nav)
    #    - Layout wrapper with left sidebar + main content + right sidebar
    #    - Bottom elements (footer)
```

### Frontend (`composePageHtml` in design_canvas.js)

Same logic replicated in JavaScript for client-side rendering of thumbnails and previews.

## User Flow

### Generating Design Previews

1. User enables "Design" toggle in chat
2. User requests design generation (e.g., "Generate design for authentication feature")
3. AI calls `generate_design_preview` tool with:
   - Common elements (header, footer, sidebar)
   - Page content partials (login, register, forgot-password)
4. Data saved to `ProjectDesignFeature` model
5. Design appears in Design Canvas tab

### Editing Designs with AI

1. User clicks magic wand icon on a screen card
2. AI chat panel slides in
3. User describes changes (e.g., "Make the header blue")
4. Request sent to `/api/design-chat/`
5. AI determines what to edit:
   - If header/footer/sidebar change: `edit_target="common_element"`
   - If main content change: `edit_target="page_content"`
6. Database updated with new HTML
7. Screen card thumbnail and preview modal updated

## Preview Modal Navigation

- Left/right arrow buttons to navigate between screens
- Keyboard support (Arrow keys, Escape)
- Breadcrumb title: `Feature Name → Screen Name`
- Counter: `1 / 5`

## Fullscreen Mode

- Press `F` or click fullscreen button
- Uses `position: fixed` with `z-index: 999999`
- Press `Escape` or `F` to exit

## CSS Architecture

All design CSS is stored in `css_style` field and shared across:
- Common elements (header, footer, sidebar)
- Page content partials
- Composed full pages

The CSS should include styles for:
- `.layout-wrapper` - flex container for sidebar layouts
- `.main-content` - main content area
- Common element classes (header, footer, sidebar styles)
