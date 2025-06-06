# Fix for Claude JSON Schema Validation Error

## Problem
Getting error when using Claude/Anthropic:
```
tools.5.custom.input_schema: JSON schema is invalid. It must match JSON Schema draft 2020-12 
```

## Root Cause
The `checklist_tickets` tool (tool #5 in the tools array) had a duplicate entry in its `required` array:

```python
"required": ["name", "description", "priority", "role", "ui_requirements", "component_specs", "acceptance_criteria", "priority"]
#                                    ^^^^^^^^                                                                            ^^^^^^^^
#                                    Duplicate!
```

Having duplicate values in a JSON Schema `required` array violates the JSON Schema specification, which requires the array to contain unique values.

## Solution
Removed the duplicate "priority" entry from the required array in `coding/utils/ai_tools.py` line 245:

### Before:
```python
"required": ["name", "description", "priority", "role", "ui_requirements", "component_specs", "acceptance_criteria", "priority"]
```

### After:
```python
"required": ["name", "description", "role", "ui_requirements", "component_specs", "acceptance_criteria", "priority"]
```

## Result
The JSON schema is now valid according to JSON Schema draft 2020-12 specification, and Claude will accept the tool definitions without error.

## Note
This type of error can occur with:
- Duplicate entries in `required` arrays
- Invalid enum values
- Incorrect type specifications
- Missing required schema properties
- Using Python-specific values that don't translate well to JSON (though `False` → `false` is handled correctly)