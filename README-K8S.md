# Kubernetes Integration Guide

LFG provides powerful Kubernetes integration for creating isolated development environments and managing remote code execution. This allows you to:

- **Create isolated pods** for each project or development session
- **Execute code remotely** in secure, containerized environments
- **Persist environment configurations** in the database
- **Scale development environments** dynamically
- **Manage multiple clusters** from a single interface

## Prerequisites

- Kubernetes cluster (local or cloud-based)
- `kubectl` configured and authenticated
- Cluster admin permissions (for initial setup)
- Python Kubernetes client library

## Linking Your Kubernetes Cluster

### 1. **Install Kubernetes Dependencies**

```bash
pip install kubernetes
# or if using requirements.txt, it should already be included
```

### 2. **Configure Cluster Access**

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

### 3. **Environment Configuration**

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

### 4. **Initialize Kubernetes Resources**

```bash
# Create namespace for LFG pods
kubectl create namespace lfg-development

# Apply RBAC configurations
kubectl apply -f config/k8s/rbac.yaml

# Set up persistent volume claims (optional)
kubectl apply -f config/k8s/storage.yaml
```

## Cluster Management Features

### **Pod Lifecycle Management**

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

### **Supported Pod Types**

- **Development Pods**: Interactive coding environments
- **Build Pods**: For CI/CD and automated builds
- **Testing Pods**: Isolated testing environments
- **Deployment Pods**: For application deployment

### **Resource Management**

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

## Multi-Cluster Support

LFG supports connecting multiple Kubernetes clusters for different environments:

### **Configuration for Multiple Clusters**

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

### **Cluster Selection**

Users can select which cluster to use for their development environment:

- **Development**: For active coding and testing
- **Staging**: For pre-production testing
- **Production**: For deployment and monitoring

## Security & Best Practices

### **Network Policies**

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

### **Security Recommendations**

- **Use dedicated namespaces** for LFG pods
- **Implement resource quotas** to prevent resource exhaustion
- **Configure network policies** to isolate pod traffic
- **Use service accounts** with minimal required permissions
- **Enable pod security policies** or pod security standards
- **Regular cleanup** of unused pods and resources

## Monitoring & Troubleshooting

### **Pod Status Monitoring**

```bash
# Check LFG pod status
kubectl get pods -n lfg-development -l app=lfg-development-pod

# View pod logs
kubectl logs -n lfg-development <pod-name>

# Describe pod for detailed information
kubectl describe pod -n lfg-development <pod-name>
```

### **Common Issues & Solutions**

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

## Advanced Configuration

### **Custom Pod Templates**

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

### **Integration with CI/CD**

```bash
# Environment variables for CI/CD integration
KUBERNETES_CI_NAMESPACE=lfg-ci
KUBERNETES_CI_SERVICE_ACCOUNT=lfg-ci-runner
KUBERNETES_BUILD_TIMEOUT=3600  # 1 hour
KUBERNETES_CLEANUP_POLICY=always
```

---

For more information about LFG, see the main [README](README.md). 