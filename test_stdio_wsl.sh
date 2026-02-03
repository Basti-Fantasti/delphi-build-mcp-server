#!/bin/bash
# Test script for Delphi Build MCP Server - stdio via WSL Interop
#
# Tests that the MCP server works when launched from WSL using the
# Windows Python binary (WSL interop). This is the simplest way to
# use the Delphi MCP server from WSL -- no HTTP server needed.
#
# Usage (run from WSL or Git Bash):
#   ./test_stdio_wsl.sh [path-to-server-dir]
#
# Example:
#   ./test_stdio_wsl.sh /mnt/c/Users/Teufel/mcp-server/delphi-build-mcp-server
#
# The script auto-detects the server directory if run from within the repo.

set -e

# Determine server directory
if [ -n "$1" ]; then
    SERVER_DIR="$1"
elif [ -f "$(dirname "$0")/main.py" ]; then
    SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
else
    echo "[FAIL] Cannot find server directory."
    echo "       Run from the repo root or pass the path as argument:"
    echo "       ./test_stdio_wsl.sh /mnt/c/path/to/delphi-build-mcp-server"
    exit 1
fi

# Find the Python executable
PYTHON_EXE="${SERVER_DIR}/.venv/Scripts/python.exe"
MAIN_PY="${SERVER_DIR}/main.py"

# Fallback for non-Windows venv layout
if [ ! -f "${PYTHON_EXE}" ]; then
    PYTHON_EXE="${SERVER_DIR}/.venv/bin/python"
fi

echo "============================================"
echo " Delphi Build MCP Server - stdio Test"
echo " Python: ${PYTHON_EXE}"
echo " Server: ${MAIN_PY}"
echo "============================================"
echo ""

# Verify files exist
if [ ! -f "${PYTHON_EXE}" ]; then
    echo "[FAIL] Python not found at: ${PYTHON_EXE}"
    echo "       Make sure the .venv exists and was created on Windows."
    exit 1
fi

if [ ! -f "${MAIN_PY}" ]; then
    echo "[FAIL] main.py not found at: ${MAIN_PY}"
    exit 1
fi

# MCP stdio transport uses newline-delimited JSON-RPC.
# Each message is a single JSON object followed by a newline.

INIT_MSG='{"jsonrpc":"2.0","method":"initialize","params":{"capabilities":{},"clientInfo":{"name":"test-stdio-wsl","version":"1.0"},"protocolVersion":"2025-03-26"},"id":1}'
INITIALIZED_MSG='{"jsonrpc":"2.0","method":"notifications/initialized"}'
LIST_TOOLS_MSG='{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}'

echo "[1/3] Spawning server and sending initialize..."

RESPONSE=$(
    {
        echo "$INIT_MSG"
        sleep 1
        echo "$INITIALIZED_MSG"
        sleep 0.5
        echo "$LIST_TOOLS_MSG"
        sleep 1
    } | timeout 10 "${PYTHON_EXE}" "${MAIN_PY}" 2>/dev/null || true
)

if [ -z "${RESPONSE}" ]; then
    echo ""
    echo "[FAIL] No response received from server."
    echo "       Possible causes:"
    echo "       - WSL interop is disabled (check /etc/wsl.conf)"
    echo "       - The .venv was not created (run: uv venv && uv pip install -e .)"
    exit 1
fi

echo "[2/3] Checking initialize response..."

if echo "${RESPONSE}" | grep -q "delphi-build-server"; then
    echo "  [OK] Server identified as delphi-build-server"
else
    echo "  [FAIL] Server name not found in response"
fi

echo "[3/3] Checking tools/list response..."

TOOLS_OK=true
for tool in compile_delphi_project generate_config_from_build_log generate_config_from_multiple_build_logs extend_config_from_build_log; do
    if echo "${RESPONSE}" | grep -q "$tool"; then
        echo "  [OK] $tool"
    else
        echo "  [FAIL] $tool not found"
        TOOLS_OK=false
    fi
done

echo ""
if [ "$TOOLS_OK" = true ]; then
    echo "============================================"
    echo " All tests passed!"
    echo "============================================"
else
    echo "============================================"
    echo " Some tests failed - see above"
    echo "============================================"
    exit 1
fi
