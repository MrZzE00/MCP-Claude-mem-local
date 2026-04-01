# Security Policy

## Trust Model

### MCP Server (stdio transport)

The MCP server (`src/server.py`) uses **stdio transport**, which is inherently trusted: the calling process (Claude Code) controls the pipe. No additional authentication is added at this layer.

**If the transport is changed to SSE or HTTP, authentication MUST be added.**

### REST API Server (`src/api_server.py`)

The REST API is protected by:

- **API Key authentication** (required by default via `REQUIRE_AUTH=true`)
- **Rate limiting** (configurable, in-memory)
- **CORS** restricted to localhost origins
- **Security headers** (CSP, X-Frame-Options, X-Content-Type-Options)
- **Localhost binding** by default (`127.0.0.1`)

#### Rate Limiting Caveat

The in-memory rate limiter can be bypassed via `X-Forwarded-For` header spoofing. For production deployments exposed beyond localhost, use a reverse proxy (nginx, Caddy) with proper rate limiting.

### Database

- The PostgreSQL user `claude` runs with **least-privilege permissions** (SELECT, INSERT, UPDATE, DELETE only)
- **Row Level Security (RLS)** isolates memories by `user_id`
- All queries use **parameterized statements** (no SQL injection)
- Extensions (pgvector, pg_trgm) are created by the `postgres` superuser during init

### Ollama

- `OLLAMA_HOST` is validated to only allow `localhost` or `127.0.0.1` to prevent SSRF
- The Ollama installer on Linux is downloaded and validated before execution (no pipe-to-shell)

## Configuration

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PG_PASSWORD` | Yes | PostgreSQL password |
| `API_KEY` | Yes (when `REQUIRE_AUTH=true`) | API authentication key |
| `REQUIRE_AUTH` | No (default: `true`) | Set to `false` only for local development |

### File Permissions

- `.env` files should have `chmod 600` (owner-only read/write)
- The install script sets this automatically

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it privately:

1. **Do NOT** open a public GitHub issue
2. Email the maintainers or use GitHub's private vulnerability reporting
3. Include steps to reproduce and potential impact

We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

## Audit History

| Date | Scope | Method | Result |
|------|-------|--------|--------|
| 2026-03-31 | Full codebase (~4266 lines, 35 files) | 5 parallel security agents | MEDIUM risk — 38 findings addressed |
