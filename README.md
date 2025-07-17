# LFG 🚀 | AI-Powered Product Development Platform

> **AI-Powered Product Development Platform** - The open-source platform that accelerates software development by combining human creativity with AI assistance. Transform ideas into comprehensive PRDs, technical specifications, and actionable development tickets.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.0+-green.svg)](https://djangoproject.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red.svg)](https://github.com/lfg-hq/lfg)

## 🌟 Overview

LFG is an AI-powered product development platform designed to streamline the software development lifecycle. It helps teams transform ideas into well-structured Product Requirements Documents (PRDs), break down features into actionable tickets, and provide technical implementation guidance.

### ✨ Why LFG?

- **📝 Smart PRD Generation**: Transform ideas into comprehensive product requirements with AI assistance
- **🎯 Intelligent Ticket Creation**: Automatically break down features into actionable, prioritized development tickets
- **💡 Technical Analysis**: Get implementation guidance and architectural recommendations
- **🔓 100% Open Source**: Complete transparency and control over your development workflow
- **🛠️ Flexible Integration**: Works with your existing tools and AI providers (OpenAI, Anthropic)
- **🚀 Accelerated Development**: Reduce planning overhead and focus on building

## 🚀 Features

### 📋 Core Capabilities

**PRD Generation**
- Transform high-level ideas into detailed Product Requirements Documents
- Include user stories, acceptance criteria, and success metrics
- Structure features with clear scope and dependencies
- Generate technical constraints and considerations

**Ticket Management**
- Automatically break down PRDs into development tickets
- Prioritize tasks based on dependencies and impact
- Create clear implementation steps for each ticket
- Integration with project management tools (Linear)


### 💻 Technical Features

- **🤖 Multi-Provider AI Support**: Choose between OpenAI GPT-4 and Anthropic Claude models
- **💬 Real-time Chat Interface**: Interactive AI assistance with context awareness
- **📁 File Management**: Upload and analyze existing codebases and documentation
- **🔧 Customizable Workflows**: Adapt the platform to your team's processes
- **📊 Token Usage Tracking**: Monitor AI usage and manage costs effectively
- **🔐 Secure API Key Management**: Store provider API keys securely per user
- **🌐 Web-based Interface**: Access from anywhere with a modern browser

### 🎨 Integration & Extensibility

- **Linear Integration**: Sync tickets directly to your Linear workspace
- **GitHub Authentication**: Secure login with GitHub OAuth
- **Webhook Support**: Real-time updates for subscription and payment events
- **API Ready**: RESTful APIs for custom integrations
- **Containerized Execution**: Safe code execution in isolated environments 

## 🛠️ Get Started Locally

Set up LFG on your machine in just a few minutes!

### System Requirements
- ✅ Python 3.8 or higher
- ✅ PostgreSQL or SQLite
- ✅ Node.js 16+ (for frontend assets)
- ✅ Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/lfg-hq/lfg.git
   ```

2. **Create virtual environment**
   ```bash
   cd lfg && python -m venv venv && source venv/bin/activate
   ```
   On Windows: `cd lfg && python -m venv venv && venv\Scripts\activate`

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment**
   ```bash
   cp .env.example .env
   ```
   Configure your environment variables and add your API keys

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Start the development server**
   ```bash
   uvicorn LFG.asgi:application --host 0.0.0.0 --port 8000 --workers 2
   ```

   Launch LFG locally and access it at [http://localhost:8000](http://localhost:8000)

### 🔑 Required API Keys

You'll need at least one of these AI provider API keys:

- **OpenAI**: GPT-4 models - [Get API Key →](https://platform.openai.com/api-keys)
- **Anthropic**: Claude models - [Get API Key →](https://www.anthropic.com/api)

### Docker Setup (Alternative)

```bash
# Build and run with Docker Compose
docker-compose up --build

# Access at http://localhost:8000
```

## 💡 Use Cases

### Perfect For:

**📱 Product Managers**
- Quickly draft comprehensive PRDs from initial ideas
- Structure feature requirements with technical considerations
- Generate user stories and acceptance criteria

**👥 Development Teams**
- Convert PRDs into actionable development tickets
- Get technical implementation guidance
- Maintain consistent documentation standards

**🚀 Startups**
- Accelerate product planning and specification
- Structure ideas into actionable development plans
- Reduce time from concept to implementation

**🏢 Enterprises**
- Standardize requirement documentation processes
- Ensure comprehensive technical analysis
- Improve cross-team communication

## 📁 Project Structure

```
lfg/
├── accounts/           # User authentication and profiles
├── chat/              # AI chat and collaboration system
├── coding/            # Code generation and execution
│   ├── docker/        # Docker sandbox management
│   ├── k8s_manager/   # Kubernetes pod management
│   └── utils/         # AI prompts, tools, and utilities
├── projects/          # Project management and organization
├── subscriptions/     # Subscription and credit management
├── templates/         # HTML templates
│   └── marketing/     # Landing pages and marketing
├── static/           # Static files (CSS, JS, images)
├── media/            # User-uploaded files
├── config/           # Configuration files
├── LFG/              # Core Django settings
└── requirements.txt  # Python dependencies
```

### 🔧 Key Components

- **AI Integration**: Located in `development/utils/` - handles AI provider connections and response streaming
- **Chat System**: WebSocket-based real-time communication for interactive AI assistance
- **Project Management**: PRD generation, ticket creation, and Linear integration
- **Container Management**: Docker and Kubernetes integration for secure code execution environments

## 🔧 Configuration

### Environment Variables

Create a `.env` file or configure `env.sh` with the following variables:

## 🤝 Contributing

We welcome contributions from the community! Here's how you can help:

### Getting Started
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines
- Follow PEP 8 for Python code
- Write comprehensive tests
- Update documentation for new features
- Ensure all tests pass before submitting


## 🆘 Support

Need help? We're here for you!

- **📚 Documentation**: Check our comprehensive [docs](https://github.com/lfg-hq/lfg/blob/main/README.md)
- **🐛 Issues**: Report bugs on [GitHub Issues](https://github.com/lfg-hq/lfg/issues)
- **🌟 Star us**: If you find LFG helpful, [give us a star](https://github.com/lfg-hq/lfg)!

## 🌟 Why Open Source?

We believe the future of software development should be:
- **Transparent**: See exactly how your AI agents work
- **Customizable**: Modify anything to fit your needs
- **Community-Driven**: Built by developers, for developers
- **Forever Free**: Core features will always be open source

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Trademark Notice**: "LFG" and related trademarks are property of Microgigs Inc. The MIT license does not grant trademark rights.

---

<div align="center">
  
**🚀 Ready to accelerate your product development?**

[Get Started](https://github.com/lfg-hq/lfg) • [Documentation](docs/) • [Report Issue](https://github.com/lfg-hq/lfg/issues)

**LFG - Let's F***ing Go! 🚀**

*Forever open source. Built with ❤️ by the community.*

</div> 