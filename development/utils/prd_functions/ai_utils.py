import openai
import os
import json
from .ai_tools import feature_difference, persona_difference, generate_design_schema, generate_ticket_tools
import logging

logger = logging.getLogger(__name__)

def analyze_features(feature_list, prd):
    """
    Analyze the features and provide insights or suggestions for improvement.
    """
    logger.info("Analyzing features function called")
    
    # Create a function call to OpenAI
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """
You are FeatureDiffBot.  
Your ONLY task is to compare two inputs and report what’s missing:

INPUTS
1. existing_features – an array of strings.  
   • Treat the text BEFORE the first colon (:) in each string as the canonical feature name.  
   • Trim whitespace and compare names case‑insensitively.

2. PRD – free‑form text that contains a “Features” section with bullet‑ or number‑listed feature names.

WHAT TO DO
1. Build Set A from the canonical names in existing_features.  
2. Extract the canonical names from the PRD’s Features section and build Set B.  
3. Compute Set C = B − A (features present in the PRD but absent from the existing list).

OUTPUT
Call feature_difference() exactly once with JSON matching this schema:

{
  "features": [
    {
      "name": "<canonical feature name>",
      "description": "<one‑sentence summary>",
      "details": "<3–4 sentences elaborating on what the feature does>",
      "priority": "High" | "Medium" | "Low"
    }
  ]
}

If Set C is empty, return:
feature_difference({"features":[]})

RULES
• Do NOT return any feature that already exists in existing_features.  
• Ignore everything in the PRD except the Features section.  
• Produce ONLY the feature_difference() call—no extra text, markdown, or commentary.
"""
    
    # Prepare the prompt
    prompt = f"You will be provided a list of existing features for the project and the corresponding PRD file." + \
                "You will analyze the PRD and identify features that are missing from the provided list." + \
                "You will send back the missing features from the list, but are there in the PRD." + \
                "Do no send the features if they are already in the provided list." + \
                "\n\nHere is the list of the existing features for this project:\n"
    prompt += "feature_list: " + json.dumps(feature_list) + "\n"
    
    prompt += "\n----------------------------------\n"
    prompt += f"\nHere is the PRD for this project: \n<prd>\n {prd}\n</prd>\n----------------------------------\n"
    
    logger.debug(f"Features Prompt: {prompt}")

    # Make the API call
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        tools=[feature_difference],
        tool_choice={"type": "function", "function": {"name": "feature_difference"}}
    )
    
    # Process the response - handle tool calls if present
    message = response.choices[0].message
    
    if message.tool_calls:
        # Get the function call
        function_call = message.tool_calls[0]
        function_name = function_call.function.name
        
        if function_name == "feature_difference":
            logger.debug(f"Extract features function called: {function_call.function.arguments}")
            # Extract the tool response which should contain the missing features
            return function_call.function.arguments
    
    # Fallback to content if no tool calls were made
    return message.content


def analyze_personas(persona_list, prd):
    """
    Analyze the personas and provide insights or suggestions for improvement.
    """
    logger.info("Analyzing personas function called")
    
    # Create a function call to OpenAI
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """
You are PersonaDiffBot.  
Your ONLY task is to compare two inputs and report what’s missing:

INPUTS
1. existing_personas – an array of strings.  
   • Treat the text BEFORE the first colon (:) in each string as the canonical persona name.  
   • Trim whitespace and compare names case‑insensitively.

2. PRD – free‑form text that contains a Personas section with bullet‑ or number‑listed persona names.

WHAT TO DO
1. Build Set A from the canonical names in existing_personas.  
2. Extract the canonical names from the PRD’s Personas section and build Set B.  
3. Compute Set C = B − A (personas present in the PRD but absent from the existing list).

OUTPUT
Call persona_difference() exactly once with JSON matching this schema:

{
  "personas": [
    {
      "name": "<canonical persona name>",
      "role": "<one‑sentence summary>",
      "description": "<3–4 sentences elaborating on the persona role>",
    }
  ]
}

If Set C is empty, return:
persona_difference({"personas":[]})

RULES
• Do NOT return any persona that already exists in existing_personas.  
• Ignore everything in the PRD except the Personas section.  
• Produce ONLY the persona_difference() call—no extra text, markdown, or commentary.
"""
    
    # Prepare the prompt
    prompt = f"You will be provided a list of existing personas for the project and the corresponding PRD file." + \
                "You will analyze the PRD and identify personas that are missing from the provided list." + \
                "You will send back the missing personas from the list, but are there in the PRD." + \
                "Do no send the personas if they are already in the provided list." + \
                "\n\nHere is the list of the existing personas for this project:\n"
    prompt += "persona_list: " + json.dumps(persona_list) + "\n"


    prompt += "\n----------------------------------\n"
    prompt += f"\nHere is the PRD for this project: \n<prd>\n {prd}\n</prd>\n----------------------------------\n"
    
    logger.debug(f"Personas Prompt: {prompt}")
    

    # Make the API call
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        tools=[persona_difference],
        tool_choice={"type": "function", "function": {"name": "persona_difference"}}
    )
    
    # Process the response - handle tool calls if present
    message = response.choices[0].message
    
    if message.tool_calls:
        # Get the function call
        function_call = message.tool_calls[0]
        function_name = function_call.function.name
        
        if function_name == "persona_difference":
            # Extract the tool response which should contain the missing personas
            return function_call.function.arguments
    
    # Fallback to content if no tool calls were made
    return message.content


def design_schema(prd, current_style_guide, user_input):
    """
    Generate a design schema for a project based on the PRD and user input.
    """
    logger.info("Design schema function called")
    
    # Create a function call to OpenAI
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """
    You are DesignSchemaBot, an expert UI/UX designer about to generate a style guide for a web application.

Your mission
============
1. Read the Product Requirements Document wrapped in <prd>…</prd> tags, the current design schema wrapped in <current_style_guide>…</current_style_guide> tags and any extra user notes that follow.  
IMPORTANT: Whatever instructions user sends, it is only pertaining to the style guide. 
2. Generate a **complete design schema** for a *web application*, covering at minimum:  
   • Color palette (friendly names + HEX codes)  
   • Typography (families, weights, sizes in px and rem)  
   • Spacing, border‑radius, shadow tokens  
   • UI component specs (buttons, cards, icons, etc.)  
   • Accessibility guidance (contrast ratios, focus rings)  
3. Render the output as one self‑contained HTML document:  
   • Page background **#000000**, base text **#FFFFFF**  
   • Inline `<style>` only—no external CSS or scripts  
   • All content inside `<main style="padding:0 24px">`  
   • Show color swatches with class `swatch` (`width:48px;height:24px;border:1px solid #555;border-radius:4px;`)  
   • **Use the exact TABLE‑BASED structure shown below—never switch to lists**  
   • Insert `<!-- DesignSchemaBot v1 skeleton — do not edit -->` immediately after `<main>` so diffs stay predictable  
   • Do **not** include navigation bars, footers, analytics, lorem‑ipsum, or filler  
4. Return **only** the HTML document (or, if you are answering a function call, place that HTML in the single string field requested). No Markdown, no explanations, no code fences.

Skeleton (must be followed exactly)
-----------------------------------
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Style Guide – {project_name}</title>
<style>
  body{margin:0;background:#000;color:#FFF;font-family:Inter,Arial,sans-serif;}
  main{max-width:960px;margin:auto;padding:0 24px;}
  h1,h2,h3{margin:1.2em 0 0.6em;}
  table{width:100%;border-collapse:collapse;margin-bottom:1.5em;}
  th,td{padding:8px;text-align:left;border-bottom:1px solid #333;}
  .swatch{width:48px;height:24px;border:1px solid #555;border-radius:4px;display:inline-block;vertical-align:middle;margin-right:8px;}
</style>
</head>
<body>
<main>
<!-- DesignSchemaBot v1 skeleton — do not edit -->

  <!-- 1. Overview -->
  <h1>Style Guide – {project_name}</h1>
  <p>{quick_summary}</p>

  <!-- 2. Color Palette -->
  <h2>Color Palette</h2>
  <table>
    <thead><tr><th>Swatch</th><th>Name</th><th>Usage</th><th>HEX</th></tr></thead>
    <tbody>
      <!-- repeat one <tr> per color -->
      <tr><td><span class="swatch" style="background:#FFC928;"></span></td><td>Golden Retriever (Primary)</td><td>CTAs & Icons</td><td>#FFC928</td></tr>
    </tbody>
  </table>

  <!-- 3. Typography -->
  <h2>Typography</h2>
  <table>
    <thead><tr><th>Use</th><th>Font</th><th>Weight</th><th>Size</th><th>Line‑height</th></tr></thead>
    <tbody>
      <!-- repeat rows -->
      <tr><td>Body</td><td>Inter</td><td>400</td><td>16 px / 1 rem</td><td>1.4</td></tr>
    </tbody>
  </table>

  <!-- 4. UI Components -->
  <h2>UI Components</h2>
  <table>
    <thead><tr><th>Component</th><th>Spec</th></tr></thead>
    <tbody>
      <tr><td>Primary Button</td><td>bg #FFC928, text #000, radius 8 px, padding 12 px 24 px</td></tr>
      <!-- more rows -->
    </tbody>
  </table>

  <!-- 5. Accessibility -->
  <h2>Accessibility Notes</h2>
  <ul>
    <li>Maintain ≥ 4.5:1 contrast for body text.</li>
    <li>Focus ring: 2 px solid #FFC928 on dark backgrounds.</li>
  </ul>

</main>
</body>
</html>

    """

    logger.debug(f"System Prompt: {system_prompt}")

    user_prompt = f"""
    Here is the PRD for this project:
    <prd>
    {prd}
    </prd>  
    Here is the user input for this project:
    {user_input}
    
    Here is the current design schema for this project, which you will modify as per user input:
    <current_style_guide>
    {current_style_guide}
    </current_style_guide>
    """
    
    # Make the API call
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        tools=[generate_design_schema],
        tool_choice={"type": "function", "function": {"name": "generate_design_schema"}}
    )

    # Process the response - handle tool calls if present
    message = response.choices[0].message
    
    if message.tool_calls:
        # Get the function call
        function_call = message.tool_calls[0]
        function_name = function_call.function.name
        
        if function_name == "generate_design_schema":
            # Extract the tool response which should contain the design schema
            return function_call.function.arguments
    
    # Fallback to content if no tool calls were made
    return message.content  


def generate_tickets_per_feature(feature, personas, prd):
    """
    Generate tickets for a project based on the PRD and user input.
    """
    logger.info("Generate tickets function called")
    
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """
    You are TicketBot, an expert ticket generator for a web application. 
    You will review the provided PRD, the feature request and the personas, and generate a list of 
    tickets for the provided feature. Note that these tickets will be further used for software development:
    - generate the backend code
    - generate the frontend code
    
    You will receive the project PRD in the <prd> tags.
    You will receive the feature request in the <feature> tags.
    You will receive the personas in the <personas> tags.

    You will generate a list of tickets for the provided feature.
    Each ticket will have a title, a description, a status, and a list of backend and frontend tasks.

    For the provided feature, think of all the use-cases that need to be handled and generate tickets for each use-case.

    Review how the features are interconnected to each other. While generating tickets, 
    consider how these tickets fit into the overall architecture of the project.
    """
    
    user_prompt = f"""
    Here is the PRD for this project:
    <prd>
    {prd}
    </prd>  
    Here is the feature request for this project:
    <feature>
    {feature}
    </feature>
    Here are the personas for this project:
    <personas>
    {personas}
    </personas>
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        tools=[generate_ticket_tools],
        tool_choice={"type": "function", "function": {"name": "generate_ticket_tools"}}  
    )

    message = response.choices[0].message
    
    if message.tool_calls:
        # Get the function call
        function_call = message.tool_calls[0]
        function_name = function_call.function.name
        
        if function_name == "generate_ticket_tools":
            # Extract the tool response which should contain the design schema
            return function_call.function.arguments
    # Fallback to content if no tool calls were made
    return message.content


def generate_project_code(user_input):
    """
    Generate a code prompt for a project based on the user input.
    """
    logger.info("Generate code prompt function called")
    
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """
    You are CodeBot, an expert code generator for a web application. 
    You will receive the user input for this project and generate the code for the project.

    You will maintain an internal Readme file, which has the specs or features or user-request mapped to the code files that you will generate.
    This readme file should first start with directory tree structure, with each files listed. Name this file as "ai_code.readme".
    Note that this file is only for AI code generation and mapping the components. This is kind of useless to the user. 

    Before generating the code, you will request this readme file "ai_code.readme". 

    Get as much context as you can from the existing project if you need to.

    You have two tools available:
    - get_file(): to fetch the file from the storage directory.
    - write_file(): to write the file to the storage directory. You will write the file in patch-diff mode. 

    """

    user_prompt = f"""
    Here is the user input for this project:
    {user_input}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )