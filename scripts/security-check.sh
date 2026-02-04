#!/bin/bash
# Security verification script for Claude Memory Local
# Run this after applying security fixes

set -e

echo "=========================================="
echo "Claude Memory Local - Security Verification"
echo "=========================================="
echo ""

ERRORS=0

# Check 1: .env not in git
echo "[1/8] Checking .env is gitignored..."
if git ls-files --error-unmatch .env 2>/dev/null; then
    echo "  ❌ FAIL: .env is tracked by git! Remove it with: git rm --cached .env"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✅ PASS: .env is not tracked"
fi

# Check 2: No hardcoded passwords
echo ""
echo "[2/8] Checking for hardcoded passwords..."
if grep -rn "claudelocal123\|synaptic123" --include="*.py" src/ plugins/ 2>/dev/null; then
    echo "  ❌ FAIL: Found hardcoded default passwords!"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✅ PASS: No hardcoded passwords found"
fi

# Check 3: CORS not wildcard
echo ""
echo "[3/8] Checking CORS configuration..."
if grep -n 'allow_origins=\["\*"\]' src/api_server.py 2>/dev/null; then
    echo "  ❌ FAIL: CORS allows all origins!"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✅ PASS: CORS is restricted"
fi

# Check 4: Localhost binding
echo ""
echo "[4/8] Checking server binding..."
if grep -n 'host="0.0.0.0"' src/api_server.py 2>/dev/null; then
    echo "  ❌ FAIL: Server binds to 0.0.0.0!"
    ERRORS=$((ERRORS + 1))
else
    echo "  ✅ PASS: Server binds to localhost"
fi

# Check 5: Rate limiting present
echo ""
echo "[5/8] Checking rate limiting..."
if grep -q "RateLimitMiddleware" src/api_server.py 2>/dev/null; then
    echo "  ✅ PASS: Rate limiting is implemented"
else
    echo "  ❌ FAIL: No rate limiting found!"
    ERRORS=$((ERRORS + 1))
fi

# Check 6: Security headers present
echo ""
echo "[6/8] Checking security headers..."
if grep -q "SecurityHeadersMiddleware" src/api_server.py 2>/dev/null; then
    echo "  ✅ PASS: Security headers middleware found"
else
    echo "  ❌ FAIL: No security headers middleware!"
    ERRORS=$((ERRORS + 1))
fi

# Check 7: API key authentication
echo ""
echo "[7/8] Checking API authentication..."
if grep -q "verify_api_key" src/api_server.py 2>/dev/null; then
    echo "  ✅ PASS: API key verification is implemented"
else
    echo "  ⚠️  WARN: API key verification not found"
fi

# Check 8: SSRF protection
echo ""
echo "[8/8] Checking SSRF protection..."
if grep -q "ALLOWED_OLLAMA_HOSTS" src/api_server.py 2>/dev/null; then
    echo "  ✅ PASS: OLLAMA_HOST validation found"
else
    echo "  ❌ FAIL: No SSRF protection!"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo "✅ All security checks passed!"
else
    echo "❌ $ERRORS security issue(s) found"
    echo "Please fix the issues above before deploying."
    exit 1
fi
echo "=========================================="

# Optional: Run security scanners if available
echo ""
echo "Optional: Running security scanners..."

if command -v bandit &> /dev/null; then
    echo ""
    echo "Running Bandit..."
    bandit -r src/ plugins/ -ll --quiet || true
else
    echo "  ⚠️  Bandit not installed. Install with: pip install bandit"
fi

if command -v safety &> /dev/null; then
    echo ""
    echo "Running Safety check..."
    safety check --file requirements.txt 2>/dev/null || echo "  ⚠️  Safety check requires a Safety account"
else
    echo "  ⚠️  Safety not installed. Install with: pip install safety"
fi

echo ""
echo "Done!"
