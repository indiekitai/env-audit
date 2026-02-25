# env-audit

Scan a codebase for environment variables and generate a documented `.env.example`.

## The Problem

Every project has environment variables. Few have documentation. You join a project, clone the repo, and then spend 30 minutes hunting through code to figure out what env vars you need.

env-audit fixes this in one command.

## Features

- 🔍 **Multi-language scanning** - Python, Node, Go, Rust, Ruby, Shell, Docker
- 🧠 **Smart extraction** - Finds default values, marks required vs optional
- 🔒 **Sensitive detection** - Flags SECRET, KEY, PASSWORD, TOKEN vars
- ✅ **CI-friendly** - `--check` mode for automated verification
- 📝 **Multiple formats** - .env, TypeScript types, Zod schemas
- 🤖 **MCP Server** - Agent-friendly tools for Claude, Cursor, etc.

## Quick Start

```bash
# Scan current directory
python env_audit.py

# Scan a specific path
python env_audit.py /path/to/project

# Save to file
python env_audit.py -o .env.example

# Get JSON output (for tooling)
python env_audit.py --json > env-vars.json

# Just show stats
python env_audit.py --stats
```

## CI Integration

Use `--check` mode to fail CI if there are undocumented env vars:

```bash
# In your CI pipeline
python env_audit.py --check

# Exit codes:
# 0 = all vars documented
# 1 = undocumented vars found
```

Example GitHub Actions workflow:

```yaml
- name: Check env vars are documented
  run: python env_audit.py --check
```

## Output Formats

### Default (.env.example)

```bash
python env_audit.py -o .env.example
```

Generates:
```bash
# Database connection string (required, sensitive)
# Found in: src/db/connect.py, src/models/user.py
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Server port number (optional, default: 3000)
# Found in: src/server.py
PORT=3000
```

### TypeScript Types

```bash
python env_audit.py --format=typescript -o env.d.ts
```

Generates:
```typescript
declare namespace NodeJS {
  interface ProcessEnv {
    /** Database connection string | @sensitive */
    DATABASE_URL: string;
    /** Server port number | @default 3000 */
    PORT?: string;
  }
}
```

### Zod Schema

```bash
python env_audit.py --format=zod -o envSchema.ts
```

Generates:
```typescript
import { z } from 'zod';

export const envSchema = z.object({
  DATABASE_URL: z.string().describe("Database connection string"),
  PORT: z.string().default("3000").describe("Server port number"),
});

export type Env = z.infer<typeof envSchema>;
```

## JSON Output

For tooling integration, use `--json`:

```bash
python env_audit.py --json
```

Returns:
```json
{
  "DATABASE_URL": {
    "name": "DATABASE_URL",
    "category": "database",
    "files": ["src/db.py", "src/models.py"],
    "occurrences": 5,
    "required": true,
    "sensitive": true,
    "default": null
  },
  "PORT": {
    "name": "PORT",
    "category": "api",
    "files": ["src/server.py"],
    "occurrences": 2,
    "required": false,
    "sensitive": false,
    "default": "3000"
  }
}
```

## MCP Server (for AI Agents)

env-audit includes an MCP server for integration with Claude, Cursor, and other AI tools.

### Setup

```bash
pip install fastmcp
```

### Add to Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "env-audit": {
      "command": "python",
      "args": ["/path/to/env-audit/mcp_server.py"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `env_audit_scan` | Scan a project for all env vars |
| `env_audit_check` | Check if all vars are documented |
| `env_audit_add` | Add a variable to .env.example |

### Example Usage

Claude or other agents can:

```
> What environment variables does this project need?
[uses env_audit_scan]

> Are all env vars documented?
[uses env_audit_check]

> Add STRIPE_SECRET_KEY to the env example
[uses env_audit_add]
```

## Supported Languages

| Language | Patterns |
|----------|----------|
| Python | `os.environ.get()`, `os.getenv()`, `os.environ[]` |
| Node.js | `process.env.VAR`, `process.env["VAR"]`, `process.env.VAR \|\| "default"` |
| Go | `os.Getenv()` |
| Rust | `std::env::var()`, `env::var()` |
| Ruby | `ENV[]`, `ENV.fetch()`, `ENV["VAR"] \|\| "default"` |
| Shell | `$VAR`, `${VAR}`, `${VAR:-default}` |
| Docker | `docker-compose.yml`, `Dockerfile` |

## Smart Detection

### Default Values

env-audit extracts default values from common patterns:

```python
# Python
os.getenv('PORT', '3000')  # → default: 3000

# Node.js
process.env.PORT || '3000'  # → default: 3000

# Shell
${PORT:-3000}  # → default: 3000
```

Variables with defaults are marked as **optional**.

### Sensitive Variables

Variables containing these keywords are flagged as sensitive:
- SECRET, KEY, PASSWORD, TOKEN, CREDENTIAL, PRIVATE, AUTH

### Categories

Variables are auto-categorized:
- **database**: DATABASE, DB_, POSTGRES, MYSQL, MONGO, REDIS
- **auth**: AUTH, JWT, SECRET, TOKEN, PASSWORD, API_KEY
- **api**: API_, ENDPOINT, URL, HOST, PORT
- **cloud**: AWS_, GCP_, AZURE_, S3_
- **email**: SMTP, EMAIL, MAIL, SENDGRID
- **logging**: LOG_, DEBUG, SENTRY
- **feature**: FEATURE_, ENABLE_, DISABLE_, FLAG_

## Installation

```bash
# pip (coming soon)
pip install env-audit

# Or just run directly
python env_audit.py /path/to/project

# With MCP server support
pip install fastmcp
```

## Why This Exists

Saw this pattern across many projects:
- New dev joins → spends hours figuring out env vars
- `.env.example` exists but is outdated
- Code has new env vars not in the template

This tool can be run in CI to catch undocumented env vars before they cause onboarding pain.

## License

MIT
