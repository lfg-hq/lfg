# LFG 🚀 | AI-Powered Product Development Platform

> **Ship 10x Faster with AI** - The open-source platform that brings together the best of human creativity and artificial intelligence. Build products with specialized AI agents working as your virtual team.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.0+-green.svg)](https://djangoproject.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red.svg)](https://github.com/lfg-hq/lfg)

## 🌟 Overview

LFG is an Agentic framework for AI dev team. .

The AI-powered platform that combines Product Managers, Developers, and Designers in one intelligent workspace. Create PRDs, build apps, fix bugs, and ship faster than ever.

### ✨ Why LFG?

- **🚀 Ship 10x Faster**: Accelerate development with AI agents handling repetitive tasks
- **🤖 AI Dream Team**: Product managers, developers, and designers working 24/7
- **💡 Human + AI Collaboration**: Enhance creativity, don't replace it
- **🔓 100% Open Source**: No vendor lock-in, complete transparency
- **🎯 Production-Ready**: Built for real products, not just demos
- **🛠️ Fully Customizable**: Choose your AI models, tech stack, and deployment

## 🚀 Features

### 🤖 Meet Your AI Team

**Product Manager Agent**
- Transforms ideas into comprehensive PRDs
- Creates user stories and acceptance criteria
- Prioritizes features based on impact
- Manages product roadmap and timelines

**Developer Agent**
- Writes production-ready code
- Implements features from tickets
- Debugs and optimizes performance
- Follows best practices and patterns


### 💻 Core Capabilities

- **📝 Smart PRD Generation**: Transform your ideas into comprehensive Product Requirements Documents with AI-powered insights
- **🎯 Intelligent Ticket System**: Automatically break down complex features into actionable, prioritized tickets
- **💡 Real-time Code Generation**: Watch your ideas come to life with AI writing production-ready code
- **🔧 Built-in Development Environment**: Professional IDE with AI assistance and real-time collaboration
- **🌐 Full-Stack Development**: Build complete applications from frontend to backend with AI guidance
- **🚀 Automated Testing**: Generate comprehensive test suites to ensure code quality
- **📊 Progress Tracking**: Real-time visibility into development progress and AI agent activities

### 🎨 Customization & Flexibility

- **Choose Your AI**: Support for OpenAI GPT-4 and Anthropic Claude models
- **Tech Stack Freedom**: Use any programming language or framework
- **Deployment Options**: Deploy anywhere - cloud, on-premise, or hybrid
- **Custom Workflows**: Adapt the platform to your team's processes
- **API Integration**: Connect with your existing tools and services 

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

- **AI Prompts & Tools**: Located in `coding/utils/` - contains all the AI prompts, agent definitions, and utility functions that power the intelligent features
- **Agent System**: Specialized AI agents (Product Manager, Developer, Designer) with their respective prompts and behaviors
- **Code Execution**: Sandboxed environments using Docker and Kubernetes for secure code execution

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
  
**🚀 Ready to ship 10x faster?**

[Get Started](https://github.com/lfg-hq/lfg) • [Documentation](docs/) • [Report Issue](https://github.com/lfg-hq/lfg/issues)

**LFG - Let's F***ing Go! 🚀**

*Forever open source. Built with ❤️ by the community.*

</div> 