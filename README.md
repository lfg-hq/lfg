# LFG 🚀 | AI-Powered Product Development Platform

> **Build Products with AI Agents** - The ultimate open-source platform that combines Product Managers, Developers, and Designers in one intelligent workspace.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.0+-green.svg)](https://djangoproject.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-❤️-red.svg)](https://github.com/yourusername/lfg)

## 🌟 Overview

LFG is an open-source AI-powered product development platform that revolutionizes how teams build software. From ideation to deployment, our specialized AI agents handle every aspect of product development, enabling you to ship faster than ever before.

### ✨ Key Highlights

- 🤖 **6 Specialized AI Agents** working as your virtual team
- 📝 **Smart PRD Generation** with AI-powered requirements
- 🎯 **Intelligent Ticket Creation** with automated task breakdown
- 💻 **Built-in Code Editor** with AI assistance
- 🌐 **Full-Stack Web Apps** from frontend to backend
- 🐛 **Automated Bug Fixing** with intelligent detection
- 🚀 **One-Click Deployment** to multiple platforms
- 🎨 **Fully Customizable** - choose your AI models, tech stack, and deployment options

## 🤖 Meet Your AI Team

### Currently Available
- **👔 Product Manager** - Strategy & Planning
  - Defines product vision and creates roadmaps
  - Writes comprehensive PRDs
  - Manages feature prioritization with market insights

- **💻 Full-Stack Developer** - Implementation & Architecture
  - Builds robust applications and implements features
  - Optimizes performance and ensures code quality
  - Handles both frontend and backend development

- **🎨 UI/UX Designer** - Design & Experience
  - Creates beautiful interfaces and user experiences
  - Ensures accessibility and usability standards
  - Designs with modern best practices

### Coming Soon
- **🛡️ QA Engineer** - Quality & Testing *(Coming Soon)*
- **☁️ DevOps Engineer** - Deployment & Infrastructure *(Coming Soon)*
- **📊 Data Analyst** - Insights & Analytics *(Coming Soon)*

## 🚀 Features

### Core Capabilities
- **Smart PRD Generation**: AI-powered Product Requirements Documents that capture your vision and translate it into actionable development tasks
- **Intelligent Ticket Creation**: Automatically break down complex features into manageable tickets with proper prioritization
- **Built-in Code Editor**: Professional-grade editor with AI assistance, syntax highlighting, and real-time collaboration
- **Full-Stack Development**: Build complete web applications with AI guidance and best practices
- **Automated Bug Fixing**: Intelligent detection and resolution with suggested fixes and automated testing
- **One-Click Deployment**: Deploy instantly with multiple hosting options and automated CI/CD pipelines

### Customization Options

#### 🧠 AI Models
- OpenAI GPT-4 & GPT-3.5
- Anthropic Claude
- Google Gemini
- Local LLMs (Ollama)
- Custom fine-tuned models

#### 🛠️ Tech Stacks
- **Frontend**: React, Vue, Angular
- **Backend**: Node.js, Python, Go
- **Databases**: PostgreSQL, MongoDB
- **Infrastructure**: Docker, Kubernetes
- **Custom frameworks** supported

#### 🌐 Deployment Options
- **Cloud Providers**: AWS, Google Cloud, Azure
- **Platform Services**: Vercel, Netlify, Railway
- **Self-hosted solutions**
- **On-premise deployment**
- **Hybrid cloud setups**

#### 🔌 Integrations
- **Version Control**: GitHub, GitLab, Bitbucket
- **Project Management**: Jira, Linear, Notion
- **Communication**: Slack, Discord, Teams
- **Design Tools**: Figma, Adobe XD
- **Custom APIs & webhooks**

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Node.js 16+
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
   python manage.py runserver
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
│   └── k8s_manager/   # Kubernetes pod management
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

## 🔧 Configuration

### Environment Variables

Create a `.env` file or configure `env.sh` with the following variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lfg

# AI Models
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_AI_API_KEY=your_google_key

# Cloud Providers (optional)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
GOOGLE_CLOUD_PROJECT=your_gcp_project

# Integrations (optional)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_secret
SLACK_BOT_TOKEN=your_slack_token
```

## 🚀 Deployment

### Production Deployment

1. **Using Docker**
   ```bash
   docker build -t lfg-platform .
   docker run -p 8000:8000 lfg-platform
   ```

2. **Using Kubernetes**
   ```bash
   kubectl apply -f k8s/
   ```

3. **Cloud Platforms**
   - Deploy to AWS, Google Cloud, or Azure
   - Use platform-specific deployment guides in `/docs`

### Environment-Specific Configurations

- **Development**: Use `env.sh` for local development
- **Production**: Use `env.prod.sh` for production settings
- **Kubernetes**: See [README-K8S.md](README-K8S.md) for detailed K8s setup

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

### Areas We Need Help
- 🧪 **QA Engineer Agent** - Automated testing capabilities
- ☁️ **DevOps Agent** - Infrastructure and deployment automation
- 📊 **Data Analytics Agent** - User behavior analysis and insights
- 🌐 **Additional Integrations** - More third-party service connections
- 🎨 **UI/UX Improvements** - Enhanced user interface and experience

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

**Trademark Notice**: "LFG" and related trademarks are property of LFG Technologies. The MIT license does not grant trademark rights.

## 🙏 Acknowledgments

- Built with ❤️ by the open-source community
- Powered by cutting-edge AI models from OpenAI, Anthropic, and Google
- Special thanks to all our contributors and supporters

---

**Ready to build the future?** [Get started now](https://github.com/yourusername/lfg) and join thousands of developers shipping faster with AI-powered development! 🚀 

## ☸️ Kubernetes Integration

LFG provides powerful Kubernetes integration for creating isolated development environments and managing remote code execution. This allows you to:

- **Create isolated pods** for each project or development session
- **Execute code remotely** in secure, containerized environments
- **Persist environment configurations** in the database
- **Scale development environments** dynamically
- **Manage multiple clusters** from a single interface

### Prerequisites

- Kubernetes cluster (local or cloud-based)
- `kubectl` configured and authenticated
- Cluster admin permissions (for initial setup)
- Python Kubernetes client library

### Linking Your Kubernetes Cluster

#### 1. **Install Kubernetes Dependencies**

```bash
pip install kubernetes
# or if using requirements.txt, it should already be included
```

#### 2. **Configure Cluster Access**

**Option A: Using kubeconfig file**
```bash
# Ensure your kubeconfig is properly configured
kubectl config current-context
kubectl cluster-info

# LFG will automatically use your default kubeconfig
export KUBECONFIG=~/.kube/config
```

**Option B: Using Service Account (Recommended for Production)**
```bash
# Create a service account for LFG
kubectl create serviceaccount lfg-service-account

# Create cluster role binding
kubectl create clusterrolebinding lfg-cluster-admin \
  --clusterrole=cluster-admin \
  --serviceaccount=default:lfg-service-account

# Get the service account token
kubectl get secret $(kubectl get serviceaccount lfg-service-account -o jsonpath='{.secrets[0].name}') -o jsonpath='{.data.token}' | base64 --decode
```

#### 3. **Environment Configuration**

Add these variables to your `env.sh` or `.env` file:

```bash
# Kubernetes Configuration
KUBERNETES_ENABLED=true
KUBERNETES_NAMESPACE=lfg-development
KUBERNETES_SERVICE_ACCOUNT=lfg-service-account

# Cluster Configuration
KUBERNETES_CLUSTER_NAME=your-cluster-name
KUBERNETES_SERVER_URL=https://your-cluster-api-server
KUBERNETES_TOKEN=your-service-account-token

# Optional: Custom resource limits
KUBERNETES_DEFAULT_CPU_LIMIT=1000m
KUBERNETES_DEFAULT_MEMORY_LIMIT=2Gi
KUBERNETES_DEFAULT_STORAGE_LIMIT=10Gi

# Pod Configuration
KUBERNETES_DEFAULT_IMAGE=python:3.9-slim
KUBERNETES_PULL_POLICY=IfNotPresent
KUBERNETES_RESTART_POLICY=Never
```

#### 4. **Initialize Kubernetes Resources**

```bash
# Create namespace for LFG pods
kubectl create namespace lfg-development

# Apply RBAC configurations
kubectl apply -f config/k8s/rbac.yaml

# Set up persistent volume claims (optional)
kubectl apply -f config/k8s/storage.yaml
```

### Cluster Management Features

#### **Pod Lifecycle Management**

LFG automatically manages the complete lifecycle of development pods:

```python
# Example: Creating a development pod
from coding.k8s_manager import KubernetesManager

k8s = KubernetesManager()

# Create a new development environment
pod_config = {
    'project_id': 'my-project',
    'user_id': 'user123',
    'image': 'python:3.9-slim',
    'resources': {
        'cpu': '500m',
        'memory': '1Gi'
    }
}

pod = k8s.create_development_pod(pod_config)
```

#### **Supported Pod Types**

- **Development Pods**: Interactive coding environments
- **Build Pods**: For CI/CD and automated builds
- **Testing Pods**: Isolated testing environments
- **Deployment Pods**: For application deployment

#### **Resource Management**

```yaml
# Example pod resource configuration
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "2Gi"
    ephemeral-storage: "10Gi"
```

### Multi-Cluster Support

LFG supports connecting multiple Kubernetes clusters for different environments:

#### **Configuration for Multiple Clusters**

```bash
# Primary development cluster
KUBERNETES_DEV_CLUSTER_NAME=dev-cluster
KUBERNETES_DEV_SERVER_URL=https://dev-cluster-api
KUBERNETES_DEV_TOKEN=dev-cluster-token

# Production cluster
KUBERNETES_PROD_CLUSTER_NAME=prod-cluster
KUBERNETES_PROD_SERVER_URL=https://prod-cluster-api
KUBERNETES_PROD_TOKEN=prod-cluster-token

# Staging cluster
KUBERNETES_STAGING_CLUSTER_NAME=staging-cluster
KUBERNETES_STAGING_SERVER_URL=https://staging-cluster-api
KUBERNETES_STAGING_TOKEN=staging-cluster-token
```

#### **Cluster Selection**

Users can select which cluster to use for their development environment:

- **Development**: For active coding and testing
- **Staging**: For pre-production testing
- **Production**: For deployment and monitoring

### Security & Best Practices

#### **Network Policies**

```yaml
# Example network policy for LFG pods
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: lfg-pod-policy
  namespace: lfg-development
spec:
  podSelector:
    matchLabels:
      app: lfg-development-pod
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: lfg-development
  egress:
  - to: []
```

#### **Security Recommendations**

- **Use dedicated namespaces** for LFG pods
- **Implement resource quotas** to prevent resource exhaustion
- **Configure network policies** to isolate pod traffic
- **Use service accounts** with minimal required permissions
- **Enable pod security policies** or pod security standards
- **Regular cleanup** of unused pods and resources

### Monitoring & Troubleshooting

#### **Pod Status Monitoring**

```bash
# Check LFG pod status
kubectl get pods -n lfg-development -l app=lfg-development-pod

# View pod logs
kubectl logs -n lfg-development <pod-name>

# Describe pod for detailed information
kubectl describe pod -n lfg-development <pod-name>
```

#### **Common Issues & Solutions**

**Issue: Pod creation fails**
```bash
# Check cluster resources
kubectl top nodes
kubectl describe node <node-name>

# Check namespace quotas
kubectl describe quota -n lfg-development
```

**Issue: Pod networking problems**
```bash
# Test pod connectivity
kubectl exec -n lfg-development <pod-name> -- ping google.com

# Check service endpoints
kubectl get endpoints -n lfg-development
```

**Issue: Storage mounting fails**
```bash
# Check persistent volumes
kubectl get pv
kubectl get pvc -n lfg-development

# Verify storage class
kubectl get storageclass
```

### Advanced Configuration

#### **Custom Pod Templates**

Create custom pod templates for specific use cases:

```yaml
# config/k8s/templates/python-dev-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: lfg-python-dev-{user_id}-{project_id}
  namespace: lfg-development
  labels:
    app: lfg-development-pod
    user: "{user_id}"
    project: "{project_id}"
    type: python-development
spec:
  containers:
  - name: python-dev
    image: python:3.9-slim
    resources:
      requests:
        cpu: "250m"
        memory: "512Mi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
    volumeMounts:
    - name: workspace
      mountPath: /workspace
    - name: cache
      mountPath: /root/.cache
  volumes:
  - name: workspace
    emptyDir: {}
  - name: cache
    emptyDir: {}
  restartPolicy: Never
```

#### **Integration with CI/CD**

```bash
# Environment variables for CI/CD integration
KUBERNETES_CI_NAMESPACE=lfg-ci
KUBERNETES_CI_SERVICE_ACCOUNT=lfg-ci-runner
KUBERNETES_BUILD_TIMEOUT=3600  # 1 hour
KUBERNETES_CLEANUP_POLICY=always
```

For detailed Kubernetes setup and advanced configurations, see our [Kubernetes Documentation](README-K8S.md). 