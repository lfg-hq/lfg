import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

CSRF_TRUSTED_ORIGINS = [
    'https://lfg.run',
    'https://www.lfg.run', 
    'http://localhost:8000',
    'http://localhost:3000',
]
ALLOWED_HOSTS = [
    'lfg.run',
    'www.lfg.run',
    'localhost',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'django_q',
    'chat',
    'accounts',
    'marketing',
    'projects',
    'subscriptions',
    'coding',
    'tasks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'LFG.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'subscriptions.context_processors.user_credits',
            ],
        },
    },
]

WSGI_APPLICATION = 'LFG.wsgi.application'
ASGI_APPLICATION = 'LFG.asgi.application'

# Channel layers configuration
# Set USE_REDIS_CHANNELS=True in environment to use Redis, otherwise uses InMemory
USE_REDIS_CHANNELS = os.environ.get('USE_REDIS_CHANNELS', 'False').lower() == 'true'

if USE_REDIS_CHANNELS:
    # Redis Channel Layer - Recommended for production
    redis_host = os.environ.get('REDIS_HOST', 'localhost')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    redis_db = int(os.environ.get('REDIS_DB', 0))
    redis_password = os.environ.get('REDIS_PASSWORD', '')
    
    # Build the connection URL based on available credentials
    if redis_password:
        # Production configuration with password and DB
        redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
    else:
        # Local development without password
        redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [redis_url],
                "capacity": 1000,  # Number of messages to store per channel
                "expiry": 60,      # Seconds until a message expires
                "group_expiry": 86400,  # Seconds until a group expires (24 hours)
                "channel_capacity": {
                    # Specific capacity limits per channel pattern
                    "chat_*": 100,  # Limit chat channels to 100 messages
                },
                "symmetric_encryption_keys": [os.environ.get('CHANNEL_ENCRYPTION_KEY', '')],
            },
        },
    }
else:
    # InMemory Channel Layer - For development
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
            # IMPORTANT: The in-memory channel layer has limitations:
            # - Messages are limited in size (default ~100KB)
            # - No persistence across restarts
            # - No support for multiple server instances
        },
    }

# Database configuration
# Set USE_POSTGRES_DB=True in environment to use PostgreSQL, otherwise uses SQLite
USE_POSTGRES_DB = os.environ.get('USE_POSTGRES_DB', 'False').lower() == 'true'

if USE_POSTGRES_DB:
    # PostgreSQL for production/staging
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'lfg_prod'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    # SQLite for local development
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Use SQLite for testing
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",  # Your JS files location
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (User uploaded content)
# MEDIA_URL = '/media/'
# MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# # File storage for chat attachments
# FILE_STORAGE_PATH = os.path.join(MEDIA_ROOT, 'file_storage')
# os.makedirs(FILE_STORAGE_PATH, exist_ok=True)

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True

# Security settings
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow pages to be displayed in frames on the same origin

# AI Provider Selection Feature
# AI_PROVIDER_DEFAULT = 'openai'  # Default provider 
AI_PROVIDER_DEFAULT = 'anthropic'  # Alternate provider 

# Kubernetes SSH server settings
# K8S_SSH_HOST = os.environ.get('K8S_SSH_HOST', '127.0.0.1')
# K8S_SSH_PORT = int(os.environ.get('K8S_SSH_PORT', 22))
# K8S_SSH_USERNAME = os.environ.get('K8S_SSH_USERNAME', 'root')
# K8S_SSH_KEY_FILE = os.environ.get('K8S_SSH_KEY_FILE', os.path.expanduser('~/.ssh/id_rsa'))
# K8S_SSH_KEY_STRING = os.environ.get('K8S_SSH_KEY_STRING', None)  # SSH private key as a string
# K8S_SSH_KEY_PASSPHRASE = os.environ.get('K8S_SSH_KEY_PASSPHRASE', None)

# Authentication URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/chat/'  # Redirect to chat page after successful login
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Authentication backends
# AUTHENTICATION_BACKENDS = [
#     'accounts.backends.EmailBackend',  # Custom email backend
#     'django.contrib.auth.backends.ModelBackend',  # Default Django backend
# ]

# Email Configuration
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For development - outputs to console
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # For production
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@lfg.run')

# GitHub OAuth Settings
# You should set these in environment variables or .env file
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET', '') 

# Kubernetes API Configuration
K8S_API_HOST = os.getenv('K8S_CLUSTER_HOST', "https://178.156.148.88:6443")
K8S_NODE_SSH_HOST = os.getenv('K8S_NODE_SSH_HOST', "178.156.138.23")
K8S_API_TOKEN = os.getenv('K8S_PERMANENT_TOKEN', "")
K8S_CA_CERT = os.getenv('K8S_CA_CERTIFICATE', "")
K8S_VERIFY_SSL = False  # Disabled by default since CA cert verification is problematic
K8S_DEFAULT_NAMESPACE = "lfg"
SSH_USERNAME=os.getenv('SSH_USERNAME', 'root')
SSH_KEY_STRING=os.getenv('SSH_KEY_STRING', None)

ENVIRONMENT = os.getenv('environment', 'local')

Q_CLUSTER = {
        'name': 'LFG_Tasks',
        'workers': 1,  # Reduced to single worker to prevent timer conflicts
        'recycle': 100,  # Reduced recycle count
        'timeout': 30,   # Reduced timeout
        'retry': 60,     # Reduced retry time
        'queue_limit': 10,  # Reduced queue limit
        'bulk': 1,       # Single task processing
        'orm': 'default',
        'guard_cycle': 10,  # Longer guard cycle
        'daemonize_workers': False,  # Disable daemon mode
        'max_attempts': 1,
        'sync': False,   # Keep async for production
        'redis': {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': int(os.getenv('REDIS_DB', 0)),
            'password': os.getenv('REDIS_PASSWORD', None),
        }
    }

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[{levelname}] {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'channels': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'chat': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'coding': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'coding.utils': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'coding.utils.ai_providers': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'coding.utils.ai_functions': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}