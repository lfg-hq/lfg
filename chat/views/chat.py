import json
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from chat.models import Conversation, Message
from django.conf import settings
from chat.utils.ai_providers import AIProvider
from django.contrib.auth.decorators import login_required


prompt = """
You are an expert technical product manager. You will respond in markdown format. You will greet the user
saying that you are michael scott.

You will offer your help in helping the client build useful web apps and other software. 

You will also offer to help the client with their projects.

When they provide a requirement, and if it is not clear or absurd, you will ask for clarification..

You will ask questions as many times as required. 

Then when you have enough information, you will create a rough PRD of the project and share it 
with the client. You will ask for clarification and only proceed after that.

In the PRD, you will primarily work towards defining the features, the personas who might use the app,
the core functionalities, the design layout, etc.

"""

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def chat_api__to_be_removed(request):
    """Handle chat API requests and stream responses."""
    data = json.loads(request.body)
    user_message = data.get('message', '')
    conversation_id = data.get('conversation_id')
    project_id = data.get('project_id')
    provider_name = data.get('provider', settings.AI_PROVIDER_DEFAULT)
    
    # Get or create conversation
    if conversation_id:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = Conversation.objects.create(
            user=request.user,
            title=user_message[:50]
        )
    
    # Save user message
    Message.objects.create(
        conversation=conversation,
        role='user',
        content=user_message
    )
    
    # Get conversation history
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in conversation.messages.all()
    ]
    
    # Add system message if not present
    if not any(msg["role"] == "system" for msg in messages):
        messages.insert(0, {
            "role": "system",
            "content": prompt
        })
    
    # Get the appropriate AI provider
    ai_provider = AIProvider.get_provider(provider_name)
    
    def generate_response():
        full_response = ""
        
        # Use the selected AI provider to generate a response
        try:
            for content in ai_provider.generate_stream(messages):
                full_response += content
                yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
        except Exception as e:
            error_message = f"Error: {str(e)}"
            yield f"data: {json.dumps({'content': error_message, 'done': False})}\n\n"
            full_response += error_message
        
        # Save assistant message
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=full_response
        )
        
        # Update conversation title if it's new
        if not conversation.title or conversation.title == conversation.id:
            # Generate title using AI based on the conversation
            try:
                # Create a special prompt for title generation
                title_prompt = [
                    {
                        "role": "system",
                        "content": "Generate a short, concise title (maximum 50 characters) that summarizes this conversation. The title should capture the main topic or purpose of the discussion. Only respond with the title text, no additional commentary or formatting."
                    },
                    {
                        "role": "user", 
                        "content": f"User: {user_message[:200]}...\nAI: {full_response[:200]}..."
                    }
                ]
                
                # Generate the title
                title = ""
                for content in ai_provider.generate_stream(title_prompt):
                    title += content
                
                # Clean and truncate the generated title
                title = title.strip()
                if len(title) > 50:
                    title = title[:47] + "..."
                
                # Update the conversation title
                conversation.title = title
                conversation.save()
                print(f"Generated title for conversation {conversation.id}: {title}")
            except Exception as e:
                # Fallback to original behavior
                print(f"Error generating title: {str(e)}")
                conversation.title = user_message[:50]
                conversation.save()
            
        # Get project_id if conversation is linked to a project
        project_id = None
        if hasattr(conversation, 'projects'):
            projects = conversation.projects.all()
            if projects.exists():
                project_id = projects.first().id
            
        yield f"data: {json.dumps({'content': '', 'done': True, 'conversation_id': conversation.id, 'provider': provider_name, 'project_id': project_id})}\n\n"
    
    return StreamingHttpResponse(
        generate_response(),
        content_type='text/event-stream'
    )
