#!/usr/bin/env python3
"""
env-audit MCP Server

Provides three tools for AI agents:
- env_audit_scan: Scan a project for environment variables
- env_audit_check: Check if all env vars are documented
- env_audit_add: Add a variable to .env.example

Install: pip install fastmcp
Run: python mcp_server.py
"""

from pathlib import Path
from typing import Optional
import json
import sys

# Import from main module
from env_audit import scan_directory, check_existing_env, run_check, guess_description, guess_example

# FastMCP is optional - tools work without it for testing
try:
    from fastmcp import FastMCP
    mcp = FastMCP("env-audit")
    HAS_MCP = True
except ImportError:
    mcp = None
    HAS_MCP = False
    
    # Dummy decorator when fastmcp not installed
    class DummyMCP:
        def tool(self):
            def decorator(f):
                return f
            return decorator
    mcp = DummyMCP()


@mcp.tool()
def env_audit_scan(path: str = ".") -> str:
    """
    Scan a codebase for environment variable references.
    
    Returns JSON with all found env vars, including:
    - name: Variable name
    - category: database, auth, api, cloud, email, logging, feature, general
    - files: List of files where the var is used
    - required: True if no default value found in code
    - sensitive: True if name contains SECRET, KEY, PASSWORD, TOKEN, etc.
    - default: Default value found in code (if any)
    
    Args:
        path: Directory to scan (default: current directory)
    """
    root = Path(path).resolve()
    
    if not root.exists():
        return json.dumps({"error": f"Path '{path}' does not exist"})
    
    vars_dict = scan_directory(root)
    existing = check_existing_env(root)
    
    # Add "documented" field
    for var_name, var_info in vars_dict.items():
        var_info['documented'] = var_name in existing
    
    result = {
        "path": str(root),
        "total": len(vars_dict),
        "documented": len(existing),
        "undocumented": len(vars_dict) - len(set(vars_dict.keys()) & existing),
        "variables": vars_dict
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def env_audit_check(path: str = ".") -> str:
    """
    Check if all environment variables are documented in .env.example.
    
    Returns JSON with:
    - passed: True if all vars are documented
    - missing: List of undocumented variable names with details
    - total: Total number of env vars found
    - documented: Number of documented vars
    
    Use this in CI to ensure env var documentation is up to date.
    
    Args:
        path: Directory to check (default: current directory)
    """
    root = Path(path).resolve()
    
    if not root.exists():
        return json.dumps({"error": f"Path '{path}' does not exist"})
    
    vars_dict = scan_directory(root)
    existing = check_existing_env(root)
    passed, missing_names = run_check(vars_dict, existing)
    
    # Build detailed missing list
    missing = []
    for var_name in missing_names:
        info = vars_dict[var_name]
        missing.append({
            "name": var_name,
            "required": info['required'],
            "sensitive": info['sensitive'],
            "files": info['files'][:3],
            "category": info['category'],
        })
    
    result = {
        "passed": passed,
        "total": len(vars_dict),
        "documented": len(existing),
        "missing_count": len(missing),
        "missing": missing
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def env_audit_add(
    path: str = ".",
    var: str = "",
    value: str = "",
    description: Optional[str] = None
) -> str:
    """
    Add a new environment variable to .env.example.
    
    If .env.example doesn't exist, creates it.
    If the variable already exists, returns an error.
    
    Args:
        path: Project directory (default: current directory)
        var: Variable name (e.g., "DATABASE_URL")
        value: Example value (e.g., "postgresql://...")
        description: Optional description (auto-generated if not provided)
    """
    if not var:
        return json.dumps({"error": "Variable name is required"})
    
    root = Path(path).resolve()
    env_example = root / ".env.example"
    
    # Check if var already exists
    existing = check_existing_env(root)
    if var in existing:
        return json.dumps({
            "error": f"Variable '{var}' already exists in .env.example",
            "action": "none"
        })
    
    # Generate description if not provided
    if not description:
        description = guess_description(var, "")
    
    # Generate value if not provided
    if not value:
        value = guess_example(var)
    
    # Build the entry
    entry = f"\n# {description}\n{var}={value}\n"
    
    # Append to file
    try:
        if env_example.exists():
            with open(env_example, 'a') as f:
                f.write(entry)
        else:
            header = "# Environment Variables\n# Generated by env-audit\n"
            with open(env_example, 'w') as f:
                f.write(header + entry)
        
        return json.dumps({
            "success": True,
            "action": "added",
            "variable": var,
            "value": value,
            "description": description,
            "file": str(env_example)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    """Run the MCP server."""
    if not HAS_MCP:
        print("Error: fastmcp not installed.", file=sys.stderr)
        print("Install with: pip install fastmcp", file=sys.stderr)
        print("\nYou can still use the tool functions directly:", file=sys.stderr)
        print("  from mcp_server import env_audit_scan, env_audit_check, env_audit_add", file=sys.stderr)
        sys.exit(1)
    mcp.run()


if __name__ == "__main__":
    main()
