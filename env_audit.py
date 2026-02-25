#!/usr/bin/env python3
"""
env-audit: Scan a codebase and generate documented .env.example

Scans source files for environment variable references and produces
a clean, documented template with categories and descriptions.

Features:
- Multi-language support (Python, Node, Go, Rust, Ruby, Shell, Docker)
- Smart extraction of default values
- Required vs optional detection
- Sensitive variable marking
- Multiple output formats (env, json, typescript, zod)
- CI-friendly --check mode
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional

# Patterns to find env var references WITH default value extraction
# Each tuple: (pattern, language, default_value_group_index_or_None)
PATTERNS = [
    # Python: os.environ.get("VAR", "default"), os.getenv("VAR", "default")
    (r'os\.environ\.get\(["\']([A-Z][A-Z0-9_]*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?\)', 'python', 2),
    (r'os\.getenv\(["\']([A-Z][A-Z0-9_]*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?\)', 'python', 2),
    (r'os\.environ\[["\']([A-Z][A-Z0-9_]*)["\']', 'python', None),
    
    # Node.js: process.env.VAR || "default", process.env.VAR ?? "default"
    (r'process\.env\.([A-Z][A-Z0-9_]*)\s*(?:\|\||&&|\?\?)\s*["\']([^"\']*)["\']', 'javascript', 2),
    (r'process\.env\.([A-Z][A-Z0-9_]*)', 'javascript', None),
    (r'process\.env\[["\']([A-Z][A-Z0-9_]*)["\']', 'javascript', None),
    
    # Go: os.Getenv("VAR")
    (r'os\.Getenv\(["\']([A-Z][A-Z0-9_]*)["\']', 'go', None),
    
    # Rust: std::env::var("VAR"), env::var("VAR")
    (r'env::var\(["\']([A-Z][A-Z0-9_]*)["\']', 'rust', None),
    
    # Ruby: ENV["VAR"] || "default", ENV.fetch("VAR", "default")
    (r'ENV\[["\']([A-Z][A-Z0-9_]*)["\']\]\s*\|\|\s*["\']([^"\']*)["\']', 'ruby', 2),
    (r'ENV\.fetch\(["\']([A-Z][A-Z0-9_]*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?\)', 'ruby', 2),
    (r'ENV\[["\']([A-Z][A-Z0-9_]*)["\']', 'ruby', None),
    
    # Shell/Bash: ${VAR:-default}, ${VAR:=default}
    (r'\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}', 'shell', 2),
    (r'\$\{([A-Z][A-Z0-9_]*):=([^}]*)\}', 'shell', 2),
    (r'\$\{?([A-Z][A-Z0-9_]*)\}?', 'shell', None),
    
    # Generic: env("VAR", "default"), getEnv("VAR")
    (r'(?:get)?[Ee]nv\(["\']([A-Z][A-Z0-9_]*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?\)', 'generic', 2),
    
    # Docker/docker-compose
    (r'^\s*-?\s*([A-Z][A-Z0-9_]*)=([^\s]*)', 'docker', 2),
    (r'\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}', 'docker', 2),
    (r'\$\{([A-Z][A-Z0-9_]*)', 'docker', None),
]

# File extensions to scan
SCAN_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.rb',
    '.sh', '.bash', '.zsh', '.env', '.env.example', '.env.local',
    '.yaml', '.yml', '.json', '.toml', '.ini', '.conf',
    '.dockerfile', '.docker-compose.yml', '.docker-compose.yaml',
}

# Directories to skip
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.next', 'target', 'vendor', '.cargo',
}

# Additional dirs to skip when --no-scripts is used
SCRIPT_DIRS = {'scripts', 'script', 'test', 'tests', '__tests__', 'spec', 'e2e'}

# Common env var categories
CATEGORIES = {
    'database': ['DATABASE', 'DB_', 'POSTGRES', 'MYSQL', 'MONGO', 'REDIS', 'SQL'],
    'auth': ['AUTH', 'JWT', 'SECRET', 'TOKEN', 'PASSWORD', 'API_KEY', 'OAUTH', 'SESSION', 'CREDENTIAL'],
    'api': ['API_', 'ENDPOINT', 'URL', 'HOST', 'PORT', 'BASE_URL'],
    'cloud': ['AWS_', 'GCP_', 'AZURE_', 'S3_', 'CLOUD'],
    'email': ['SMTP', 'EMAIL', 'MAIL', 'SENDGRID', 'SES_'],
    'logging': ['LOG_', 'DEBUG', 'SENTRY', 'NEWRELIC'],
    'feature': ['FEATURE_', 'ENABLE_', 'DISABLE_', 'FLAG_'],
}

# Keywords that indicate sensitive variables
SENSITIVE_KEYWORDS = {'SECRET', 'KEY', 'PASSWORD', 'TOKEN', 'CREDENTIAL', 'PRIVATE', 'AUTH'}

# Shell built-ins and common false positives to skip
SKIP_VARS = {
    'HOME', 'PATH', 'USER', 'SHELL', 'PWD', 'TERM', 'LANG', 'LC_ALL',
    'BASH_SOURCE', 'BASH_LINENO', 'FUNCNAME', 'LINENO', 'RANDOM', 'SECONDS',
    'IFS', 'PS1', 'PS2', 'PS4', 'OLDPWD', 'HOSTNAME', 'HOSTTYPE', 'OSTYPE',
    'UID', 'EUID', 'GROUPS', 'PPID', 'SHELLOPTS', 'BASHOPTS',
    # Color codes in scripts
    'RED', 'GREEN', 'YELLOW', 'BLUE', 'PURPLE', 'CYAN', 'WHITE', 'NC', 'RESET', 'BOLD',
    # Common script variables
    'SCRIPT_DIR', 'PROJECT_ROOT', 'DIR', 'ROOT', 'BASE_DIR',
}


def is_sensitive(var_name: str) -> bool:
    """Check if a variable name indicates sensitive data."""
    var_upper = var_name.upper()
    return any(kw in var_upper for kw in SENSITIVE_KEYWORDS)


def categorize_var(var_name: str) -> str:
    """Categorize an env var based on its name."""
    var_upper = var_name.upper()
    for category, prefixes in CATEGORIES.items():
        for prefix in prefixes:
            if prefix in var_upper:
                return category
    return 'general'


def guess_description(var_name: str, context: str) -> str:
    """Generate a description based on var name and context."""
    descriptions = {
        'DATABASE_URL': 'Database connection string',
        'DB_HOST': 'Database host address',
        'DB_PORT': 'Database port number',
        'DB_USER': 'Database username',
        'DB_PASSWORD': 'Database password',
        'DB_NAME': 'Database name',
        'REDIS_URL': 'Redis connection URL',
        'API_KEY': 'API key for authentication',
        'SECRET_KEY': 'Application secret key',
        'JWT_SECRET': 'JWT signing secret',
        'PORT': 'Server port number',
        'HOST': 'Server host address',
        'NODE_ENV': 'Node.js environment (development/production)',
        'DEBUG': 'Enable debug mode',
        'LOG_LEVEL': 'Logging level (debug/info/warn/error)',
    }
    
    if var_name in descriptions:
        return descriptions[var_name]
    
    # Generate from name
    words = var_name.replace('_', ' ').title()
    return f'{words} configuration'


def guess_example(var_name: str, default_value: Optional[str] = None) -> str:
    """Guess an example value for the env var."""
    # If we found a default value in code, use it
    if default_value:
        return default_value
    
    examples = {
        'DATABASE_URL': 'postgresql://user:pass@localhost:5432/dbname',
        'REDIS_URL': 'redis://localhost:6379',
        'PORT': '3000',
        'HOST': 'localhost',
        'NODE_ENV': 'development',
        'DEBUG': 'false',
        'LOG_LEVEL': 'info',
    }
    
    var_upper = var_name.upper()
    
    if var_name in examples:
        return examples[var_name]
    if 'URL' in var_upper:
        return 'https://example.com'
    if 'PORT' in var_upper:
        return '8080'
    if 'HOST' in var_upper:
        return 'localhost'
    if 'KEY' in var_upper or 'SECRET' in var_upper or 'TOKEN' in var_upper:
        return 'your-secret-here'
    if 'PASSWORD' in var_upper:
        return 'your-password'
    if 'USER' in var_upper or 'NAME' in var_upper:
        return 'your-username'
    if 'EMAIL' in var_upper:
        return 'user@example.com'
    if 'DEBUG' in var_upper or 'ENABLE' in var_upper:
        return 'false'
    
    return ''


def scan_file(filepath: Path) -> Dict[str, Dict]:
    """Scan a file for env var references. Returns {var: {occurrences, default, ...}}."""
    results = {}
    
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return results
    
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        for pattern, lang, default_group in PATTERNS:
            for match in re.finditer(pattern, line):
                var_name = match.group(1)
                
                # Skip very short names or common false positives
                if len(var_name) < 3:
                    continue
                if var_name in SKIP_VARS:
                    continue
                
                # Extract default value if pattern supports it
                default_value = None
                if default_group and len(match.groups()) >= default_group:
                    raw_default = match.group(default_group)
                    # Skip shell command substitutions as defaults
                    if raw_default and not raw_default.startswith('$(') and not raw_default.startswith('`'):
                        default_value = raw_default
                
                if var_name not in results:
                    results[var_name] = {
                        'occurrences': [],
                        'default': None,
                    }
                
                results[var_name]['occurrences'].append((line_num, line.strip()[:100]))
                
                # Keep the first non-None default value found
                if default_value and results[var_name]['default'] is None:
                    results[var_name]['default'] = default_value
    
    return results


def scan_directory(root: Path, skip_scripts: bool = False) -> Dict[str, Dict]:
    """Scan a directory for all env var references."""
    all_vars = {}
    
    skip_set = SKIP_DIRS | (SCRIPT_DIRS if skip_scripts else set())
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored directories
        dirnames[:] = [d for d in dirnames if d not in skip_set]
        
        for filename in filenames:
            filepath = Path(dirpath) / filename
            
            # Check extension or special filenames
            ext = filepath.suffix.lower()
            if ext not in SCAN_EXTENSIONS and not filename.startswith('.env'):
                # Also check dockerfile and compose files
                if 'dockerfile' not in filename.lower() and 'compose' not in filename.lower():
                    continue
            
            file_vars = scan_file(filepath)
            
            for var_name, var_data in file_vars.items():
                if var_name not in all_vars:
                    all_vars[var_name] = {
                        'name': var_name,
                        'category': categorize_var(var_name),
                        'files': [],
                        'occurrences': 0,
                        'context': '',
                        'default': None,
                        'required': True,  # Will be set to False if default found
                        'sensitive': is_sensitive(var_name),
                    }
                
                rel_path = filepath.relative_to(root)
                all_vars[var_name]['files'].append(str(rel_path))
                all_vars[var_name]['occurrences'] += len(var_data['occurrences'])
                
                # Update default value (first found wins)
                if var_data['default'] and all_vars[var_name]['default'] is None:
                    all_vars[var_name]['default'] = var_data['default']
                    all_vars[var_name]['required'] = False
                
                # Store first context
                if var_data['occurrences'] and not all_vars[var_name]['context']:
                    all_vars[var_name]['context'] = var_data['occurrences'][0][1]
    
    return all_vars


def check_existing_env(root: Path) -> Set[str]:
    """Check for existing .env files and extract already-defined vars."""
    defined = set()
    
    for env_file in ['.env', '.env.local', '.env.example', '.env.development']:
        filepath = root / env_file
        if filepath.exists():
            try:
                for line in filepath.read_text().split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        var_name = line.split('=')[0].strip()
                        defined.add(var_name)
            except Exception:
                pass
    
    return defined


def generate_env_example(vars_dict: Dict[str, Dict], existing: Set[str]) -> str:
    """Generate a documented .env.example file."""
    output = []
    output.append("# Environment Variables")
    output.append("# Generated by env-audit")
    output.append("# https://github.com/indiekitai/env-audit")
    output.append("")
    
    # Group by category
    by_category = defaultdict(list)
    for var_info in vars_dict.values():
        by_category[var_info['category']].append(var_info)
    
    # Sort categories
    category_order = ['database', 'auth', 'api', 'cloud', 'email', 'logging', 'feature', 'general']
    
    for category in category_order:
        if category not in by_category:
            continue
        
        vars_list = sorted(by_category[category], key=lambda x: x['name'])
        
        output.append(f"# {'=' * 50}")
        output.append(f"# {category.upper()}")
        output.append(f"# {'=' * 50}")
        output.append("")
        
        for var_info in vars_list:
            name = var_info['name']
            desc = guess_description(name, var_info['context'])
            example = guess_example(name, var_info['default'])
            
            # Build status indicators
            status_parts = []
            if name in existing:
                status_parts.append("already defined")
            if var_info['sensitive']:
                status_parts.append("sensitive")
            if not var_info['required']:
                status_parts.append(f"optional, default: {var_info['default']}")
            elif var_info['required']:
                status_parts.append("required")
            
            status = f" ({', '.join(status_parts)})" if status_parts else ""
            
            output.append(f"# {desc}{status}")
            output.append(f"# Found in: {', '.join(var_info['files'][:3])}")
            if len(var_info['files']) > 3:
                output.append(f"#   ...and {len(var_info['files']) - 3} more files")
            output.append(f"{name}={example}")
            output.append("")
    
    return '\n'.join(output)


def generate_typescript(vars_dict: Dict[str, Dict]) -> str:
    """Generate TypeScript type declarations for env vars."""
    output = []
    output.append("// Environment variable types")
    output.append("// Generated by env-audit")
    output.append("// https://github.com/indiekitai/env-audit")
    output.append("")
    output.append("declare namespace NodeJS {")
    output.append("  interface ProcessEnv {")
    
    for var_info in sorted(vars_dict.values(), key=lambda x: x['name']):
        name = var_info['name']
        required = var_info['required']
        sensitive = var_info['sensitive']
        desc = guess_description(name, var_info['context'])
        
        # Add JSDoc comment
        comments = [desc]
        if sensitive:
            comments.append("@sensitive")
        if not required:
            comments.append(f"@default {var_info['default']}")
        
        output.append(f"    /** {' | '.join(comments)} */")
        
        # Optional vars get `?`
        optional = "?" if not required else ""
        output.append(f"    {name}{optional}: string;")
    
    output.append("  }")
    output.append("}")
    output.append("")
    output.append("export {};")
    
    return '\n'.join(output)


def generate_zod(vars_dict: Dict[str, Dict]) -> str:
    """Generate Zod schema for env var validation."""
    output = []
    output.append("// Environment variable validation schema")
    output.append("// Generated by env-audit")
    output.append("// https://github.com/indiekitai/env-audit")
    output.append("")
    output.append("import { z } from 'zod';")
    output.append("")
    output.append("export const envSchema = z.object({")
    
    for var_info in sorted(vars_dict.values(), key=lambda x: x['name']):
        name = var_info['name']
        required = var_info['required']
        default = var_info['default']
        desc = guess_description(name, var_info['context'])
        
        # Build zod chain
        chain = "z.string()"
        if not required and default:
            chain += f'.default("{default}")'
        elif not required:
            chain += '.optional()'
        
        # Add description
        chain += f'.describe("{desc}")'
        
        output.append(f"  {name}: {chain},")
    
    output.append("});")
    output.append("")
    output.append("export type Env = z.infer<typeof envSchema>;")
    output.append("")
    output.append("// Usage: const env = envSchema.parse(process.env);")
    
    return '\n'.join(output)


def run_check(vars_dict: Dict[str, Dict], existing: Set[str]) -> Tuple[bool, List[str]]:
    """Check if all env vars are documented. Returns (passed, missing_vars)."""
    found_vars = set(vars_dict.keys())
    missing = found_vars - existing
    
    # Filter to only required vars for stricter check? 
    # For now, report all missing vars
    return len(missing) == 0, sorted(missing)


def main():
    parser = argparse.ArgumentParser(
        description='Scan a codebase for environment variables and generate .env.example'
    )
    parser.add_argument('path', nargs='?', default='.', help='Path to scan (default: current directory)')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    parser.add_argument('--check', action='store_true', help='Check mode: exit 1 if undocumented vars exist')
    parser.add_argument('--format', choices=['env', 'typescript', 'zod'], default='env',
                        help='Output format (default: env)')
    parser.add_argument('--no-scripts', action='store_true',
                        help='Skip scripts/, test/, tests/ directories')
    
    args = parser.parse_args()
    root = Path(args.path).resolve()
    
    if not root.exists():
        print(f"Error: Path '{root}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Suppress info messages in check mode or json mode
    quiet = args.check or args.json
    
    if not quiet:
        print(f"Scanning {root}...", file=sys.stderr)
    
    vars_dict = scan_directory(root, skip_scripts=args.no_scripts)
    existing = check_existing_env(root)
    
    if not quiet:
        print(f"Found {len(vars_dict)} environment variables", file=sys.stderr)
        print(f"Already defined: {len(existing)}", file=sys.stderr)
        
        # Summary of required/optional/sensitive
        required_count = sum(1 for v in vars_dict.values() if v['required'])
        sensitive_count = sum(1 for v in vars_dict.values() if v['sensitive'])
        print(f"Required: {required_count}, Optional: {len(vars_dict) - required_count}, Sensitive: {sensitive_count}", file=sys.stderr)
    
    # Check mode
    if args.check:
        passed, missing = run_check(vars_dict, existing)
        if not passed:
            print(f"❌ Found {len(missing)} undocumented environment variables:", file=sys.stderr)
            for var in missing:
                info = vars_dict[var]
                req = "required" if info['required'] else "optional"
                sens = ", sensitive" if info['sensitive'] else ""
                print(f"  - {var} ({req}{sens}) in {', '.join(info['files'][:2])}", file=sys.stderr)
            print(f"\nRun 'env-audit -o .env.example' to generate documentation.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"✅ All {len(vars_dict)} environment variables are documented.", file=sys.stderr)
            sys.exit(0)
    
    # Stats only mode
    if args.stats:
        by_category = defaultdict(int)
        for var_info in vars_dict.values():
            by_category[var_info['category']] += 1
        
        print("\nBy category:")
        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")
        
        print("\nRequired variables:")
        for var_info in sorted(vars_dict.values(), key=lambda x: x['name']):
            if var_info['required']:
                sens = " [SENSITIVE]" if var_info['sensitive'] else ""
                print(f"  {var_info['name']}{sens}")
        return
    
    # Generate output based on format
    if args.json:
        output = json.dumps(vars_dict, indent=2)
    elif args.format == 'typescript':
        output = generate_typescript(vars_dict)
    elif args.format == 'zod':
        output = generate_zod(vars_dict)
    else:
        output = generate_env_example(vars_dict, existing)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
