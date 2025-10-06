import ast
import re
import hashlib
import os
from typing import List, Dict, Any, Optional, Tuple
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class CodeParser:
    """Base class for code parsing with common functionality"""
    
    LANGUAGE_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.go': 'go',
        '.rs': 'rust',
        '.php': 'php',
    }
    
    def __init__(self):
        self.parsers = {
            'python': PythonParser(),
            'javascript': JavaScriptParser(),
            'typescript': JavaScriptParser(),  # TypeScript uses similar patterns
        }
    
    def detect_language(self, file_path: str, content: str) -> str:
        """Detect programming language from file extension and content"""
        ext = Path(file_path).suffix.lower()
        return self.LANGUAGE_EXTENSIONS.get(ext, 'unknown')
    
    def parse_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Parse a file and extract code chunks with metadata"""
        language = self.detect_language(file_path, content)
        
        # Get appropriate parser
        parser = self.parsers.get(language)
        if not parser:
            # Fallback to generic parsing for unknown languages
            return self._parse_generic(file_path, content, language)
        
        try:
            return parser.parse(file_path, content, language)
        except Exception as e:
            logger.warning(f"Language-specific parsing failed for {file_path}, falling back to generic: {e}")
            return self._parse_generic(file_path, content, language)
    
    def _parse_generic(self, file_path: str, content: str, language: str) -> Dict[str, Any]:
        """Generic parsing for unsupported languages"""
        lines = content.split('\n')
        
        chunks = []
        
        # Create a full-file chunk
        chunks.append({
            'chunk_type': 'file',
            'content': content,
            'content_preview': self._generate_preview(content),
            'start_line': 1,
            'end_line': len(lines),
            'function_name': None,
            'complexity': self._estimate_complexity(content),
            'dependencies': self._extract_imports_generic(content),
            'parameters': [],
            'tags': [language, 'full-file'],
            'description': None
        })
        
        return {
            'language': language,
            'total_lines': len(lines),
            'chunks': chunks,
            'functions_count': 0,
            'classes_count': 0,
            'imports': self._extract_imports_generic(content)
        }
    
    def _generate_preview(self, content: str, max_length: int = 200) -> str:
        """Generate a preview of the content"""
        # Remove extra whitespace and truncate
        preview = ' '.join(content.split())
        return preview[:max_length] + '...' if len(preview) > max_length else preview
    
    def _estimate_complexity(self, content: str) -> str:
        """Estimate code complexity based on various factors"""
        lines = len(content.split('\n'))
        
        # Count complexity indicators
        complexity_indicators = [
            'if', 'while', 'for', 'try', 'except', 'elif', 'else',
            'switch', 'case', 'catch', 'finally'
        ]
        
        complexity_count = sum(content.lower().count(indicator) for indicator in complexity_indicators)
        
        if lines < 20 and complexity_count < 3:
            return 'low'
        elif lines < 100 and complexity_count < 10:
            return 'medium'
        else:
            return 'high'
    
    def _extract_imports_generic(self, content: str) -> List[str]:
        """Extract imports using regex patterns for common languages"""
        imports = []
        
        # Python imports
        python_imports = re.findall(r'^\s*(?:from\s+(\S+)\s+)?import\s+(.+)', content, re.MULTILINE)
        for from_part, import_part in python_imports:
            if from_part:
                imports.append(f"{from_part}.{import_part.split(',')[0].strip()}")
            else:
                imports.append(import_part.split(',')[0].strip())
        
        # JavaScript/TypeScript imports
        js_imports = re.findall(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE)
        imports.extend(js_imports)
        
        # Java imports
        java_imports = re.findall(r'^\s*import\s+([^;]+);', content, re.MULTILINE)
        imports.extend(java_imports)
        
        return list(set(imports))


class PythonParser:
    """Specialized parser for Python code using AST"""
    
    def parse(self, file_path: str, content: str, language: str) -> Dict[str, Any]:
        """Parse Python code using AST"""
        try:
            tree = ast.parse(content)
            analyzer = PythonASTAnalyzer()
            return analyzer.analyze(tree, content, file_path, language)
        except SyntaxError as e:
            logger.warning(f"Python syntax error in {file_path}: {e}")
            # Fall back to regex-based parsing
            return self._parse_python_regex(file_path, content, language)
    
    def _parse_python_regex(self, file_path: str, content: str, language: str) -> Dict[str, Any]:
        """Fallback regex-based Python parsing"""
        lines = content.split('\n')
        chunks = []
        
        # Extract functions and classes using regex
        function_pattern = re.compile(r'^(\s*)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\):', re.MULTILINE)
        class_pattern = re.compile(r'^(\s*)class\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.MULTILINE)
        
        for match in function_pattern.finditer(content):
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1
            function_name = match.group(2)
            parameters = [p.strip() for p in match.group(3).split(',') if p.strip()]
            
            # Find function end (simplified)
            end_line = self._find_python_block_end(lines, start_line - 1)
            
            function_content = '\n'.join(lines[start_line-1:end_line])
            
            chunks.append({
                'chunk_type': 'function',
                'content': function_content,
                'content_preview': f"def {function_name}({match.group(3)})",
                'start_line': start_line,
                'end_line': end_line,
                'function_name': function_name,
                'complexity': self._estimate_complexity(function_content),
                'dependencies': self._extract_python_dependencies(function_content),
                'parameters': parameters,
                'tags': ['python', 'function', function_name],
                'description': None
            })
        
        for match in class_pattern.finditer(content):
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1
            class_name = match.group(2)
            
            end_line = self._find_python_block_end(lines, start_line - 1)
            class_content = '\n'.join(lines[start_line-1:end_line])
            
            chunks.append({
                'chunk_type': 'class',
                'content': class_content,
                'content_preview': f"class {class_name}",
                'start_line': start_line,
                'end_line': end_line,
                'function_name': class_name,
                'complexity': self._estimate_complexity(class_content),
                'dependencies': self._extract_python_dependencies(class_content),
                'parameters': [],
                'tags': ['python', 'class', class_name],
                'description': None
            })
        
        # Add full file chunk
        chunks.append({
            'chunk_type': 'file',
            'content': content,
            'content_preview': f"Python file: {os.path.basename(file_path)}",
            'start_line': 1,
            'end_line': len(lines),
            'function_name': None,
            'complexity': self._estimate_complexity(content),
            'dependencies': self._extract_python_imports(content),
            'parameters': [],
            'tags': ['python', 'full-file'],
            'description': None
        })
        
        return {
            'language': language,
            'total_lines': len(lines),
            'chunks': chunks,
            'functions_count': len([c for c in chunks if c['chunk_type'] == 'function']),
            'classes_count': len([c for c in chunks if c['chunk_type'] == 'class']),
            'imports': self._extract_python_imports(content)
        }
    
    def _find_python_block_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end of a Python block (class or function)"""
        if start_idx >= len(lines):
            return len(lines)
        
        # Get the indentation of the definition line
        def_line = lines[start_idx]
        base_indent = len(def_line) - len(def_line.lstrip())
        
        # Find the end of the block
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if line.strip() == '':  # Skip empty lines
                continue
            
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= base_indent and line.strip():
                return i
        
        return len(lines)
    
    def _estimate_complexity(self, content: str) -> str:
        """Estimate Python code complexity"""
        complexity_keywords = ['if', 'elif', 'else', 'for', 'while', 'try', 'except', 'with']
        complexity_count = sum(content.count(keyword) for keyword in complexity_keywords)
        lines = len(content.split('\n'))
        
        if complexity_count < 3 and lines < 20:
            return 'low'
        elif complexity_count < 10 and lines < 100:
            return 'medium'
        else:
            return 'high'
    
    def _extract_python_imports(self, content: str) -> List[str]:
        """Extract Python imports"""
        imports = []
        
        # Standard imports
        import_matches = re.findall(r'^\s*import\s+([^\s#]+)', content, re.MULTILINE)
        imports.extend(import_matches)
        
        # From imports
        from_matches = re.findall(r'^\s*from\s+([^\s#]+)\s+import', content, re.MULTILINE)
        imports.extend(from_matches)
        
        return list(set(imports))
    
    def _extract_python_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from a code chunk"""
        # This is a simplified version - could be enhanced with more sophisticated analysis
        return self._extract_python_imports(content)


class PythonASTAnalyzer(ast.NodeVisitor):
    """AST analyzer for Python code"""
    
    def __init__(self):
        self.functions = []
        self.classes = []
        self.imports = []
        self.content = ""
        self.lines = []
    
    def analyze(self, tree: ast.AST, content: str, file_path: str, language: str) -> Dict[str, Any]:
        """Analyze Python AST and extract chunks"""
        self.content = content
        self.lines = content.split('\n')
        
        # Visit all nodes in the AST
        self.visit(tree)
        
        chunks = []
        
        # Process functions
        for func_info in self.functions:
            func_content = self._extract_content(func_info['start_line'], func_info['end_line'])
            chunks.append({
                'chunk_type': 'function',
                'content': func_content,
                'content_preview': f"def {func_info['name']}({', '.join(func_info['parameters'])})",
                'start_line': func_info['start_line'],
                'end_line': func_info['end_line'],
                'function_name': func_info['name'],
                'complexity': self._calculate_complexity(func_info),
                'dependencies': func_info['dependencies'],
                'parameters': func_info['parameters'],
                'tags': ['python', 'function', func_info['name']],
                'description': func_info['docstring']
            })
        
        # Process classes
        for class_info in self.classes:
            class_content = self._extract_content(class_info['start_line'], class_info['end_line'])
            chunks.append({
                'chunk_type': 'class',
                'content': class_content,
                'content_preview': f"class {class_info['name']}",
                'start_line': class_info['start_line'],
                'end_line': class_info['end_line'],
                'function_name': class_info['name'],
                'complexity': self._calculate_complexity(class_info),
                'dependencies': class_info['dependencies'],
                'parameters': class_info['methods'],
                'tags': ['python', 'class', class_info['name']],
                'description': class_info['docstring']
            })
        
        # Add imports chunk if there are imports
        if self.imports:
            import_lines = [i['line'] for i in self.imports]
            import_content = '\n'.join(import_lines)
            chunks.append({
                'chunk_type': 'import',
                'content': import_content,
                'content_preview': f"{len(self.imports)} import statements",
                'start_line': min(i['line_num'] for i in self.imports),
                'end_line': max(i['line_num'] for i in self.imports),
                'function_name': None,
                'complexity': 'low',
                'dependencies': [i['module'] for i in self.imports],
                'parameters': [],
                'tags': ['python', 'imports'],
                'description': 'Import statements'
            })
        
        # Add full file chunk
        chunks.append({
            'chunk_type': 'file',
            'content': content,
            'content_preview': f"Python file: {os.path.basename(file_path)}",
            'start_line': 1,
            'end_line': len(self.lines),
            'function_name': None,
            'complexity': self._estimate_file_complexity(),
            'dependencies': [i['module'] for i in self.imports],
            'parameters': [],
            'tags': ['python', 'full-file'],
            'description': None
        })
        
        return {
            'language': language,
            'total_lines': len(self.lines),
            'chunks': chunks,
            'functions_count': len(self.functions),
            'classes_count': len(self.classes),
            'imports': [i['module'] for i in self.imports]
        }
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition nodes"""
        # Extract function metadata
        func_info = {
            'name': node.name,
            'start_line': node.lineno,
            'end_line': node.end_lineno or node.lineno,
            'parameters': [arg.arg for arg in node.args.args],
            'docstring': ast.get_docstring(node),
            'dependencies': [],
            'complexity_nodes': 0
        }
        
        # Count complexity-increasing nodes
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                func_info['complexity_nodes'] += 1
        
        self.functions.append(func_info)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition nodes"""
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(item.name)
        
        class_info = {
            'name': node.name,
            'start_line': node.lineno,
            'end_line': node.end_lineno or node.lineno,
            'methods': methods,
            'docstring': ast.get_docstring(node),
            'dependencies': [],
            'complexity_nodes': len(methods)
        }
        
        self.classes.append(class_info)
        self.generic_visit(node)
    
    def visit_Import(self, node: ast.Import):
        """Visit import nodes"""
        for alias in node.names:
            self.imports.append({
                'module': alias.name,
                'alias': alias.asname,
                'line_num': node.lineno,
                'line': f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
            })
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Visit from...import nodes"""
        module = node.module or ''
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imports.append({
                'module': full_name,
                'alias': alias.asname,
                'line_num': node.lineno,
                'line': f"from {module} import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
            })
        self.generic_visit(node)
    
    def _extract_content(self, start_line: int, end_line: int) -> str:
        """Extract content between line numbers"""
        return '\n'.join(self.lines[start_line-1:end_line])
    
    def _calculate_complexity(self, item_info: Dict[str, Any]) -> str:
        """Calculate complexity based on various factors"""
        complexity_nodes = item_info.get('complexity_nodes', 0)
        line_count = item_info['end_line'] - item_info['start_line'] + 1
        
        if complexity_nodes <= 2 and line_count <= 20:
            return 'low'
        elif complexity_nodes <= 8 and line_count <= 100:
            return 'medium'
        else:
            return 'high'
    
    def _estimate_file_complexity(self) -> str:
        """Estimate overall file complexity"""
        total_functions = len(self.functions)
        total_classes = len(self.classes)
        total_lines = len(self.lines)
        
        if total_functions + total_classes <= 5 and total_lines <= 100:
            return 'low'
        elif total_functions + total_classes <= 20 and total_lines <= 500:
            return 'medium'
        else:
            return 'high'


class JavaScriptParser:
    """Parser for JavaScript/TypeScript code"""
    
    def parse(self, file_path: str, content: str, language: str) -> Dict[str, Any]:
        """Parse JavaScript/TypeScript code using regex patterns"""
        lines = content.split('\n')
        chunks = []
        
        # Function patterns for JavaScript/TypeScript
        function_patterns = [
            re.compile(r'^\s*function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(([^)]*)\)', re.MULTILINE),
            re.compile(r'^\s*const\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*\(([^)]*)\)\s*=>', re.MULTILINE),
            re.compile(r'^\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:\s*\(([^)]*)\)\s*=>', re.MULTILINE),
        ]
        
        # Class pattern
        class_pattern = re.compile(r'^\s*class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', re.MULTILINE)
        
        # Extract functions
        for pattern in function_patterns:
            for match in pattern.finditer(content):
                start_pos = match.start()
                start_line = content[:start_pos].count('\n') + 1
                function_name = match.group(1)
                parameters = [p.strip() for p in match.group(2).split(',') if p.strip()]
                
                # Estimate end line (simplified)
                end_line = self._find_js_block_end(lines, start_line - 1)
                
                function_content = '\n'.join(lines[start_line-1:end_line])
                
                chunks.append({
                    'chunk_type': 'function',
                    'content': function_content,
                    'content_preview': f"{function_name}({match.group(2)})",
                    'start_line': start_line,
                    'end_line': end_line,
                    'function_name': function_name,
                    'complexity': self._estimate_js_complexity(function_content),
                    'dependencies': self._extract_js_dependencies(function_content),
                    'parameters': parameters,
                    'tags': [language, 'function', function_name],
                    'description': None
                })
        
        # Extract classes
        for match in class_pattern.finditer(content):
            start_pos = match.start()
            start_line = content[:start_pos].count('\n') + 1
            class_name = match.group(1)
            
            end_line = self._find_js_block_end(lines, start_line - 1)
            class_content = '\n'.join(lines[start_line-1:end_line])
            
            chunks.append({
                'chunk_type': 'class',
                'content': class_content,
                'content_preview': f"class {class_name}",
                'start_line': start_line,
                'end_line': end_line,
                'function_name': class_name,
                'complexity': self._estimate_js_complexity(class_content),
                'dependencies': self._extract_js_dependencies(class_content),
                'parameters': [],
                'tags': [language, 'class', class_name],
                'description': None
            })
        
        # Extract imports
        imports = self._extract_js_imports(content)
        if imports:
            import_lines_info = []
            for match in re.finditer(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE):
                start_pos = match.start()
                line_num = content[:start_pos].count('\n') + 1
                import_lines_info.append((line_num, lines[line_num-1]))
            
            if import_lines_info:
                import_content = '\n'.join([line for _, line in import_lines_info])
                chunks.append({
                    'chunk_type': 'import',
                    'content': import_content,
                    'content_preview': f"{len(imports)} import statements",
                    'start_line': min(line_num for line_num, _ in import_lines_info),
                    'end_line': max(line_num for line_num, _ in import_lines_info),
                    'function_name': None,
                    'complexity': 'low',
                    'dependencies': imports,
                    'parameters': [],
                    'tags': [language, 'imports'],
                    'description': 'Import statements'
                })
        
        # Add full file chunk
        chunks.append({
            'chunk_type': 'file',
            'content': content,
            'content_preview': f"{language.title()} file: {os.path.basename(file_path)}",
            'start_line': 1,
            'end_line': len(lines),
            'function_name': None,
            'complexity': self._estimate_js_complexity(content),
            'dependencies': imports,
            'parameters': [],
            'tags': [language, 'full-file'],
            'description': None
        })
        
        return {
            'language': language,
            'total_lines': len(lines),
            'chunks': chunks,
            'functions_count': len([c for c in chunks if c['chunk_type'] == 'function']),
            'classes_count': len([c for c in chunks if c['chunk_type'] == 'class']),
            'imports': imports
        }
    
    def _find_js_block_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end of a JavaScript/TypeScript block"""
        if start_idx >= len(lines):
            return len(lines)
        
        brace_count = 0
        found_opening = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    found_opening = True
                elif char == '}':
                    brace_count -= 1
                    if found_opening and brace_count == 0:
                        return i + 1
        
        return len(lines)
    
    def _estimate_js_complexity(self, content: str) -> str:
        """Estimate JavaScript/TypeScript complexity"""
        complexity_keywords = ['if', 'else', 'for', 'while', 'try', 'catch', 'switch', 'case']
        complexity_count = sum(content.count(keyword) for keyword in complexity_keywords)
        lines = len(content.split('\n'))
        
        if complexity_count < 3 and lines < 30:
            return 'low'
        elif complexity_count < 10 and lines < 150:
            return 'medium'
        else:
            return 'high'
    
    def _extract_js_imports(self, content: str) -> List[str]:
        """Extract JavaScript/TypeScript imports"""
        imports = []
        
        # ES6 imports
        import_matches = re.findall(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE)
        imports.extend(import_matches)
        
        # CommonJS requires
        require_matches = re.findall(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content)
        imports.extend(require_matches)
        
        return list(set(imports))
    
    def _extract_js_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from JavaScript/TypeScript code"""
        return self._extract_js_imports(content)


def calculate_content_hash(content: str) -> str:
    """Calculate SHA256 hash of content for change detection"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def should_index_file(file_path: str, exclude_patterns: List[str], max_size_kb: int, file_extensions: List[str]) -> Tuple[bool, str]:
    """Determine if a file should be indexed based on configured rules"""
    
    # Check file extension
    file_ext = Path(file_path).suffix.lower()
    if file_ext not in file_extensions:
        return False, f"Extension {file_ext} not in allowed extensions"
    
    # Check exclude patterns
    for pattern in exclude_patterns:
        if pattern in file_path or Path(file_path).match(pattern):
            return False, f"Matches exclude pattern: {pattern}"
    
    # Check file size
    try:
        if os.path.exists(file_path):
            file_size_kb = os.path.getsize(file_path) / 1024
            if file_size_kb > max_size_kb:
                return False, f"File too large: {file_size_kb:.1f}KB > {max_size_kb}KB"
    except OSError:
        return False, "Cannot access file"
    
    return True, "File meets indexing criteria"