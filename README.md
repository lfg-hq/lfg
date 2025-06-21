# LFG 🚀 | Agentic framework for AI dev team.

> **Build Products with AI Agents** - The ultimate open-source platform that combines Product Managers, Developers, and Designers in one intelligent workspace.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.0+-green.svg)](https://djangoproject.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red.svg)](https://github.com/yourusername/lfg)

> ⚠️ **Work in Progress**: LFG is currently under active development. Features and APIs may change as we continue to improve the platform. We welcome feedback and contributions!

## 🌟 Overview

LFG is an open-source AI-powered product development platform that helps you build software. The goal is to help you at every stage of product development, from ideation to deployment, and fixing bugs. (Still a work in progress)



### ✨ Key Highlights

- 🤖 **Specialized AI Agents** working as your virtual team (product manager, developer, designer)
- 📝 **Smart PRD Generation** with AI-powered requirements
- 🎯 **Intelligent Ticket Creation** with automated task breakdown
- 💻 **Built-in Code Editor** (Only when configured with Kubernetes)
- 🌐 **Full-Stack Web Apps** from frontend to backend

#### Coming Soon

- 🐛 **Automated Bug Fixing** with intelligent detection
- 🚀 **One-Click Deployment** to multiple platforms
- 🎨 **Fully Customizable** - choose your AI models, tech stack, and deployment options

## 🚀 Features

### Core Capabilities
- **Smart PRD Generation**: AI-powered Product Requirements Documents that capture your vision and translate it into actionable development tasks
- **Intelligent Ticket Creation**: Automatically break down complex features into manageable tickets with proper prioritization
- **Built-in Code Editor**: Professional-grade editor with AI assistance, syntax highlighting, and real-time collaboration
- **Full-Stack Development**: Build complete web applications with AI guidance and best practices

Coming soon:
- **Automated Bug Fixing**: Intelligent detection and resolution with suggested fixes and automated testing
- **One-Click Deployment**: Deploy instantly with multiple hosting options and automated CI/CD pipelines

### Customization Options

#### 🧠 AI Models
- OpenAI
- Anthropic Claude

#### 🔌 Integrations
- **Version Control**: GitHub
- **Project Management**: 
- **Communication**: 
- **Design Tools**: 

## 🛠️ Installation

### Prerequisites
- Python 3.11+
- Redis
- Docker (optional, for containerized development)
- Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/lfg.git
   cd lfg
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp env.sh.example env.sh
   # Edit env.sh with your configuration
   source env.sh
   ```

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the development server**
   ```bash
   uvicorn LFG.asgi:application --host 0.0.0.0 --port 8000 --workers 2
   ```

8. **Access the platform**
   Open your browser and navigate to `http://localhost:8000`

### Docker Setup (Alternative)

```bash
# Build and run with Docker Compose
docker-compose up --build

# Access at http://localhost:8000
```

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

## 📚 Documentation

- [Quick Start Guide](docs/quickstart.md)
- [API Documentation](docs/api.md)
- [Kubernetes Setup](README-K8S.md)
- [Deployment Guide](docs/deployment.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Architecture Overview](docs/architecture.md)

## 🆘 Support

- **Documentation**: Check our [docs](docs/) directory
- **Issues**: Report bugs on [GitHub Issues](https://github.com/yourusername/lfg/issues)
- **Discussions**: Join our [GitHub Discussions](https://github.com/yourusername/lfg/discussions)
- **Community**: Connect with us on [Discord](https://discord.gg/lfg)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Trademark Notice**: "LFG" and related trademarks are property of Microgigs Inc. The MIT license does not grant trademark rights.

---

**Ready to build the future?** [Get started now](https://github.com/yourusername/lfg) and join thousands of developers shipping faster with AI-powered development! 🚀 