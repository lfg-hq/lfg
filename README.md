# LFG Platform

LFG is a collaborative AI-assisted development platform that helps teams build software faster.

## Features

- AI-assisted code development and chat
- Project management and organization
- Docker-based sandboxes for code execution
- Kubernetes pod management for remote environments
- Subscription and credit management

## Getting Started

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment variables in `.env`
4. Run migrations: `python manage.py migrate`
5. Start the development server: `python manage.py runserver`

## Kubernetes Pod Management

The platform includes a robust system for creating and managing Kubernetes pods remotely. This allows for:

- Creation of isolated development environments for each project
- Remote code execution in secure containers
- Persistence of environment details in the database

For complete documentation on the Kubernetes pod management system, see:
- [Kubernetes Quick Start Guide](README-K8S.md)
- [Detailed Kubernetes Documentation](coding/k8s_manager.py/README.md)

## Docker Sandboxes

In addition to Kubernetes pods, the platform also supports local Docker-based sandboxes for development and code execution.

## Project Structure

- `accounts/` - User authentication and account management
- `chat/` - Real-time chat and AI collaboration system
- `coding/` - Code generation and execution systems
  - `coding/docker/` - Docker sandbox management
  - `coding/k8s_manager.py/` - Kubernetes pod management
- `projects/` - Project management and organization
- `subscriptions/` - Subscription and credit management
- `templates/` - HTML templates for the web interface
- `static/` - Static files (CSS, JS, images)
- `LFG/` - Core application settings and configuration

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Trademark Notice:** "LFG" and "lfg.run" are trademarks. The MIT license does not grant trademark rights. 