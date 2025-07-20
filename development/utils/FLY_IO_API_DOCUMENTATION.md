# Fly.io Machines API Documentation

This document provides comprehensive documentation for the Fly.io Machines API endpoints used to launch and manage micro-VMs.

## Overview

Fly Machines are fast-launching VMs that can boot in approximately 300ms. They are hardware-virtualized containers running on Fly.io's infrastructure that can run for a single HTTP request or for weeks of uptime.

## Authentication

All API requests require authentication using a Fly.io API token:

```bash
# Get your API token
fly auth token
```

Include the token in all requests:
```
Authorization: Bearer YOUR_FLY_API_TOKEN
```

## Base URLs

- **Public API**: `https://api.machines.dev/v1`
- **Internal API** (from within Fly network): `http://_api.internal:4280/v1`

## API Endpoints

### 1. App Management

#### Create App
```http
POST /v1/apps
Content-Type: application/json

{
  "app_name": "my-app",
  "org_slug": "personal"  // optional
}
```

#### Get App
```http
GET /v1/apps/{app_name}
```

#### Delete App
```http
DELETE /v1/apps/{app_name}
```

### 2. Machine Management

#### Create Machine
```http
POST /v1/apps/{app_name}/machines
Content-Type: application/json

{
  "name": "web-1",  // optional
  "region": "iad",  // optional, defaults to nearest
  "config": {
    "image": "registry-1.docker.io/library/nginx:latest",
    "guest": {
      "cpus": 1,      // shared CPUs: 1, 2, 4, 6, 8
      "memory_mb": 256  // 256, 512, 1024, 2048, 4096, 8192
    },
    "env": {
      "KEY": "value"
    },
    "init": {
      "cmd": ["npm", "start"],        // optional
      "entrypoint": ["/usr/bin/node"]  // optional
    },
    "services": [{
      "ports": [{
        "port": 443,
        "handlers": ["http", "tls"]
      }, {
        "port": 80,
        "handlers": ["http"]
      }],
      "protocol": "tcp",
      "internal_port": 8080
    }],
    "mounts": [{
      "volume": "data",
      "path": "/data"
    }],
    "restart": {
      "policy": "on-failure"  // "no", "on-failure", "always"
    },
    "auto_destroy": false
  },
  "skip_launch": false  // Create without starting
}
```

#### List Machines
```http
GET /v1/apps/{app_name}/machines
```

#### Get Machine
```http
GET /v1/apps/{app_name}/machines/{machine_id}
```

#### Update Machine
```http
POST /v1/apps/{app_name}/machines/{machine_id}
Content-Type: application/json

{
  "config": {
    // Same structure as create
  }
}
```

#### Start Machine
```http
POST /v1/apps/{app_name}/machines/{machine_id}/start
```

#### Stop Machine
```http
POST /v1/apps/{app_name}/machines/{machine_id}/stop
Content-Type: application/json

{
  "timeout": 30  // seconds
}
```

#### Restart Machine
```http
POST /v1/apps/{app_name}/machines/{machine_id}/restart
Content-Type: application/json

{
  "timeout": 30  // seconds
}
```

#### Delete Machine
```http
DELETE /v1/apps/{app_name}/machines/{machine_id}?force=true
```

### 3. Volume Management

#### Create Volume
```http
POST /v1/apps/{app_name}/volumes
Content-Type: application/json

{
  "name": "data",
  "size_gb": 10,
  "region": "iad"
}
```

#### List Volumes
```http
GET /v1/apps/{app_name}/volumes
```

#### Get Volume
```http
GET /v1/apps/{app_name}/volumes/{volume_id}
```

#### Delete Volume
```http
DELETE /v1/apps/{app_name}/volumes/{volume_id}
```

## Machine States

Machines can be in the following states:
- `created` - Machine is created but not started
- `starting` - Machine is booting
- `started` - Machine is running
- `stopping` - Machine is shutting down
- `stopped` - Machine is stopped
- `destroying` - Machine is being deleted
- `destroyed` - Machine is deleted
- `error` - Machine encountered an error

## Region Codes

Common Fly.io regions:
- `iad` - Ashburn, Virginia (US East)
- `lax` - Los Angeles, California (US West)
- `sea` - Seattle, Washington (US West)
- `ord` - Chicago, Illinois (US Central)
- `lhr` - London, United Kingdom
- `ams` - Amsterdam, Netherlands
- `fra` - Frankfurt, Germany
- `sin` - Singapore
- `syd` - Sydney, Australia
- `nrt` - Tokyo, Japan

## Machine Sizing

### Shared CPU Options
| CPUs | Memory Options (MB) |
|------|-------------------|
| 1    | 256, 512, 1024, 2048 |
| 2    | 512, 1024, 2048, 4096 |
| 4    | 1024, 2048, 4096, 8192 |
| 6    | 2048, 4096, 8192 |
| 8    | 4096, 8192 |

### Performance CPU Options
For performance CPUs, prefix with "performance-":
- `performance-1x`, `performance-2x`, `performance-4x`, `performance-8x`, `performance-16x`

## Service Configuration

When exposing services to the internet:

```json
{
  "services": [{
    "ports": [{
      "port": 443,
      "handlers": ["http", "tls"],
      "http_options": {
        "compress": true
      },
      "tls_options": {
        "alpn": ["h2", "http/1.1"]
      }
    }],
    "protocol": "tcp",
    "internal_port": 8080,
    "concurrency": {
      "type": "connections",
      "hard_limit": 25,
      "soft_limit": 20
    }
  }]
}
```

## Example Usage with Python

```python
import requests

class FlyClient:
    def __init__(self, api_token):
        self.base_url = "https://api.machines.dev/v1"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def create_machine(self, app_name, image, region="iad"):
        data = {
            "config": {
                "image": image,
                "guest": {
                    "cpus": 1,
                    "memory_mb": 256
                }
            },
            "region": region
        }
        
        response = requests.post(
            f"{self.base_url}/apps/{app_name}/machines",
            headers=self.headers,
            json=data
        )
        return response.json()

# Usage
client = FlyClient("your-api-token")
machine = client.create_machine("my-app", "nginx:latest")
print(f"Created machine: {machine['id']}")
```

## Quick Start Examples

### 1. Deploy a Web App
```python
from fly_io_manager import FlyIOManager, MachineConfig

# Initialize
manager = FlyIOManager(api_token="your-token")

# Create app
app = manager.create_app("my-web-app")

# Deploy web server
web = manager.launch_web_app(
    app_name="my-web-app",
    image="my-docker-image:latest",
    port=3000,
    region="iad",
    cpus=1,
    memory_mb=512
)
```

### 2. Deploy a Background Worker
```python
# Deploy worker
worker_config = MachineConfig(
    image="my-worker:latest",
    name="background-worker",
    cpus=2,
    memory_mb=1024,
    cmd=["python", "worker.py"],
    env={"QUEUE_URL": "redis://..."},
    restart_policy="always"
)

worker = manager.create_machine("my-web-app", worker_config)
```

### 3. Deploy with Persistent Storage
```python
# Create volume
volume = manager.create_volume(
    app_name="my-web-app",
    volume_name="data",
    size_gb=10,
    region="iad"
)

# Deploy with volume
config = MachineConfig(
    image="postgres:15",
    name="database",
    cpus=2,
    memory_mb=2048,
    mounts=[{
        "volume": "data",
        "path": "/var/lib/postgresql/data"
    }],
    env={"POSTGRES_PASSWORD": "secret"}
)

db = manager.create_machine("my-web-app", config)
```

## Best Practices

1. **Region Selection**: Choose regions close to your users for better latency
2. **Resource Sizing**: Start small and scale up based on monitoring
3. **Health Checks**: Configure health checks for automatic restarts
4. **Volumes**: Use volumes for persistent data that needs to survive machine restarts
5. **Secrets**: Use Fly secrets instead of hardcoding sensitive data in env vars
6. **Monitoring**: Use `fly logs` and `fly status` to monitor your machines

## Rate Limits

- API requests are rate-limited per account
- Typical limits: 100 requests per minute
- Machine creation may have additional limits

## Error Handling

Common error responses:
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (invalid token)
- `404` - Not Found (app/machine doesn't exist)
- `422` - Unprocessable Entity (validation errors)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

## Additional Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Machines API Reference](https://fly.io/docs/machines/api/)
- [Fly CLI Documentation](https://fly.io/docs/flyctl/)
- [Community Forum](https://community.fly.io/)