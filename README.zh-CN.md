[English](README.md) | [中文](README.zh-CN.md)

# env-audit

扫描代码库中的环境变量，自动生成带文档的 `.env.example`。

## 痛点

每个项目都有环境变量，很少有文档说明。你加入一个项目，clone 仓库，然后花 30 分钟在代码里翻找到底需要哪些环境变量。

env-audit 一条命令解决这个问题。

## 功能

- 🔍 **多语言扫描** - Python、Node、Go、Rust、Ruby、Shell、Docker
- 🧠 **智能提取** - 发现默认值，标记必填与可选
- 🔒 **敏感检测** - 标记 SECRET、KEY、PASSWORD、TOKEN 变量
- ✅ **CI 友好** - `--check` 模式用于自动化验证
- 📝 **多种格式** - .env、TypeScript 类型、Zod Schema
- 🤖 **MCP Server** - Agent 友好的工具，支持 Claude、Cursor 等

## 快速开始

```bash
# 扫描当前目录
python env_audit.py

# 扫描指定路径
python env_audit.py /path/to/project

# 保存到文件
python env_audit.py -o .env.example

# JSON 输出（方便工具集成）
python env_audit.py --json > env-vars.json

# 仅显示统计
python env_audit.py --stats
```

## CI 集成

使用 `--check` 模式在有未文档化的环境变量时让 CI 失败：

```bash
python env_audit.py --check

# 退出码：
# 0 = 所有变量已文档化
# 1 = 发现未文档化的变量
```

GitHub Actions 示例：

```yaml
- name: Check env vars are documented
  run: python env_audit.py --check
```

## 输出格式

### 默认 (.env.example)

```bash
python env_audit.py -o .env.example
```

生成：
```bash
# 数据库连接字符串（必填，敏感）
# 出现在：src/db/connect.py, src/models/user.py
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# 服务器端口号（可选，默认：3000）
# 出现在：src/server.py
PORT=3000
```

### TypeScript 类型

```bash
python env_audit.py --format=typescript -o env.d.ts
```

### Zod Schema

```bash
python env_audit.py --format=zod -o envSchema.ts
```

## JSON 输出

```bash
python env_audit.py --json
```

## MCP Server（AI Agent 集成）

env-audit 内置 MCP Server，可与 Claude、Cursor 等 AI 工具集成。

### 配置

```bash
pip install fastmcp
```

### 添加到 Claude Desktop

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

### 可用工具

| 工具 | 描述 |
|------|------|
| `env_audit_scan` | 扫描项目中的所有环境变量 |
| `env_audit_check` | 检查所有变量是否已文档化 |
| `env_audit_add` | 向 .env.example 添加变量 |

## 支持的语言

| 语言 | 匹配模式 |
|------|----------|
| Python | `os.environ.get()`、`os.getenv()`、`os.environ[]` |
| Node.js | `process.env.VAR`、`process.env["VAR"]`、`process.env.VAR \|\| "default"` |
| Go | `os.Getenv()` |
| Rust | `std::env::var()`、`env::var()` |
| Ruby | `ENV[]`、`ENV.fetch()`、`ENV["VAR"] \|\| "default"` |
| Shell | `$VAR`、`${VAR}`、`${VAR:-default}` |
| Docker | `docker-compose.yml`、`Dockerfile` |

## 智能检测

### 默认值

env-audit 从常见模式中提取默认值：

```python
# Python
os.getenv('PORT', '3000')  # → 默认值：3000

# Node.js
process.env.PORT || '3000'  # → 默认值：3000

# Shell
${PORT:-3000}  # → 默认值：3000
```

有默认值的变量标记为**可选**。

### 敏感变量

包含以下关键词的变量会被标记为敏感：
- SECRET、KEY、PASSWORD、TOKEN、CREDENTIAL、PRIVATE、AUTH

### 自动分类

变量自动分类：
- **database**：DATABASE、DB_、POSTGRES、MYSQL、MONGO、REDIS
- **auth**：AUTH、JWT、SECRET、TOKEN、PASSWORD、API_KEY
- **api**：API_、ENDPOINT、URL、HOST、PORT
- **cloud**：AWS_、GCP_、AZURE_、S3_
- **email**：SMTP、EMAIL、MAIL、SENDGRID
- **logging**：LOG_、DEBUG、SENTRY
- **feature**：FEATURE_、ENABLE_、DISABLE_、FLAG_

## 为什么做这个

在很多项目中看到同样的问题：
- 新人加入 → 花几小时搞清楚需要哪些环境变量
- `.env.example` 存在但已过时
- 代码里有新的环境变量，模板里没有

这个工具可以在 CI 中运行，在未文档化的环境变量导致入职困难之前就捕获它们。

## 许可证

MIT
