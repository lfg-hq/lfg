# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LFG (Let's F***ing Go!) is an AI-powered product development platform that combines human creativity with artificial intelligence to accelerate software development. It's a Django-based application with real-time WebSocket communication, containerized code execution, and multi-provider AI integration.

## Common Commands

```bash
# Development Server
python manage.py runserver              # Start Django development server
uvicorn LFG.asgi:application --host 0.0.0.0 --port 8000 --workers 2  # ASGI server with WebSocket support

# Database Management
python manage.py migrate                # Apply database migrations
python manage.py makemigrations         # Create new migrations
python manage.py createsuperuser        # Create admin user

# Testing
python manage.py test                   # Run all tests
python manage.py test <app_name>        # Run tests for specific app (e.g., development, projects)

# Static Files
python manage.py collectstatic          # Collect static files
./copy_static.sh                        # Copy static files to staticfiles directory

# Environment Setup
source env.sh                          # Load development environment variables
source env.prod.sh                     # Load production environment variables

# Deployment
./prod_deploy.sh                       # Deploy to production using Kamal

# Docker Development
docker-compose up                      # Start all services (Django, Redis, PostgreSQL)

# Custom Management Commands
python manage.py show_token_usage      # Display AI token usage statistics
python manage.py create_default_plans  # Initialize subscription plans
```

## High-Level Architecture

### Core Django Apps

1. **accounts/** - User authentication, profiles, API key management
   - Custom Profile model extends Django User
   - Stores provider-specific API keys for AI services
   - GitHub integration for authentication

2. **chat/** - Real-time AI chat system
   - WebSocket consumer (`consumers.py`) handles bidirectional communication
   - Streaming AI responses with chunk-based delivery
   - File upload support and message persistence
   - Auto-save functionality for long conversations

3. **development/** - Code generation and execution
   - **docker/** - Container management for sandboxed execution
   - **k8s_manager/** - Kubernetes pod orchestration for production
   - **utils/ai_providers.py** - Multi-provider AI integration (Anthropic, OpenAI, XAI)
   - **utils/ai_tools.py** - Tool/function definitions for AI agents

4. **projects/** - Project and feature management
   - PRD generation and management
   - Feature breakdown into tickets
   - Linear integration for issue tracking
   - Git worktree support for parallel development

5. **subscriptions/** - Payment and credit system
   - Stripe integration for payments
   - Credit-based usage tracking
   - Webhook handling for subscription events

### AI Provider Architecture

The system uses a factory pattern for AI providers:
- Base `AIProvider` class with streaming and tool support
- Implementations: `AnthropicProvider`, `OpenAIProvider`, `xAIGrokProvider`
- User-specific API keys stored in Profile model
- Token usage tracking and cost calculation

### WebSocket Architecture

Real-time communication flow:
1. Client connects to WebSocket endpoint
2. Messages saved to database and processed asynchronously
3. AI responses streamed back in chunks
4. Tool executions trigger real-time UI updates via notifications

### Container Execution Environment

Two-tier container management:
- **Development**: Docker containers with resource limits
- **Production**: Kubernetes pods with namespace isolation
- Automatic cleanup and timeout mechanisms
- Volume mounting for code persistence

### Tool System

AI agents can execute tools defined in `ai_tools.py`:
- Code execution and file manipulation
- PRD and implementation planning
- Project and ticket management
- Linear integration operations
- Container and server management

## Development Guidelines

### Adding New AI Providers

1. Create a new class inheriting from `AIProvider` in `coding/utils/ai_providers.py`
2. Implement `generate_response()` and `generate_response_stream()` methods
3. Add provider configuration to model selection logic
4. Update frontend model selection dropdown

### WebSocket Message Handling

Messages follow this structure:
```python
{
    "type": "message" | "notification" | "heartbeat",
    "content": "...",
    "metadata": { ... }
}
```

### Tool Development

New tools must:
1. Be defined in `get_available_tools()` in `ai_tools.py`
2. Have a corresponding execution function
3. Include proper JSON schema for parameters
4. Send WebSocket notifications for UI updates

### Security Considerations

- Never expose API keys in responses
- Validate all tool inputs before execution
- Use resource limits for container execution
- Implement proper authentication for WebSocket connections

## Testing

Run tests for specific apps:
```bash
python manage.py test development.tests
python manage.py test projects.tests
python manage.py test subscriptions.tests
```

Key test areas:
- AI provider response generation
- WebSocket message handling
- Container lifecycle management
- Tool execution and validation
- Payment webhook processing