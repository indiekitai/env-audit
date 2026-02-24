#!/usr/bin/env python3
"""
env-audit: Scan a codebase and generate documented .env.example

Scans source files for environment variable references and produces
a clean, documented template with categories and descriptions.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Patterns to find env var references
PATTERNS = [
    # Python: os.environ.get("VAR"), os.getenv("VAR"), os.environ["VAR"]
    (r'os\.environ\.get\(["\']([A-Z][A-Z0-9_]*)["\']', 'python'),
    (r'os\.getenv\(["\']([A-Z][A-Z0-9_]*)["\']', 'python'),
    (r'os\.environ\[["\']([A-Z][A-Z0-9_]*)["\']', 'python'),
    # Node.js: process.env.VAR, process.env["VAR"]
    (r'process\.env\.([A-Z][A-Z0-9_]*)', 'javascript'),
    (r'process\.env\[["\']([A-Z][A-Z0-9_]*)["\']', 'javascript'),
    # Go: os.Getenv("VAR")
    (r'os\.Getenv\(["\']([A-Z][A-Z0-9_]*)["\']', 'go'),
    # Rust: std::env::var("VAR"), env::var("VAR")
    (r'env::var\(["\']([A-Z][A-Z0-9_]*)["\']', 'rust'),
    # Ruby: ENV["VAR"], ENV.fetch("VAR")
    (r'ENV\[["\']([A-Z][A-Z0-9_]*)["\']', 'ruby'),
    (r'ENV\.fetch\(["\']([A-Z][A-Z0-9_]*)["\']', 'ruby'),
    # Shell/Bash: $VAR, ${VAR}
    (r'\$\{?([A-Z][A-Z0-9_]*)\}?', 'shell'),
    # Generic: env("VAR"), getEnv("VAR")
    (r'(?:get)?[Ee]nv\(["\']([A-Z][A-Z0-9_]*)["\']', 'generic'),
    # Docker/docker-compose
    (r'^\s*-?\s*([A-Z][A-Z0-9_]*)=', 'docker'),
    (r'\$\{([A-Z][A-Z0-9_]*)', 'docker'),
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

# Common env var categories
CATEGORIES = {
    'database': ['DATABASE', 'DB_', 'POSTGRES', 'MYSQL', 'MONGO', 'REDIS', 'SQL'],
    'auth': ['AUTH', 'JWT', 'SECRET', 'TOKEN', 'PASSWORD', 'API_KEY', 'OAUTH', 'SESSION'],
    'api': ['API_', 'ENDPOINT', 'URL', 'HOST', 'PORT', 'BASE_URL'],
    'cloud': ['AWS_', 'GCP_', 'AZURE_', 'S3_', 'CLOUD'],
    'email': ['SMTP', 'EMAIL', 'MAIL', 'SENDGRID', 'SES_'],
    'logging': ['LOG_', 'DEBUG', 'SENTRY', 'NEWRELIC'],
    'feature': ['FEATURE_', 'ENABLE_', 'DISABLE_', 'FLAG_'],
}


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


def guess_example(var_name: str) -> str:
    """Guess an example value for the env var."""
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


def scan_file(filepath: Path) -> Dict[str, List[Tuple[int, str]]]:
    """Scan a file for env var references. Returns {var: [(line_num, context)]}."""
    results = defaultdict(list)
    
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return results
    
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        for pattern, lang in PATTERNS:
            for match in re.finditer(pattern, line):
                var_name = match.group(1)
                # Skip very short names or common false positives
                if len(var_name) < 3:
                    continue
                if var_name in {'HOME', 'PATH', 'USER', 'SHELL', 'PWD', 'TERM'}:
                    continue
                results[var_name].append((line_num, line.strip()[:100]))
    
    return results


def scan_directory(root: Path) -> Dict[str, Dict]:
    """Scan a directory for all env var references."""
    all_vars = {}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        
        for filename in filenames:
            filepath = Path(dirpath) / filename
            
            # Check extension or special filenames
            ext = filepath.suffix.lower()
            if ext not in SCAN_EXTENSIONS and not filename.startswith('.env'):
                # Also check dockerfile and compose files
                if 'dockerfile' not in filename.lower() and 'compose' not in filename.lower():
                    continue
            
            file_vars = scan_file(filepath)
            
            for var_name, occurrences in file_vars.items():
                if var_name not in all_vars:
                    all_vars[var_name] = {
                        'name': var_name,
                        'category': categorize_var(var_name),
                        'files': [],
                        'occurrences': 0,
                        'context': '',
                    }
                
                rel_path = filepath.relative_to(root)
                all_vars[var_name]['files'].append(str(rel_path))
                all_vars[var_name]['occurrences'] += len(occurrences)
                if occurrences and not all_vars[var_name]['context']:
                    all_vars[var_name]['context'] = occurrences[0][1]
    
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
            example = guess_example(name)
            
            status = ""
            if name in existing:
                status = " (already defined)"
            
            output.append(f"# {desc}{status}")
            output.append(f"# Found in: {', '.join(var_info['files'][:3])}")
            if len(var_info['files']) > 3:
                output.append(f"#   ...and {len(var_info['files']) - 3} more files")
            output.append(f"{name}={example}")
            output.append("")
    
    return '\n'.join(output)


def main():
    parser = argparse.ArgumentParser(
        description='Scan a codebase for environment variables and generate .env.example'
    )
    parser.add_argument('path', nargs='?', default='.', help='Path to scan (default: current directory)')
    parser.add_argument('-o', '--output', help='Output file (default: stdout)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    root = Path(args.path).resolve()
    
    if not root.exists():
        print(f"Error: Path '{root}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    print(f"Scanning {root}...", file=sys.stderr)
    
    vars_dict = scan_directory(root)
    existing = check_existing_env(root)
    
    print(f"Found {len(vars_dict)} environment variables", file=sys.stderr)
    print(f"Already defined: {len(existing)}", file=sys.stderr)
    
    if args.stats:
        by_category = defaultdict(int)
        for var_info in vars_dict.values():
            by_category[var_info['category']] += 1
        
        print("\nBy category:")
        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")
        return
    
    if args.json:
        import json
        output = json.dumps(vars_dict, indent=2)
    else:
        output = generate_env_example(vars_dict, existing)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
