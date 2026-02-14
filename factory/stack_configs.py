"""
Stack Configuration Registry

Defines configuration for different technology stacks (Next.js, Python, Go, etc.)
Used by workspace setup, dev sandbox, and AI prompts to handle multi-stack projects.
"""

from typing import Dict, Any, Optional


STACK_CONFIGS: Dict[str, Dict[str, Any]] = {
    'nextjs': {
        'name': 'Next.js',
        'template_repo': 'lfg-hq/nextjs-template',
        'project_dir': 'project',
        'install_cmd': 'npm install',
        'dev_cmd': 'npm run dev',
        'build_cmd': 'npm run build',
        'default_port': 3000,
        'language': 'javascript',
        'package_manager': 'npm',
        'bootstrap_packages': [],  # Node.js is pre-installed in base workspace
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Configure npm to use /root for all storage
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache
echo 'export PATH=/root/.npm-global/bin:$PATH' >> ~/.bashrc
echo "VM ready for Next.js development"
''',
        'health_check': 'curl -sf http://localhost:3000 > /dev/null',
        'file_patterns': ['package.json', 'next.config.js', 'next.config.mjs', 'next.config.ts'],
        'env_file': '.env.local',
        'gitignore_extras': ['node_modules/', '.next/', '.env.local'],
        'pre_dev_cmd': 'export PATH=/root/.npm-global/bin:$PATH',
    },

    'python-django': {
        'name': 'Python (Django)',
        'template_repo': 'lfg-hq/django-template',
        'project_dir': 'django-app',
        'install_cmd': 'pip install -r requirements.txt',
        'dev_cmd': 'python manage.py runserver 0.0.0.0:8000',
        'build_cmd': 'python manage.py collectstatic --noinput',
        'default_port': 8000,
        'language': 'python',
        'package_manager': 'pip',
        'bootstrap_packages': ['python3', 'python3-pip', 'python3-venv'],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Create virtualenv in /root for persistence
python3 -m venv /root/venv || true
# Configure pip to cache in /root
mkdir -p /root/.pip-cache
echo 'export PIP_CACHE_DIR=/root/.pip-cache' >> ~/.bashrc
echo 'source /root/venv/bin/activate' >> ~/.bashrc
echo "VM ready for Django development"
''',
        'health_check': 'curl -sf http://localhost:8000 > /dev/null',
        'file_patterns': ['manage.py', 'requirements.txt', 'settings.py'],
        'env_file': '.env',
        'gitignore_extras': ['venv/', '*.pyc', '__pycache__/', '.env', 'db.sqlite3'],
        'pre_dev_cmd': 'source /root/venv/bin/activate && export PIP_CACHE_DIR=/root/.pip-cache',
    },

    'python-fastapi': {
        'name': 'Python (FastAPI)',
        'template_repo': 'lfg-hq/fastapi-template',
        'project_dir': 'fastapi-app',
        'install_cmd': 'pip install -r requirements.txt',
        'dev_cmd': 'uvicorn main:app --host 0.0.0.0 --port 8000 --reload',
        'build_cmd': '',  # No build step for FastAPI
        'default_port': 8000,
        'language': 'python',
        'package_manager': 'pip',
        'bootstrap_packages': ['python3', 'python3-pip', 'python3-venv'],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Create virtualenv in /root for persistence
python3 -m venv /root/venv || true
# Configure pip to cache in /root
mkdir -p /root/.pip-cache
echo 'export PIP_CACHE_DIR=/root/.pip-cache' >> ~/.bashrc
echo 'source /root/venv/bin/activate' >> ~/.bashrc
echo "VM ready for FastAPI development"
''',
        'health_check': 'curl -sf http://localhost:8000/health > /dev/null || curl -sf http://localhost:8000/docs > /dev/null',
        'file_patterns': ['main.py', 'requirements.txt', 'app.py'],
        'env_file': '.env',
        'gitignore_extras': ['venv/', '*.pyc', '__pycache__/', '.env'],
        'pre_dev_cmd': 'source /root/venv/bin/activate && export PIP_CACHE_DIR=/root/.pip-cache',
    },

    'go': {
        'name': 'Go',
        'template_repo': 'lfg-hq/go-template',
        'project_dir': 'go-app',
        'install_cmd': 'go mod download',
        'dev_cmd': 'go run .',
        'build_cmd': 'go build -o app .',
        'default_port': 8080,
        'language': 'go',
        'package_manager': 'go mod',
        'bootstrap_packages': [],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Install Go to /root if not present
mkdir -p /root/go-sdk /root/go
if [ ! -f /root/go-sdk/bin/go ]; then
    echo "Installing Go to /root/go-sdk..."
    wget -q https://go.dev/dl/go1.22.0.linux-amd64.tar.gz -O /tmp/go.tar.gz
    tar -C /root/go-sdk --strip-components=1 -xzf /tmp/go.tar.gz
    rm /tmp/go.tar.gz
fi
# Set Go environment to use /root
echo 'export GOROOT=/root/go-sdk' >> ~/.bashrc
echo 'export GOPATH=/root/go' >> ~/.bashrc
echo 'export GOCACHE=/root/.go-cache' >> ~/.bashrc
echo 'export PATH=/root/go-sdk/bin:/root/go/bin:$PATH' >> ~/.bashrc
mkdir -p /root/.go-cache
echo "VM ready for Go development"
''',
        'health_check': 'curl -sf http://localhost:8080 > /dev/null',
        'file_patterns': ['go.mod', 'go.sum', 'main.go'],
        'env_file': '.env',
        'gitignore_extras': ['app', '*.exe', '.env'],
        'pre_dev_cmd': 'export GOROOT=/root/go-sdk && export GOPATH=/root/go && export GOCACHE=/root/.go-cache && export PATH=/root/go-sdk/bin:/root/go/bin:$PATH',
    },

    'rust': {
        'name': 'Rust',
        'template_repo': 'lfg-hq/rust-template',
        'project_dir': 'rust-app',
        'install_cmd': 'cargo build',
        'dev_cmd': 'cargo run',
        'build_cmd': 'cargo build --release',
        'default_port': 8080,
        'language': 'rust',
        'package_manager': 'cargo',
        'bootstrap_packages': [],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Install Rust to /root
export RUSTUP_HOME=/root/.rustup
export CARGO_HOME=/root/.cargo
mkdir -p $RUSTUP_HOME $CARGO_HOME
if [ ! -f /root/.cargo/bin/rustc ]; then
    echo "Installing Rust to /root..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
fi
echo 'export RUSTUP_HOME=/root/.rustup' >> ~/.bashrc
echo 'export CARGO_HOME=/root/.cargo' >> ~/.bashrc
echo 'export PATH=/root/.cargo/bin:$PATH' >> ~/.bashrc
echo "VM ready for Rust development"
''',
        'health_check': 'curl -sf http://localhost:8080 > /dev/null',
        'file_patterns': ['Cargo.toml', 'Cargo.lock', 'src/main.rs'],
        'env_file': '.env',
        'gitignore_extras': ['target/', '.env'],
        'pre_dev_cmd': 'export RUSTUP_HOME=/root/.rustup && export CARGO_HOME=/root/.cargo && export PATH=/root/.cargo/bin:$PATH',
    },

    'ruby-rails': {
        'name': 'Ruby on Rails',
        'template_repo': 'lfg-hq/rails-template',
        'project_dir': 'rails-app',
        'install_cmd': 'bundle install --path /root/.bundle',
        'dev_cmd': 'rails server -b 0.0.0.0 -p 3000',
        'build_cmd': 'rails assets:precompile',
        'default_port': 3000,
        'language': 'ruby',
        'package_manager': 'bundler',
        'bootstrap_packages': ['ruby', 'ruby-dev', 'build-essential'],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Configure Ruby/Bundler to use /root
mkdir -p /root/.gem /root/.bundle
export GEM_HOME=/root/.gem
export GEM_PATH=/root/.gem
export BUNDLE_PATH=/root/.bundle
echo 'export GEM_HOME=/root/.gem' >> ~/.bashrc
echo 'export GEM_PATH=/root/.gem' >> ~/.bashrc
echo 'export BUNDLE_PATH=/root/.bundle' >> ~/.bashrc
echo 'export PATH=/root/.gem/bin:$PATH' >> ~/.bashrc
# Install bundler to /root
gem install bundler --install-dir /root/.gem || true
echo "VM ready for Rails development"
''',
        'health_check': 'curl -sf http://localhost:3000 > /dev/null',
        'file_patterns': ['Gemfile', 'Gemfile.lock', 'config/routes.rb'],
        'env_file': '.env',
        'gitignore_extras': ['vendor/bundle/', 'log/', 'tmp/', '.env'],
        'pre_dev_cmd': 'export GEM_HOME=/root/.gem && export GEM_PATH=/root/.gem && export BUNDLE_PATH=/root/.bundle && export PATH=/root/.gem/bin:$PATH',
    },

    'astro': {
        'name': 'Astro',
        'template_repo': 'lfg-hq/astro-template',
        'project_dir': 'project',
        'install_cmd': 'npm install',
        'dev_cmd': 'npx astro dev --host 0.0.0.0',
        'build_cmd': 'npx astro build',
        'default_port': 4321,
        'language': 'javascript',
        'package_manager': 'npm',
        'bootstrap_packages': [],  # Node.js is pre-installed in base workspace
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
# Configure npm to use /root for all storage
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache
echo 'export PATH=/root/.npm-global/bin:$PATH' >> ~/.bashrc
echo "VM ready for Astro development"
''',
        'health_check': 'curl -sf http://localhost:4321 > /dev/null',
        'file_patterns': ['astro.config.mjs', 'astro.config.js', 'astro.config.ts', 'package.json'],
        'env_file': '.env',
        'gitignore_extras': ['node_modules/', 'dist/', '.astro/', '.env'],
        'pre_dev_cmd': 'export PATH=/root/.npm-global/bin:$PATH',
    },

    'custom': {
        'name': 'Custom/Existing Repo',
        'template_repo': None,  # User provides their own repo
        'project_dir': 'app',
        'install_cmd': '',  # Will be detected or user-provided
        'dev_cmd': '',  # Will be detected or user-provided
        'build_cmd': '',
        'default_port': 3000,
        'language': 'unknown',
        'package_manager': 'unknown',
        'bootstrap_packages': [],
        'bootstrap_script': '''#!/bin/sh
set -eux
cd /root
echo "VM ready for custom project"
''',
        'health_check': '',
        'file_patterns': [],
        'env_file': '.env',
        'gitignore_extras': ['.env'],
        'pre_dev_cmd': '',
    },
}


def get_stack_config(stack: str, project=None) -> Dict[str, Any]:
    """
    Get configuration for a specific stack, with optional project-specific overrides.

    Args:
        stack: Stack identifier (e.g., 'nextjs', 'python-django', 'go')
        project: Optional Project model instance for custom overrides

    Returns:
        Stack configuration dictionary. Falls back to a minimal default if unknown.
        If project is provided, custom overrides from DB will be applied.
    """
    # Fall back to a minimal default instead of assuming Next.js
    fallback = {
        'name': stack,
        'template_repo': None,
        'project_dir': 'project',
        'install_cmd': '',
        'dev_cmd': '',
        'build_cmd': '',
        'default_port': 3000,
        'language': 'unknown',
        'package_manager': 'unknown',
        'bootstrap_packages': [],
        'bootstrap_script': '',
        'health_check': '',
        'file_patterns': [],
        'env_file': '.env',
        'gitignore_extras': ['.env'],
        'pre_dev_cmd': '',
    }
    config = STACK_CONFIGS.get(stack, fallback).copy()

    # Apply project-specific overrides from database
    if project:
        if project.custom_project_dir:
            config['project_dir'] = project.custom_project_dir
        if project.custom_install_cmd:
            config['install_cmd'] = project.custom_install_cmd
        if project.custom_dev_cmd:
            config['dev_cmd'] = project.custom_dev_cmd
        if project.custom_default_port:
            config['default_port'] = project.custom_default_port

    return config


def get_stack_choices() -> list:
    """Get list of (value, label) tuples for form choices."""
    return [(key, config['name']) for key, config in STACK_CONFIGS.items()]


def detect_stack_from_files(file_list: list) -> Optional[str]:
    """
    Auto-detect stack based on files present in a repository.

    Args:
        file_list: List of file paths in the repository

    Returns:
        Detected stack identifier or None if unknown
    """
    import logging
    logger = logging.getLogger(__name__)

    file_names = {f.split('/')[-1] for f in file_list}

    logger.info(f"[STACK DETECTION] Analyzing {len(file_list)} files")
    logger.info(f"[STACK DETECTION] Unique filenames: {sorted(file_names)[:50]}...")  # First 50

    # Check for key files
    has_go_mod = 'go.mod' in file_names
    has_package_json = 'package.json' in file_names
    has_next_config = 'next.config.js' in file_names or 'next.config.mjs' in file_names or 'next.config.ts' in file_names
    has_astro_config = 'astro.config.mjs' in file_names or 'astro.config.js' in file_names or 'astro.config.ts' in file_names
    has_cargo_toml = 'Cargo.toml' in file_names
    has_manage_py = 'manage.py' in file_names
    has_requirements = 'requirements.txt' in file_names

    logger.info(f"[STACK DETECTION] Key files - go.mod: {has_go_mod}, package.json: {has_package_json}, next.config.*: {has_next_config}, astro.config.*: {has_astro_config}, Cargo.toml: {has_cargo_toml}")

    # Check in order of specificity
    if has_astro_config:
        logger.info("[STACK DETECTION] Detected: astro (found astro.config.*)")
        return 'astro'
    if has_next_config:
        logger.info("[STACK DETECTION] Detected: nextjs (found next.config.*)")
        return 'nextjs'
    if has_manage_py and has_requirements:
        logger.info("[STACK DETECTION] Detected: python-django (found manage.py + requirements.txt)")
        return 'python-django'
    if has_go_mod:
        logger.info("[STACK DETECTION] Detected: go (found go.mod)")
        return 'go'
    if has_cargo_toml:
        logger.info("[STACK DETECTION] Detected: rust (found Cargo.toml)")
        return 'rust'
    if 'Gemfile' in file_names and 'config' in file_names:
        logger.info("[STACK DETECTION] Detected: ruby-rails (found Gemfile + config)")
        return 'ruby-rails'
    if has_requirements or 'pyproject.toml' in file_names:
        logger.info("[STACK DETECTION] Detected: python-fastapi (found requirements.txt or pyproject.toml)")
        return 'python-fastapi'
    if has_package_json:
        logger.info("[STACK DETECTION] Detected: nextjs (found package.json, defaulting to Next.js)")
        return 'nextjs'

    logger.info("[STACK DETECTION] No stack detected, returning None")
    return None


def get_dev_server_command(stack: str, project_dir: Optional[str] = None) -> str:
    """
    Get the full command to start the dev server for a stack.

    Args:
        stack: Stack identifier
        project_dir: Override project directory (uses config default if None)

    Returns:
        Shell command string to start the dev server
    """
    config = get_stack_config(stack)
    dir_name = project_dir or config['project_dir']
    pre_cmd = config.get('pre_dev_cmd', '')
    dev_cmd = config['dev_cmd']

    if not dev_cmd:
        return f"cd /root/{dir_name} && echo 'No dev command configured for this stack'"

    if pre_cmd:
        return f"cd /root/{dir_name} && {pre_cmd} && {dev_cmd}"
    return f"cd /root/{dir_name} && {dev_cmd}"


def get_install_command(stack: str, project_dir: Optional[str] = None) -> str:
    """
    Get the full command to install dependencies for a stack.

    Args:
        stack: Stack identifier
        project_dir: Override project directory (uses config default if None)

    Returns:
        Shell command string to install dependencies
    """
    config = get_stack_config(stack)
    dir_name = project_dir or config['project_dir']
    pre_cmd = config.get('pre_dev_cmd', '')
    install_cmd = config['install_cmd']

    if not install_cmd:
        return f"cd /root/{dir_name} && echo 'No install command configured for this stack'"

    if pre_cmd:
        return f"cd /root/{dir_name} && {pre_cmd} && {install_cmd}"
    return f"cd /root/{dir_name} && {install_cmd}"


def get_bootstrap_script(stack: str) -> str:
    """Get the bootstrap script for a stack."""
    config = get_stack_config(stack)
    return config.get('bootstrap_script', '')


def get_gitignore_content(stack: str) -> str:
    """
    Generate comprehensive .gitignore content for a given stack.

    Args:
        stack: Stack identifier (e.g., 'nextjs', 'python-django', 'go')

    Returns:
        Complete .gitignore file content as a string
    """
    config = get_stack_config(stack)
    stack_extras = config.get('gitignore_extras', [])

    # Common ignores for all projects
    common_ignores = [
        '# Dependencies',
        'node_modules/',
        '',
        '# Environment variables',
        '.env',
        '.env.local',
        '.env.*.local',
        '',
        '# IDE',
        '.idea/',
        '.vscode/',
        '*.swp',
        '*.swo',
        '*~',
        '',
        '# OS files',
        '.DS_Store',
        'Thumbs.db',
        '',
        '# Logs',
        '*.log',
        'logs/',
        '',
    ]

    # Stack-specific ignores
    stack_specific = {
        'nextjs': [
            '# Next.js',
            '.next/',
            'out/',
            'build/',
            '',
            '# Vercel',
            '.vercel',
            '',
        ],
        'python-django': [
            '# Python',
            '__pycache__/',
            '*.py[cod]',
            '*$py.class',
            '*.so',
            '',
            '# Virtual environment',
            'venv/',
            'env/',
            '.venv/',
            '',
            '# Django',
            'db.sqlite3',
            'staticfiles/',
            'media/',
            '',
        ],
        'python-fastapi': [
            '# Python',
            '__pycache__/',
            '*.py[cod]',
            '*$py.class',
            '*.so',
            '',
            '# Virtual environment',
            'venv/',
            'env/',
            '.venv/',
            '',
        ],
        'go': [
            '# Go',
            '*.exe',
            '*.exe~',
            '*.dll',
            '*.so',
            '*.dylib',
            '',
            '# Go build output',
            '/app',
            '/bin/',
            '',
            '# Go test',
            '*.test',
            '*.out',
            '',
        ],
        'rust': [
            '# Rust',
            '/target/',
            'Cargo.lock',
            '',
            '# Debug',
            'debug/',
            '*.pdb',
            '',
        ],
        'astro': [
            '# Astro',
            'dist/',
            '.astro/',
            '',
        ],
        'ruby-rails': [
            '# Ruby',
            '*.gem',
            '*.rbc',
            '',
            '# Rails',
            '/log/*',
            '/tmp/*',
            '/vendor/bundle/',
            '/public/assets/',
            '/public/packs/',
            '',
            '# Database',
            '/db/*.sqlite3',
            '/db/*.sqlite3-*',
            '',
        ],
    }

    # Build the gitignore content
    lines = ['# Auto-generated by LFG', '']
    lines.extend(common_ignores)

    # Add stack-specific ignores
    if stack in stack_specific:
        lines.extend(stack_specific[stack])

    # Add any extras from stack config that aren't already included
    if stack_extras:
        content = '\n'.join(lines)
        new_extras = [extra for extra in stack_extras if extra not in content]
        if new_extras:
            lines.append('# Additional stack-specific')
            lines.extend(new_extras)
            lines.append('')

    return '\n'.join(lines)
