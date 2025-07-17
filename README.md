# LFG 🚀 | AI-Powered Product Development Platform

> **Streamline your SDLC process with AI** - The open-source platform that helps bring method to the madness. Structure your requirements gathering, development, QA, and deployments with AI. 

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.0+-green.svg)](https://djangoproject.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red.svg)](https://github.com/lfg-hq/lfg)

## 🌟 Overview

LFG is an agentic framework for AI development teams, helping you automate the SDLC.

The AI-powered platform that combines different roles like Product Managers, Developers, and Designers in one intelligent workspace. Create PRDs, build apps, fix bugs, and ship faster than ever. LFG helps you research and analyze ideas. Assess them before you build. 

### ✨ What is LFG's mission?

- **🚀 Ship 10x Faster**: Automate away the mundane and focus on what matters - the problems you care about, your customers, and your creativity.
- **🤖 AI Dream Team**: Different roles like product managers, developers, QA engineers, and designers working 24/7, helping you ship your dream product
- **💡 Human + AI Collaboration**: Enhancing creativity, not replacing it
- **🔓 100% Open Source**: No vendor lock-in, complete transparency
- **🎯 Production-Ready**: Built for real products, not just demos
- **🛠️ Fully Customizable**: Choose your AI models, tech stack, and deployment

We are starting with baby steps. 

As of now, we are solving the requirements gathering process. LFG helps you research and analyze ideas, write PRDs, create technical docs, and generate tickets (and sync them with Linear). 

## 🚀 Features

### 🤖 Meet Your AI Team

**Product Manager Agent**
- Transforms ideas into comprehensive PRDs
- Creates user stories and acceptance criteria
- Prioritizes features based on impact
- Manages product roadmap and timelines

**Developer Agent (coming soon)**
- Writes production-ready code
- Implements features from tickets
- Debugs and optimizes performance
- Follows best practices and patterns


### 💻 Core Capabilities

- **📝 Smart PRD Generation**: Transform your ideas into comprehensive Product Requirements Documents with AI-powered insights
- **🎯 Intelligent Ticket System**: Automatically break down complex features into actionable, prioritized tickets

### 🎨 Customization & Flexibility

- **Choose Your AI**: Support for OpenAI GPT-4 and Anthropic Claude models
- **Tech Stack Freedom**: Use any programming language or framework
- **Deployment Options**: Deploy anywhere - cloud, on-premise, or hybrid
- **Custom Workflows**: Adapt the platform to your team's processes
- **API Integration**: Connect with your existing tools and services 

## 🛠️ Get Started Locally

Set up LFG on your machine in just a few minutes!

### System Requirements
- ✅ Python 3.9 or higher
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

You'll need at least one AI provider API key to use LFG:

- **OpenAI**: Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic**: Get your API key from [Anthropic Console](https://console.anthropic.com/settings/keys)
- **xAI (Grok)**: Get your API key from [xAI Console](https://console.x.ai/)

### Docker Setup (Alternative)

```bash
# Build and run with Docker Compose
docker-compose up --build

# Access at http://localhost:8000
```

## 💡 Use Cases

### Perfect For:

**🚀 Startups & Indie Hackers**
- Rapid prototyping and MVP development
- Iterate quickly based on user feedback
- Build without a full development team

**👥 Development Teams**
- Accelerate feature development
- Automate repetitive coding tasks
- Maintain consistent code quality

**🏢 Enterprises**
- Standardize development workflows
- Reduce time-to-market
- Scale development capacity

**🎓 Learning & Education**
- Learn best practices from AI
- Understand code architecture
- Build real projects faster

## 📁 Project Structure

```
lfg/
├── accounts/           # User authentication and profiles
├── chat/              # AI chat and collaboration system
├── development/       # Code generation and execution
│   └── utils/         # AI prompts, tools, and utilities
├── projects/          # Project management and organization
├── subscriptions/     # Subscription and credit management
├── templates/         # HTML templates
│   └── home/          # Landing pages and marketing
├── static/           # Static files (CSS, JS, images)
├── media/            # User-uploaded files
├── config/           # Configuration files
├── LFG/              # Core Django settings
└── requirements.txt  # Python dependencies
```

### 🔧 Core Modules Explained

#### **accounts/**
Manages user authentication, profiles, and API key storage. This module handles:
- User registration and login (including OAuth with Google/GitHub)
- Profile management where users store their AI provider API keys
- User preferences and settings
- Session management and authentication middleware

#### **development/**
The heart of the AI-powered development features. This module contains:
- **AI Provider Integration**: Factory pattern implementation for multiple AI providers (OpenAI, Anthropic, xAI)
- **Tool System**: Defines AI agent tools for code execution, file manipulation, PRD generation, and project management
- **Streaming Responses**: Real-time AI response streaming with token usage tracking

#### **projects/**
Handles all project-related functionality including:
- Project creation and management
- PRD and Technical documentation management (saving and editing)
- Ticket management with AI-powered breakdown
- Linear integration for syncing tickets with external project management tools

### 🔧 Key Components

- **AI Prompts & Tools**: Located in `development/utils/` - contains all the AI prompts, agent definitions, and utility functions that power the intelligent features
- **Agent System**: Specialized AI agents (Product Manager, Developer, Designer) with their respective prompts and behaviors
- **Code Execution**: Sandboxed environments using Docker for secure code execution

## 🔧 Configuration

### Environment Variables

Create a `.env` file or configure `env.sh` with the following variables:

```bash
# Django Settings
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True  # Set to False in production
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (PostgreSQL)
DATABASE_URL=postgres://user:password@localhost:5432/lfg_db
# Or use SQLite for local development
# DATABASE_URL=sqlite:///db.sqlite3

# AI Provider API Keys (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
XAI_API_KEY=xai-...

# Redis Configuration (for WebSocket support)
REDIS_URL=redis://localhost:6379/0

# Email Configuration (optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Stripe Configuration (optional, for payments)
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Linear Integration (optional)
LINEAR_API_KEY=lin_api_...

# GitHub OAuth (optional)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Google OAuth (optional)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

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
  
**🚀 Ready to ship 10x faster?**

[Get Started](https://github.com/lfg-hq/lfg) • [Documentation](docs/) • [Report Issue](https://github.com/lfg-hq/lfg/issues)

**LFG - Let's F* Go! 🚀**

</div> 