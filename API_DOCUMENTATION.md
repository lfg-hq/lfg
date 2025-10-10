# LFG REST API Documentation

## Base URL
```
http://localhost:8000/api/v1/
```

## Authentication
All protected endpoints require JWT token in the Authorization header:
```
Authorization: Bearer <access_token>
```

## Endpoints

### Authentication

#### Register
```http
POST /api/v1/auth/register/
Content-Type: application/json

{
  "username": "user123",
  "email": "user@example.com",
  "password": "securepassword123",
  "password2": "securepassword123"
}

Response: 201 CREATED
{
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com",
    "first_name": "",
    "last_name": ""
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJh...",
    "access": "eyJ0eXAiOiJKV1QiLCJh..."
  },
  "message": "Registration successful"
}
```

#### Login
```http
POST /api/v1/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",  // or "username": "user123"
  "password": "securepassword123"
}

Response: 200 OK
{
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com"
  },
  "profile": {
    "user": {...},
    "avatar": null,
    "email_verified": false,
    "subscription_plan": null,
    "subscription_plan_name": "Free",
    "total_tokens_used": 0
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJh...",
    "access": "eyJ0eXAiOiJKV1QiLCJh..."
  },
  "message": "Login successful"
}
```

#### Logout
```http
POST /api/v1/auth/logout/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJh..."
}

Response: 200 OK
{
  "message": "Logout successful"
}
```

#### Refresh Token
```http
POST /api/v1/auth/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJh..."
}

Response: 200 OK
{
  "access": "eyJ0eXAiOiJKV1QiLCJh..."
}
```

#### Get Current User
```http
GET /api/v1/auth/user/
Authorization: Bearer <access_token>

Response: 200 OK
{
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com"
  },
  "profile": {
    "user": {...},
    "avatar": null,
    "subscription_plan_name": "Free",
    "total_tokens_used": 0
  }
}
```

### Profile

#### Get Profile
```http
GET /api/v1/profile/
Authorization: Bearer <access_token>

Response: 200 OK
{
  "user": {...},
  "avatar": null,
  "email_verified": false,
  "subscription_plan": null,
  "subscription_plan_name": "Free",
  "total_tokens_used": 0
}
```

#### Update Profile
```http
PATCH /api/v1/profile/<id>/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "avatar": "path/to/avatar.jpg"
}

Response: 200 OK
{
  "user": {...},
  "avatar": "path/to/avatar.jpg",
  ...
}
```

### API Keys

#### Get API Keys
```http
GET /api/v1/api-keys/
Authorization: Bearer <access_token>

Response: 200 OK
{
  "openai_api_key_masked": "sk-A...xyz",
  "anthropic_api_key_masked": "sk-a...123",
  "xai_api_key_masked": null,
  "google_api_key_masked": null
}
```

#### Update API Keys
```http
POST /api/v1/api-keys/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "openai_api_key": "sk-ABCdefghijklmnopqrstuvwxyz123456",
  "anthropic_api_key": "sk-ant-api03-abc123..."
}

Response: 200 OK
{
  "message": "API keys updated successfully",
  "data": {
    "openai_api_key_masked": "sk-A...456",
    "anthropic_api_key_masked": "sk-a...123",
    ...
  }
}
```

### Subscription

#### Get Subscription Info
```http
GET /api/v1/subscription/
Authorization: Bearer <access_token>

Response: 200 OK
{
  "subscription_plan": "Free",
  "total_tokens_used": 12500,
  "credits": {
    "balance": 87500,
    "lifetime_tokens": 100000,
    "monthly_tokens": 0
  }
}
```

### Conversations

#### List Conversations
```http
GET /api/v1/conversations/
Authorization: Bearer <access_token>

Response: 200 OK
[
  {
    "id": 1,
    "title": "My first conversation",
    "created_at": "2025-10-05T10:00:00Z",
    "updated_at": "2025-10-05T11:30:00Z",
    "message_count": 10
  },
  ...
]
```

#### Create Conversation
```http
POST /api/v1/conversations/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "New conversation"
}

Response: 201 CREATED
{
  "id": 2,
  "title": "New conversation",
  "created_at": "2025-10-05T12:00:00Z",
  "updated_at": "2025-10-05T12:00:00Z",
  "message_count": 0
}
```

#### Get Conversation Messages
```http
GET /api/v1/conversations/<id>/messages/
Authorization: Bearer <access_token>

Response: 200 OK
[
  {
    "id": 1,
    "conversation": 1,
    "role": "user",
    "content": "Hello!",
    "timestamp": "2025-10-05T10:00:00Z",
    "token_count": 5
  },
  {
    "id": 2,
    "conversation": 1,
    "role": "assistant",
    "content": "Hi there! How can I help you?",
    "timestamp": "2025-10-05T10:00:05Z",
    "token_count": 12
  }
]
```

### Messages

#### Create Message
```http
POST /api/v1/messages/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "conversation": 1,
  "role": "user",
  "content": "What is React?"
}

Response: 201 CREATED
{
  "id": 3,
  "conversation": 1,
  "role": "user",
  "content": "What is React?",
  "timestamp": "2025-10-05T12:05:00Z",
  "token_count": 8
}
```

## Running Migrations

Before using the API, run:

```bash
python manage.py migrate
python manage.py createsuperuser  # Optional: create admin user
```

## Testing the API

You can test using curl:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass123","password2":"testpass123"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'

# Get user info (use access token from login)
curl -X GET http://localhost:8000/api/v1/auth/user/ \
  -H "Authorization: Bearer <access_token>"
```

## Error Responses

### 400 Bad Request
```json
{
  "field_name": ["Error message"]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```
