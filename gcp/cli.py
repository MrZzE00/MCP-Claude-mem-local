#!/usr/bin/env python3
"""
GCP CLI utility for MCP-Claude-mem-local.
Provides IAP token generation, standard MCP stdio-to-HTTP proxy, and automated IDE configuration.
"""

import sys
import os
import json
import time
import subprocess
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Token Generation & Caching
# ─────────────────────────────────────────────────────────────────────────────

def get_iap_token(project_id: str) -> str:
    """
    Generates and returns an OIDC ID Token for the IAP OAuth Client Audience.
    Uses local cache to avoid slowing down IDE transactions.
    """
    cache_path = Path.home() / ".cache" / f"mcp_iap_token_{project_id}.json"
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
            if time.time() < cache.get("expires_at", 0):
                return cache["token"]
        except Exception:
            pass

    print(f"[*] Cache miss/expired. Fetching audience (IAP Client ID) from Secret Manager...", file=sys.stderr)
    try:
        res = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             "--secret=google-secret-id", f"--project={project_id}"],
            capture_output=True, text=True, timeout=15
        )
        if res.returncode != 0 or not res.stdout.strip():
            print(f"[-] [Error] Failed to fetch secret google-secret-id: {res.stderr.strip()}", file=sys.stderr)
            return ""
        audience = res.stdout.strip()
    except Exception as e:
        print(f"[-] [Error] Failed to execute gcloud secrets command: {e}", file=sys.stderr)
        return ""

    print(f"[*] Generating Google OIDC ID token for audience: {audience[:10]}...", file=sys.stderr)
    try:
        res = subprocess.run(
            ["gcloud", "auth", "print-identity-token", f"--audiences={audience}"],
            capture_output=True, text=True, timeout=15
        )
        
        token = ""
        if res.returncode != 0:
            err_output = res.stderr.strip()
            if "Invalid account type" in err_output or "Requires valid service account" in err_output:
                env_name = "prd" if "prod" in project_id else "dev"
                service_account = f"sa-mcp-claude-memory-{env_name}@{project_id}.iam.gserviceaccount.com"
                print(f"[*] User account detected. Attempting to impersonate service account: {service_account}...", file=sys.stderr)
                res_imp = subprocess.run(
                    ["gcloud", "auth", "print-identity-token",
                     f"--impersonate-service-account={service_account}",
                     f"--audiences={audience}",
                     "--include-email"],
                    capture_output=True, text=True, timeout=15
                )
                if res_imp.returncode == 0 and res_imp.stdout.strip():
                    token = res_imp.stdout.strip().splitlines()[-1]
                else:
                    print(f"[-] [Error] Failed to generate impersonated token: {res_imp.stderr.strip()}", file=sys.stderr)
                    return ""
            else:
                print(f"[-] [Error] Failed to generate identity token: {err_output}", file=sys.stderr)
                return ""
        else:
            token = res.stdout.strip()

        if not token:
            print("[-] [Error] Token output is empty", file=sys.stderr)
            return ""

        # Save token to cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "token": token,
            "expires_at": time.time() + 3000  # Cache for 50 minutes (Google tokens expire in 1 hour)
        }))
        print("[+] Token obtained successfully.", file=sys.stderr)
        return token
    except Exception as e:
        print(f"[-] [Error] Failed to execute gcloud print-identity-token: {e}", file=sys.stderr)
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# HTTP Request Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def make_http_request(url: str, path: str, method: str = "GET", body: dict = None, token: str = "") -> dict:
    """Performs an HTTP request to the remote FastAPI backend behind IAP."""
    headers = {
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        method=method,
        headers=headers,
        data=data
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"[-] [HTTP Error {e.code}] on {path}: {err_msg}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        if "certificate verify failed" in str(e):
            print("[!] [SSL Warning] Local SSL certificate verification failed. Retrying with unverified SSL context...", file=sys.stderr)
            import ssl
            context = ssl._create_unverified_context()
            try:
                with urllib.request.urlopen(req, timeout=30, context=context) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as retry_err:
                print(f"[-] [Connection Error] Failed to reach remote backend even with unverified SSL: {retry_err}", file=sys.stderr)
                raise
        else:
            print(f"[-] [Connection Error] Failed to reach remote backend: {e}", file=sys.stderr)
            raise
    except Exception as e:
        print(f"[-] [Connection Error] Failed to reach remote backend: {e}", file=sys.stderr)
        raise

# ─────────────────────────────────────────────────────────────────────────────
# MCP Stdio-to-HTTP Proxy loop
# ─────────────────────────────────────────────────────────────────────────────

def run_proxy(url: str, project_id: str):
    """
    Fires the standard stdio-to-HTTP proxy loop.
    Acts as a bridge translating stdio JSON-RPC requests (IDE) to remote IAP-protected HTTP calls.
    """
    print(f"[*] Starting MCP Stdio-to-HTTP Proxy for {url} in project {project_id}...", file=sys.stderr)
    
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(f"[-] [JSON Error] Failed to parse stdio input: {e}", file=sys.stderr)
            continue

        method = req.get("method")
        msg_id = req.get("id")

        # Skip replies for standard notifications (no id)
        if msg_id is None:
            continue

        try:
            if method == "initialize":
                reply = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": { "name": "mcp-claude-memory", "version": "1.0.20" }
                    }
                }
            elif method == "tools/list":
                token = get_iap_token(project_id)
                tools_res = make_http_request(url, "/mcp/tools", "GET", token=token)
                reply = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": tools_res
                    }
                }
            elif method == "tools/call":
                token = get_iap_token(project_id)
                params = req.get("params", {})
                call_body = {
                    "name": params.get("name"),
                    "arguments": params.get("arguments", {})
                }
                call_res = make_http_request(url, "/mcp/call", "POST", body=call_body, token=token)
                reply = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": call_res.get("result", [])
                    }
                }
            else:
                reply = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
        except Exception as e:
            reply = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal proxy error: {str(e)}"
                }
            }

        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()

# ─────────────────────────────────────────────────────────────────────────────
# Automated IDE Installation
# ─────────────────────────────────────────────────────────────────────────────

def run_install(url: str, project_id: str):
    """Integrates the MCP plugin directly into Antigravity's mcp_config.json."""
    config_path = Path.home() / ".gemini" / "antigravity-ide" / "mcp_config.json"
    if not config_path.parent.exists():
        print(f"[-] [Error] Antigravity IDE directory not found at: {config_path.parent}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reading current Antigravity MCP configuration from {config_path}...", file=sys.stderr)
    try:
        if config_path.exists():
            config = json.loads(config_path.read_text())
        else:
            config = {"mcpServers": {}}
    except Exception as e:
        print(f"[-] [Error] Failed to read or parse config file: {e}", file=sys.stderr)
        sys.exit(1)

    # Inject/Overwrite the new server entry
    mcp_servers = config.setdefault("mcpServers", {})
    cli_path = str(Path(__file__).resolve())
    
    mcp_servers["mcp-claude-memory-prd"] = {
        "command": "/usr/bin/python3",
        "args": [
            cli_path,
            "proxy",
            "--project", project_id,
            "--url", url
        ]
    }

    print(f"[*] Writing updated config file...", file=sys.stderr)
    try:
        config_path.write_text(json.dumps(config, indent=2))
        print(f"[+] Antigravity configuration updated successfully! Key added: 'mcp-claude-memory-prd'.", file=sys.stderr)
    except Exception as e:
        print(f"[-] [Error] Failed to write config file: {e}", file=sys.stderr)
        sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# CLI Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GCP CLI Helper for MCP-Claude-mem-local."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get-token
    p_token = sub.add_parser("get-token", help="Fetch a fresh IAP Identity Token")
    p_token.add_argument("--project", default="prod-ia-staffing", help="GCP Project ID")

    # proxy
    p_proxy = sub.add_parser("proxy", help="Run the stdio-to-HTTP IAP proxy gateway")
    p_proxy.add_argument("--project", default="prod-ia-staffing", help="GCP Project ID")
    p_proxy.add_argument("--url", default="https://gen-skillz.znk.io/mcp-claude-memory", help="Remote MCP service root URL")

    # install
    p_install = sub.add_parser("install", help="Automatically install the MCP server to Antigravity")
    p_install.add_argument("--project", default="prod-ia-staffing", help="GCP Project ID")
    p_install.add_argument("--url", default="https://gen-skillz.znk.io/mcp-claude-memory", help="Remote MCP service root URL")

    args = parser.parse_args()

    if args.command == "get-token":
        token = get_iap_token(args.project)
        if token:
            print(token)
        else:
            sys.exit(1)
    elif args.command == "proxy":
        run_proxy(args.url, args.project)
    elif args.command == "install":
        run_install(args.url, args.project)

if __name__ == "__main__":
    main()
