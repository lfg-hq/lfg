"""
Frontend-specific indexing functionality for UI component mapping.

This module handles:
1. Detection of frontend frameworks (React, Vue, Angular, etc.)
2. Extraction of screens/pages and their routes
3. Mapping of UI components (buttons, forms, links, etc.)
4. Building navigation flow between screens
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


# Framework detection patterns
FRAMEWORK_PATTERNS = {
    'react': {
        'files': ['package.json'],
        'content_patterns': [r'"react":', r'"react-dom":'],
        'file_extensions': ['.jsx', '.tsx'],
        'component_patterns': [
            r'function\s+([A-Z][a-zA-Z0-9]*)\s*\(',
            r'const\s+([A-Z][a-zA-Z0-9]*)\s*=\s*\(?',
            r'class\s+([A-Z][a-zA-Z0-9]*)\s+extends\s+(React\.)?Component',
        ],
    },
    'nextjs': {
        'files': ['next.config.js', 'next.config.mjs', 'next.config.ts'],
        'content_patterns': [r'"next":', r'@next/'],
        'file_extensions': ['.jsx', '.tsx', '.js', '.ts'],
        'pages_dirs': ['pages', 'app', 'src/pages', 'src/app'],
    },
    'vue': {
        'files': ['package.json', 'vue.config.js'],
        'content_patterns': [r'"vue":', r'"@vue/'],
        'file_extensions': ['.vue'],
        'component_patterns': [
            r'export\s+default\s+defineComponent',
            r'<template>',
        ],
    },
    'angular': {
        'files': ['angular.json', 'angular-cli.json'],
        'content_patterns': [r'"@angular/core":', r'"@angular/common":'],
        'file_extensions': ['.ts', '.component.ts'],
        'component_patterns': [
            r'@Component\s*\(',
        ],
    },
    'svelte': {
        'files': ['svelte.config.js'],
        'content_patterns': [r'"svelte":', r'"@sveltejs/'],
        'file_extensions': ['.svelte'],
    },
    # Server-side template engines
    'go-templates': {
        'files': ['go.mod', 'main.go'],
        'content_patterns': [r'html/template', r'text/template'],
        'file_extensions': ['.html', '.tmpl', '.gohtml'],
        'template_dirs': ['templates', 'views', 'web/templates', 'internal/templates'],
    },
    'django': {
        'files': ['manage.py', 'settings.py'],
        'content_patterns': [r'django'],
        'file_extensions': ['.html'],
        'template_dirs': ['templates'],
    },
    'jinja': {
        'files': ['app.py', 'wsgi.py'],
        'content_patterns': [r'flask', r'jinja2'],
        'file_extensions': ['.html', '.jinja', '.jinja2'],
        'template_dirs': ['templates'],
    },
    'erb': {
        'files': ['Gemfile', 'config.ru'],
        'content_patterns': [r'rails', r'sinatra'],
        'file_extensions': ['.erb', '.html.erb'],
        'template_dirs': ['views', 'app/views'],
    },
}

# UI Component detection patterns - works for both JSX and HTML templates
COMPONENT_PATTERNS = {
    'button': [
        r'<button\b[^>]*>',
        r'<Button\b[^>]*>',
        r'<IconButton\b[^>]*',
        r'<Fab\b[^>]*',  # Material UI
        r'class="[^"]*btn[^"]*"',  # Bootstrap/Tailwind buttons
        r'type="submit"',
        r'type="button"',
    ],
    'link': [
        r'<a\b[^>]*href=["\']([^"\']*)["\']',
        r'<Link\b[^>]*to=["\']([^"\']*)["\']',
        r'<NavLink\b[^>]*to=["\']([^"\']*)["\']',
        r'<RouterLink\b[^>]*to=["\']([^"\']*)["\']',
    ],
    'input': [
        r'<input\b[^>]*',
        r'<Input\b[^>]*',
        r'<TextField\b[^>]*',
        r'<TextInput\b[^>]*',
        r'<textarea\b[^>]*',
    ],
    'form': [
        r'<form\b[^>]*',
        r'<Form\b[^>]*',
    ],
    'modal': [
        r'<Modal\b[^>]*',
        r'<Dialog\b[^>]*',
        r'<Drawer\b[^>]*',
        r'<Sheet\b[^>]*',
        r'class="[^"]*modal[^"]*"',
        r'id="[^"]*[Mm]odal[^"]*"',
        r'data-bs-toggle="modal"',
    ],
    'dropdown': [
        r'<select\b[^>]*',
        r'<Select\b[^>]*',
        r'<Dropdown\b[^>]*',
        r'<Menu\b[^>]*',
        r'<Popover\b[^>]*',
        r'class="[^"]*dropdown[^"]*"',
    ],
    'nav': [
        r'<nav\b[^>]*',
        r'<Nav\b[^>]*',
        r'<Navbar\b[^>]*',
        r'<Navigation\b[^>]*',
        r'<Sidebar\b[^>]*',
        r'class="[^"]*navbar[^"]*"',
        r'class="[^"]*sidebar[^"]*"',
        r'class="[^"]*nav\b[^"]*"',
    ],
    'card': [
        r'<Card\b[^>]*',
        r'<Paper\b[^>]*',  # Material UI
        r'class="[^"]*card[^"]*"',
    ],
    'list': [
        r'<ul\b[^>]*',
        r'<ol\b[^>]*',
        r'<List\b[^>]*',
        r'<ListView\b[^>]*',
    ],
    'table': [
        r'<table\b[^>]*',
        r'<Table\b[^>]*',
        r'<DataGrid\b[^>]*',
        r'<DataTable\b[^>]*',
    ],
    'tab': [
        r'<Tab\b[^>]*',
        r'<Tabs\b[^>]*',
        r'class="[^"]*tab[^"]*"',
        r'role="tab"',
    ],
    'icon': [
        r'<i\s+class="[^"]*fa[^"]*"',  # FontAwesome
        r'<svg\b[^>]*',
        r'<Icon\b[^>]*',
    ],
    'image': [
        r'<img\b[^>]*',
        r'<Image\b[^>]*',
        r'<picture\b[^>]*',
    ],
}

# Route extraction patterns
ROUTE_PATTERNS = {
    'react-router': [
        r'<Route\b[^>]*path=["\']([^"\']*)["\'][^>]*(?:element|component)=\{?\s*<?\s*([A-Za-z0-9_]+)',
        r'path:\s*["\']([^"\']+)["\'],\s*(?:element|component):\s*([A-Za-z0-9_]+)',
    ],
    'nextjs-pages': [
        # File-based routing - handled separately
    ],
    'vue-router': [
        r'path:\s*["\']([^"\']+)["\'],\s*component:\s*([A-Za-z0-9_]+)',
    ],
    'angular-router': [
        r'path:\s*["\']([^"\']+)["\'],\s*component:\s*([A-Za-z0-9_]+)',
    ],
}


class FrontendFrameworkDetector:
    """Detects frontend framework used in the repository"""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def detect_framework(self) -> Dict[str, Any]:
        """Detect the frontend framework used in the repository"""
        result = {
            'framework': None,
            'version': None,
            'ui_library': None,
            'confidence': 0,
        }

        # Check package.json for dependencies (JS frameworks)
        package_json = self._read_package_json()
        if package_json:
            dependencies = {
                **package_json.get('dependencies', {}),
                **package_json.get('devDependencies', {}),
            }

            # Check for frameworks
            for framework, config in FRAMEWORK_PATTERNS.items():
                for pattern in config.get('content_patterns', []):
                    for dep in dependencies.keys():
                        if re.search(pattern.replace('"', ''), f'"{dep}"'):
                            if not result['framework'] or framework in ['nextjs']:  # Prefer specific frameworks
                                result['framework'] = framework
                                result['version'] = dependencies.get(dep)
                                result['confidence'] = 90
                                break

            # Detect UI libraries
            ui_libraries = {
                '@mui/material': 'Material UI',
                '@material-ui/core': 'Material UI',
                'antd': 'Ant Design',
                '@chakra-ui/react': 'Chakra UI',
                'tailwindcss': 'Tailwind CSS',
                'bootstrap': 'Bootstrap',
                'react-bootstrap': 'React Bootstrap',
                '@headlessui/react': 'Headless UI',
                'shadcn': 'shadcn/ui',
            }

            for lib, name in ui_libraries.items():
                if lib in dependencies:
                    result['ui_library'] = name
                    break

        # Check for server-side template frameworks
        if not result['framework']:
            result = self._detect_template_framework()

        # Check for framework-specific files
        if not result['framework']:
            for framework, config in FRAMEWORK_PATTERNS.items():
                for file_pattern in config.get('files', []):
                    if (self.repo_path / file_pattern).exists():
                        result['framework'] = framework
                        result['confidence'] = 70
                        break

        return result

    def _detect_template_framework(self) -> Dict[str, Any]:
        """Detect server-side template frameworks (Go, Django, Flask, Rails)"""
        result = {
            'framework': None,
            'version': None,
            'ui_library': None,
            'confidence': 0,
        }

        # Check for Go templates
        go_mod = self.repo_path / 'go.mod'
        if go_mod.exists():
            # Check for template directories
            template_dirs = ['templates', 'views', 'web/templates', 'internal/templates', 'web/views']
            for tmpl_dir in template_dirs:
                tmpl_path = self.repo_path / tmpl_dir
                if tmpl_path.exists() and tmpl_path.is_dir():
                    # Check for HTML files
                    html_files = list(tmpl_path.rglob('*.html')) + list(tmpl_path.rglob('*.tmpl'))
                    if html_files:
                        result['framework'] = 'go-templates'
                        result['confidence'] = 85
                        # Detect UI library from HTML
                        result['ui_library'] = self._detect_ui_library_from_html(html_files)
                        return result

        # Check for Django
        manage_py = self.repo_path / 'manage.py'
        if manage_py.exists():
            templates_dir = self.repo_path / 'templates'
            if templates_dir.exists():
                result['framework'] = 'django'
                result['confidence'] = 90
                html_files = list(templates_dir.rglob('*.html'))
                result['ui_library'] = self._detect_ui_library_from_html(html_files)
                return result

        # Check for Flask/Jinja
        app_py = self.repo_path / 'app.py'
        if app_py.exists():
            templates_dir = self.repo_path / 'templates'
            if templates_dir.exists():
                result['framework'] = 'jinja'
                result['confidence'] = 85
                html_files = list(templates_dir.rglob('*.html'))
                result['ui_library'] = self._detect_ui_library_from_html(html_files)
                return result

        # Check for Rails
        gemfile = self.repo_path / 'Gemfile'
        if gemfile.exists():
            views_dir = self.repo_path / 'app' / 'views'
            if views_dir.exists():
                result['framework'] = 'erb'
                result['confidence'] = 85
                html_files = list(views_dir.rglob('*.erb'))
                result['ui_library'] = self._detect_ui_library_from_html(html_files)
                return result

        return result

    def _detect_ui_library_from_html(self, html_files: List[Path]) -> Optional[str]:
        """Detect UI library from HTML content"""
        for html_file in html_files[:10]:  # Check first 10 files
            try:
                content = html_file.read_text(encoding='utf-8')

                if 'tailwindcss' in content or 'tailwind' in content.lower():
                    return 'Tailwind CSS'
                if 'bootstrap' in content.lower():
                    return 'Bootstrap'
                if 'bulma' in content.lower():
                    return 'Bulma'
                if 'foundation' in content.lower():
                    return 'Foundation'
                if 'material' in content.lower():
                    return 'Material Design'

            except Exception:
                continue

        return None

    def _read_package_json(self) -> Optional[Dict]:
        """Read and parse package.json"""
        package_paths = [
            self.repo_path / 'package.json',
            self.repo_path / 'frontend' / 'package.json',
            self.repo_path / 'client' / 'package.json',
            self.repo_path / 'src' / 'package.json',
        ]

        for path in package_paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Error reading {path}: {e}")
                    continue

        return None


class FrontendScreenExtractor:
    """Extracts screens/pages from the frontend codebase"""

    def __init__(self, repo_path: str, framework: str):
        self.repo_path = Path(repo_path)
        self.framework = framework

    def _extract_style_files(self, file_path: Path) -> List[str]:
        """
        Extract CSS/SCSS/style file imports from a JS/JSX/TS/TSX file.
        Also finds associated CSS modules and global stylesheets.
        """
        style_files = []

        try:
            content = file_path.read_text(encoding='utf-8')

            # Patterns for style imports in React/Next.js/Vue
            style_import_patterns = [
                # import './styles.css'
                r'import\s+[\'"]([^\'"]+\.(?:css|scss|sass|less|styl))[\'"]',
                # import styles from './styles.module.css'
                r'import\s+\w+\s+from\s+[\'"]([^\'"]+\.(?:css|scss|sass|less|styl|module\.css|module\.scss))[\'"]',
                # require('./styles.css')
                r'require\s*\(\s*[\'"]([^\'"]+\.(?:css|scss|sass|less|styl))[\'"]',
                # import './globals.css' or similar
                r'import\s+[\'"]([^\'"]*(?:global|style|app|index)[^\'"]*\.(?:css|scss))[\'"]',
            ]

            for pattern in style_import_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # Resolve relative path
                    if match.startswith('./') or match.startswith('../'):
                        resolved = (file_path.parent / match).resolve()
                        if resolved.exists():
                            style_files.append(str(resolved.relative_to(self.repo_path)))
                        else:
                            # Store the relative path anyway
                            style_files.append(match.lstrip('./'))
                    elif not match.startswith('@') and not match.startswith('~'):
                        style_files.append(match)

            # Also check for co-located CSS module (ComponentName.module.css)
            component_css_patterns = [
                file_path.with_suffix('.module.css'),
                file_path.with_suffix('.module.scss'),
                file_path.with_suffix('.css'),
                file_path.with_suffix('.scss'),
                file_path.parent / 'styles.module.css',
                file_path.parent / 'styles.css',
                file_path.parent / 'index.module.css',
            ]

            for css_path in component_css_patterns:
                if css_path.exists():
                    style_files.append(str(css_path.relative_to(self.repo_path)))

        except Exception as e:
            logger.warning(f"Error extracting styles from {file_path}: {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_styles = []
        for s in style_files:
            if s not in seen:
                seen.add(s)
                unique_styles.append(s)

        return unique_styles

    def _find_global_stylesheets(self) -> List[str]:
        """Find global/app-level stylesheets (globals.css, App.css, etc.)"""
        global_styles = []

        global_style_patterns = [
            'styles/globals.css',
            'styles/global.css',
            'app/globals.css',
            'src/styles/globals.css',
            'src/index.css',
            'src/App.css',
            'src/app.css',
            'public/styles.css',
            'styles/index.css',
            'css/main.css',
            'css/app.css',
        ]

        for pattern in global_style_patterns:
            path = self.repo_path / pattern
            if path.exists():
                global_styles.append(pattern)

        # Also search for tailwind config to indicate Tailwind usage
        tailwind_configs = ['tailwind.config.js', 'tailwind.config.ts', 'tailwind.config.mjs']
        for config in tailwind_configs:
            if (self.repo_path / config).exists():
                # Find the main CSS file that imports Tailwind
                for css_file in self.repo_path.rglob('*.css'):
                    try:
                        content = css_file.read_text(encoding='utf-8')
                        if '@tailwind' in content:
                            global_styles.append(str(css_file.relative_to(self.repo_path)))
                            break
                    except:
                        continue
                break

        return global_styles

    def extract_screens(self) -> List[Dict[str, Any]]:
        """Extract all screens/pages from the codebase"""
        screens = []

        # Get global stylesheets once
        global_styles = self._find_global_stylesheets()

        if self.framework in ['nextjs']:
            screens = self._extract_nextjs_pages(global_styles)
        elif self.framework == 'react':
            screens = self._extract_react_routes(global_styles)
        elif self.framework == 'vue':
            screens = self._extract_vue_routes()
        elif self.framework in ['go-templates', 'django', 'jinja', 'erb']:
            screens = self._extract_template_screens()
        else:
            # Generic extraction - try templates first, then JS frameworks
            screens = self._extract_template_screens()
            if not screens:
                screens = self._extract_generic_screens()

        return screens

    def _extract_template_screens(self) -> List[Dict[str, Any]]:
        """Extract screens from HTML template files (Go, Django, Flask, Rails, etc.)"""
        screens = []

        # Common template directories
        template_dirs = [
            'templates', 'views', 'web/templates', 'web/views',
            'internal/templates', 'internal/views',
            'app/views', 'src/templates', 'public',
            'static', 'html', 'pages'
        ]

        # File extensions to look for
        template_extensions = ['.html', '.tmpl', '.gohtml', '.erb', '.jinja', '.jinja2', '.twig', '.hbs']

        found_files = set()

        # Find all CSS/style files in the project
        global_styles = self._find_static_css_files()

        for tmpl_dir in template_dirs:
            dir_path = self.repo_path / tmpl_dir
            if not dir_path.exists():
                continue

            for ext in template_extensions:
                for file_path in dir_path.rglob(f'*{ext}'):
                    if file_path.is_file() and str(file_path) not in found_files:
                        found_files.add(str(file_path))

                        # Determine screen type
                        screen_type = self._determine_screen_type(file_path)

                        # Extract screen name
                        screen_name = self._html_to_screen_name(file_path)

                        # Try to determine route from file path or content
                        route = self._extract_route_from_template(file_path)

                        # Extract CSS references from the HTML template
                        template_styles = self._extract_css_from_template(file_path)
                        all_styles = list(set(global_styles + template_styles))

                        screens.append({
                            'name': screen_name,
                            'route': route,
                            'file_path': str(file_path.relative_to(self.repo_path)),
                            'screen_type': screen_type,
                            'framework': self.framework or 'templates',
                            'style_files': all_styles,
                        })

        # Also look for static HTML in root or common dirs
        for html_file in self.repo_path.glob('*.html'):
            if str(html_file) not in found_files:
                found_files.add(str(html_file))
                template_styles = self._extract_css_from_template(html_file)
                all_styles = list(set(global_styles + template_styles))
                screens.append({
                    'name': self._html_to_screen_name(html_file),
                    'route': f'/{html_file.stem}' if html_file.stem != 'index' else '/',
                    'file_path': str(html_file.relative_to(self.repo_path)),
                    'screen_type': 'page',
                    'framework': self.framework or 'static',
                    'style_files': all_styles,
                })

        return screens

    def _find_static_css_files(self) -> List[str]:
        """Find global CSS/SCSS files in static directories"""
        css_files = []

        static_dirs = ['static', 'public', 'assets', 'css', 'styles', 'staticfiles',
                       'static/css', 'public/css', 'assets/css', 'web/static']

        for static_dir in static_dirs:
            dir_path = self.repo_path / static_dir
            if dir_path.exists():
                for css_file in dir_path.rglob('*.css'):
                    css_files.append(str(css_file.relative_to(self.repo_path)))
                for scss_file in dir_path.rglob('*.scss'):
                    css_files.append(str(scss_file.relative_to(self.repo_path)))

        return css_files[:20]  # Limit to avoid too many files

    def _extract_css_from_template(self, file_path: Path) -> List[str]:
        """Extract CSS file references from HTML template"""
        css_files = []

        try:
            content = file_path.read_text(encoding='utf-8')

            # Find <link rel="stylesheet" href="...">
            link_patterns = [
                r'<link[^>]+href=["\']([^"\']+\.css)["\']',
                r'<link[^>]+href=["\']([^"\']+\.scss)["\']',
                # Django static template tag
                r'\{%\s*static\s+["\']([^"\']+\.css)["\']',
                # Go template
                r'\{\{\s*\.?Static[^}]*["\']([^"\']+\.css)["\']',
                # General href patterns
                r'href=["\']([^"\']*(?:style|css)[^"\']*\.css)["\']',
            ]

            for pattern in link_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Clean up the path
                    css_path = match.strip()
                    if css_path.startswith('/'):
                        css_path = css_path[1:]
                    if not css_path.startswith('http'):
                        css_files.append(css_path)

            # Also check for inline <style> blocks - note their presence
            if '<style' in content:
                # Mark that this template has inline styles
                pass

        except Exception as e:
            logger.warning(f"Error extracting CSS from {file_path}: {e}")

        return list(set(css_files))

    def _determine_screen_type(self, file_path: Path) -> str:
        """Determine if file is a page, partial, layout, or component"""
        name_lower = file_path.name.lower()
        parent_lower = file_path.parent.name.lower()

        # Check for partials/components
        if 'partial' in parent_lower or 'partial' in name_lower:
            return 'partial'
        if 'component' in parent_lower or 'component' in name_lower:
            return 'component'
        if 'layout' in name_lower or 'base' in name_lower:
            return 'layout'
        if 'modal' in name_lower:
            return 'modal'
        if 'email' in parent_lower or 'mail' in parent_lower:
            return 'email'

        return 'page'

    def _html_to_screen_name(self, file_path: Path) -> str:
        """Convert HTML file path to a readable screen name"""
        # Get stem without extension
        name = file_path.stem

        # Remove common prefixes/suffixes
        name = re.sub(r'^(page_|view_|template_)', '', name)
        name = re.sub(r'(_page|_view|_template)$', '', name)

        # Convert to title case
        name = ' '.join(word.capitalize() for word in re.split(r'[-_]', name))

        return name or 'Unknown'

    def _extract_route_from_template(self, file_path: Path) -> Optional[str]:
        """Try to extract route from template file path or content"""
        relative = file_path.relative_to(self.repo_path)
        parts = list(relative.parts)

        # Remove template directory prefix
        template_dirs = ['templates', 'views', 'web', 'internal', 'app', 'pages']
        while parts and parts[0].lower() in template_dirs:
            parts = parts[1:]

        if not parts:
            return '/'

        # Build route from remaining path
        route_parts = []
        for part in parts[:-1]:  # Exclude filename
            route_parts.append(part)

        # Add filename without extension
        filename = parts[-1]
        stem = Path(filename).stem
        if stem.lower() not in ['index', 'home', 'main', 'base', 'layout']:
            route_parts.append(stem)

        route = '/' + '/'.join(route_parts)
        return route if route != '/' or not route_parts else '/'

    def _extract_nextjs_pages(self, global_styles: List[str] = None) -> List[Dict[str, Any]]:
        """Extract pages from Next.js file-based routing"""
        screens = []
        pages_dirs = ['pages', 'app', 'src/pages', 'src/app']
        global_styles = global_styles or []

        for pages_dir in pages_dirs:
            dir_path = self.repo_path / pages_dir
            if not dir_path.exists():
                continue

            is_app_router = 'app' in pages_dir

            for file_path in dir_path.rglob('*'):
                if file_path.is_file() and file_path.suffix in ['.js', '.jsx', '.ts', '.tsx']:
                    # Skip special files
                    if file_path.name.startswith('_') or file_path.name.startswith('['):
                        continue
                    if file_path.name in ['layout.tsx', 'layout.js', 'loading.tsx', 'loading.js',
                                          'error.tsx', 'error.js', 'not-found.tsx', 'not-found.js']:
                        if is_app_router and file_path.name.startswith('page'):
                            pass  # page.tsx files are valid
                        else:
                            continue

                    # Calculate route from file path
                    relative_path = file_path.relative_to(dir_path)
                    route = self._file_to_route(str(relative_path), is_app_router)

                    # Extract screen name from file
                    screen_name = self._extract_component_name(file_path) or \
                                  self._path_to_screen_name(str(relative_path))

                    # Extract style files from imports
                    style_files = self._extract_style_files(file_path)
                    # Add global styles
                    all_styles = list(set(global_styles + style_files))

                    screens.append({
                        'name': screen_name,
                        'route': route,
                        'file_path': str(file_path.relative_to(self.repo_path)),
                        'screen_type': 'page',
                        'framework': 'nextjs',
                        'style_files': all_styles,
                    })

        return screens

    def _extract_react_routes(self, global_styles: List[str] = None) -> List[Dict[str, Any]]:
        """Extract routes from React Router configuration"""
        screens = []
        global_styles = global_styles or []

        # Find router configuration files
        route_files = list(self.repo_path.rglob('*router*.{js,jsx,ts,tsx}')) + \
                     list(self.repo_path.rglob('*routes*.{js,jsx,ts,tsx}')) + \
                     list(self.repo_path.rglob('App.{js,jsx,ts,tsx}'))

        for route_file in route_files:
            if route_file.is_file():
                try:
                    content = route_file.read_text(encoding='utf-8')
                    # Extract style files from the router file
                    style_files = self._extract_style_files(route_file)
                    all_styles = list(set(global_styles + style_files))

                    for pattern in ROUTE_PATTERNS['react-router']:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            route = match[0] if isinstance(match, tuple) else match
                            component = match[1] if isinstance(match, tuple) and len(match) > 1 else None

                            screens.append({
                                'name': component or self._path_to_screen_name(route),
                                'route': route,
                                'file_path': str(route_file.relative_to(self.repo_path)),
                                'screen_type': 'page',
                                'framework': 'react',
                                'style_files': all_styles,
                            })
                except Exception as e:
                    logger.warning(f"Error parsing routes from {route_file}: {e}")

        # Also scan for component files in common directories
        component_dirs = ['src/pages', 'src/views', 'src/screens', 'pages', 'views', 'components/pages']
        for comp_dir in component_dirs:
            dir_path = self.repo_path / comp_dir
            if dir_path.exists():
                for file_path in dir_path.rglob('*.{jsx,tsx,js,ts}'):
                    if file_path.is_file():
                        # Extract styles from component file
                        comp_styles = self._extract_style_files(file_path)
                        all_styles = list(set(global_styles + comp_styles))

                        screen_name = self._extract_component_name(file_path) or file_path.stem
                        screens.append({
                            'name': screen_name,
                            'route': None,  # Route determined by router config
                            'file_path': str(file_path.relative_to(self.repo_path)),
                            'screen_type': 'page',
                            'framework': 'react',
                            'style_files': all_styles,
                        })

        return screens

    def _extract_vue_routes(self) -> List[Dict[str, Any]]:
        """Extract routes from Vue Router configuration"""
        screens = []

        route_files = list(self.repo_path.rglob('*router*.{js,ts}')) + \
                     list(self.repo_path.rglob('routes*.{js,ts}'))

        for route_file in route_files:
            if route_file.is_file():
                try:
                    content = route_file.read_text(encoding='utf-8')

                    for pattern in ROUTE_PATTERNS['vue-router']:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            route = match[0]
                            component = match[1] if len(match) > 1 else None

                            screens.append({
                                'name': component or self._path_to_screen_name(route),
                                'route': route,
                                'file_path': str(route_file.relative_to(self.repo_path)),
                                'screen_type': 'page',
                                'framework': 'vue',
                            })
                except Exception as e:
                    logger.warning(f"Error parsing Vue routes from {route_file}: {e}")

        return screens

    def _extract_generic_screens(self) -> List[Dict[str, Any]]:
        """Generic screen extraction for unknown frameworks"""
        screens = []
        screen_patterns = ['**/pages/**/*.{js,jsx,ts,tsx,vue}', '**/views/**/*.{js,jsx,ts,tsx,vue}',
                          '**/screens/**/*.{js,jsx,ts,tsx,vue}']

        for pattern in screen_patterns:
            for file_path in self.repo_path.glob(pattern):
                if file_path.is_file():
                    screens.append({
                        'name': self._extract_component_name(file_path) or file_path.stem,
                        'route': None,
                        'file_path': str(file_path.relative_to(self.repo_path)),
                        'screen_type': 'page',
                        'framework': 'unknown',
                    })

        return screens

    def _file_to_route(self, file_path: str, is_app_router: bool = False) -> str:
        """Convert file path to route"""
        # Remove extension
        route = re.sub(r'\.(js|jsx|ts|tsx)$', '', file_path)

        # Handle app router (page.tsx files)
        if is_app_router:
            route = re.sub(r'/page$', '', route)

        # Handle index files
        route = re.sub(r'/index$', '', route)

        # Handle dynamic routes
        route = re.sub(r'\[([^\]]+)\]', r':\1', route)

        # Ensure leading slash
        if not route.startswith('/'):
            route = '/' + route

        # Handle root
        if route == '':
            route = '/'

        return route

    def _path_to_screen_name(self, path: str) -> str:
        """Convert path to screen name"""
        # Remove extension and split
        name = re.sub(r'\.(js|jsx|ts|tsx|vue)$', '', path)
        # Take last part and capitalize
        parts = name.split('/')
        last_part = parts[-1] if parts[-1] != 'index' else (parts[-2] if len(parts) > 1 else 'Home')
        # Convert kebab-case or snake_case to Title Case
        return ' '.join(word.capitalize() for word in re.split(r'[-_]', last_part))

    def _extract_component_name(self, file_path: Path) -> Optional[str]:
        """Extract component name from file content"""
        try:
            content = file_path.read_text(encoding='utf-8')

            # Look for export default function/const ComponentName
            patterns = [
                r'export\s+default\s+function\s+([A-Z][a-zA-Z0-9]*)',
                r'export\s+default\s+([A-Z][a-zA-Z0-9]*)',
                r'const\s+([A-Z][a-zA-Z0-9]*)\s*=\s*\(?.*?\)?\s*=>\s*{?[\s\S]*?export\s+default\s+\1',
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)

        except Exception:
            pass

        return None


class FrontendComponentExtractor:
    """Extracts UI components from screen files"""

    def __init__(self, repo_path: str, framework: str):
        self.repo_path = Path(repo_path)
        self.framework = framework

    def extract_components(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract UI components from a file"""
        components = []
        full_path = self.repo_path / file_path

        if not full_path.exists():
            return components

        try:
            content = full_path.read_text(encoding='utf-8')
            lines = content.split('\n')

            for component_type, patterns in COMPONENT_PATTERNS.items():
                for pattern in patterns:
                    for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                        # Find line number
                        start_pos = match.start()
                        line_num = content[:start_pos].count('\n') + 1

                        # Extract component details
                        component = {
                            'component_type': component_type,
                            'name': self._extract_name(match.group(0), component_type),
                            'file_path': file_path,
                            'start_line': line_num,
                            'end_line': line_num,
                            'label_text': self._extract_label(match.group(0)),
                            'props': self._extract_props(match.group(0)),
                            'is_interactive': component_type in ['button', 'link', 'input', 'form', 'dropdown', 'tab'],
                            'action_type': self._determine_action_type(match.group(0), component_type),
                            'action_target': self._extract_action_target(match.group(0)),
                        }

                        components.append(component)

        except Exception as e:
            logger.warning(f"Error extracting components from {file_path}: {e}")

        return components

    def _extract_name(self, element: str, component_type: str) -> str:
        """Extract component name from element"""
        # Try to get id or name attribute
        id_match = re.search(r'id=["\']([^"\']+)["\']', element)
        if id_match:
            return id_match.group(1)

        name_match = re.search(r'name=["\']([^"\']+)["\']', element)
        if name_match:
            return name_match.group(1)

        # Try to get text content
        text_match = re.search(r'>([^<]+)<', element)
        if text_match:
            return text_match.group(1).strip()[:50]

        return f"{component_type.capitalize()}"

    def _extract_label(self, element: str) -> Optional[str]:
        """Extract label text from element"""
        # Get text between tags
        text_match = re.search(r'>([^<]+)<', element)
        if text_match:
            return text_match.group(1).strip()

        # Check for placeholder
        placeholder_match = re.search(r'placeholder=["\']([^"\']+)["\']', element)
        if placeholder_match:
            return placeholder_match.group(1)

        # Check for aria-label
        aria_match = re.search(r'aria-label=["\']([^"\']+)["\']', element)
        if aria_match:
            return aria_match.group(1)

        return None

    def _extract_props(self, element: str) -> Dict[str, Any]:
        """Extract props/attributes from element"""
        props = {}

        # Extract common attributes
        attr_patterns = [
            (r'className=["\']([^"\']+)["\']', 'className'),
            (r'class=["\']([^"\']+)["\']', 'class'),
            (r'type=["\']([^"\']+)["\']', 'type'),
            (r'variant=["\']([^"\']+)["\']', 'variant'),
            (r'size=["\']([^"\']+)["\']', 'size'),
            (r'disabled', 'disabled'),
        ]

        for pattern, attr_name in attr_patterns:
            match = re.search(pattern, element)
            if match:
                props[attr_name] = match.group(1) if match.lastindex else True

        return props

    def _determine_action_type(self, element: str, component_type: str) -> str:
        """Determine the action type for a component"""
        if component_type == 'link':
            return 'navigate'
        if component_type == 'form':
            return 'submit'

        # Check for onClick with navigation
        if 'navigate' in element.lower() or 'push' in element.lower() or 'router' in element.lower():
            return 'navigate'

        # Check for modal triggers
        if 'modal' in element.lower() or 'dialog' in element.lower():
            return 'modal_open'

        # Check for API calls
        if 'fetch' in element.lower() or 'axios' in element.lower() or 'api' in element.lower():
            return 'api_call'

        if component_type in ['button', 'link']:
            return 'navigate'

        return 'none'

    def _extract_action_target(self, element: str) -> Optional[str]:
        """Extract action target (route, API endpoint, etc.)"""
        # Check for href
        href_match = re.search(r'href=["\']([^"\']+)["\']', element)
        if href_match:
            return href_match.group(1)

        # Check for to (React Router)
        to_match = re.search(r'to=["\']([^"\']+)["\']', element)
        if to_match:
            return to_match.group(1)

        # Check for onClick navigation
        nav_match = re.search(r'navigate\(["\']([^"\']+)["\']', element)
        if nav_match:
            return nav_match.group(1)

        push_match = re.search(r'push\(["\']([^"\']+)["\']', element)
        if push_match:
            return push_match.group(1)

        return None


class FrontendUIIndexer:
    """Main class for indexing frontend UI components"""

    def __init__(self, indexed_repository):
        self.repository = indexed_repository
        self.repo_path = None

    def index_frontend(self, temp_dir: str) -> Tuple[bool, str]:
        """Index the frontend UI components"""
        from .models import (
            FrontendScreen, FrontendUIComponent, FrontendIndexingStatus
        )

        self.repo_path = temp_dir

        try:
            # Create or update indexing status
            status, created = FrontendIndexingStatus.objects.get_or_create(
                repository=self.repository,
                defaults={'status': 'analyzing'}
            )
            status.status = 'analyzing'
            status.save()

            # Detect framework
            detector = FrontendFrameworkDetector(temp_dir)
            framework_info = detector.detect_framework()

            logger.info(f"Detected framework: {framework_info}")

            if not framework_info['framework']:
                status.status = 'error'
                status.error_message = 'Could not detect frontend framework'
                status.save()
                return False, 'Could not detect frontend framework'

            # Update status with framework info
            status.detected_framework = framework_info['framework']
            status.framework_version = framework_info.get('version')
            status.ui_library = framework_info.get('ui_library')
            status.save()

            # Clear existing data
            FrontendScreen.objects.filter(repository=self.repository).delete()

            # Extract screens
            screen_extractor = FrontendScreenExtractor(temp_dir, framework_info['framework'])
            screens = screen_extractor.extract_screens()

            logger.info(f"Extracted {len(screens)} screens")

            # Create screen records and extract components
            component_extractor = FrontendComponentExtractor(temp_dir, framework_info['framework'])
            total_components = 0
            navigation_flow = {}

            for screen_data in screens:
                screen = FrontendScreen.objects.create(
                    repository=self.repository,
                    name=screen_data['name'],
                    route=screen_data.get('route'),
                    file_path=screen_data['file_path'],
                    screen_type=screen_data.get('screen_type', 'page'),
                    framework=screen_data.get('framework'),
                )

                # Extract components from screen file
                components = component_extractor.extract_components(screen_data['file_path'])

                for comp_data in components:
                    FrontendUIComponent.objects.create(
                        screen=screen,
                        name=comp_data['name'],
                        component_type=comp_data['component_type'],
                        file_path=comp_data['file_path'],
                        start_line=comp_data['start_line'],
                        end_line=comp_data['end_line'],
                        label_text=comp_data.get('label_text'),
                        props=comp_data.get('props', {}),
                        is_interactive=comp_data.get('is_interactive', False),
                        action_type=comp_data.get('action_type', 'none'),
                        action_target=comp_data.get('action_target'),
                    )
                    total_components += 1

                    # Build navigation flow
                    if comp_data.get('action_target') and comp_data.get('action_type') == 'navigate':
                        if screen.route not in navigation_flow:
                            navigation_flow[screen.route or screen.name] = []
                        navigation_flow[screen.route or screen.name].append({
                            'target': comp_data['action_target'],
                            'component': comp_data['name'],
                            'type': comp_data['component_type'],
                        })

            # Link navigation between screens
            self._link_navigation_targets()

            # Update status
            status.status = 'completed'
            status.last_indexed_at = timezone.now()
            status.total_screens = len(screens)
            status.total_components = total_components
            status.total_routes = len([s for s in screens if s.get('route')])
            status.navigation_flow = navigation_flow
            status.error_message = None
            status.save()

            return True, f"Indexed {len(screens)} screens with {total_components} components"

        except Exception as e:
            logger.exception(f"Error indexing frontend: {e}")

            # Update status with error
            try:
                status = FrontendIndexingStatus.objects.get(repository=self.repository)
                status.status = 'error'
                status.error_message = str(e)
                status.save()
            except FrontendIndexingStatus.DoesNotExist:
                pass

            return False, str(e)

    def _link_navigation_targets(self):
        """Link navigation components to their target screens"""
        from .models import FrontendScreen, FrontendUIComponent

        screens = FrontendScreen.objects.filter(repository=self.repository)
        route_to_screen = {s.route: s for s in screens if s.route}

        # Update components with navigation targets
        components = FrontendUIComponent.objects.filter(
            screen__repository=self.repository,
            action_type='navigate',
            action_target__isnull=False
        )

        for component in components:
            target = component.action_target
            if target in route_to_screen:
                component.navigates_to = route_to_screen[target]
                component.save()
