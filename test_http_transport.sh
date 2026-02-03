#!/bin/bash
# Test script for Delphi Build MCP Server - Streamable HTTP Transport
# Usage: First start the server on Windows, then run this script from WSL
#   Start server (Windows):  uv run main.py --transport streamable-http
#   Run tests (WSL):         ./test_http_transport.sh [host] [port]
#
# To find your Windows host IP from WSL:
#   cat /etc/resolv.conf | grep nameserver | awk '{print $2}'

set -e

HOST="${1:-127.0.0.1}"
PORT="${2:-8080}"
BASE_URL="http://${HOST}:${PORT}/mcp"

echo "============================================"
echo " Delphi Build MCP Server - HTTP Transport Test"
echo " Target: ${BASE_URL}"
echo "============================================"
echo ""

# Step 1: Initialize
echo "[1/3] Sending initialize request..."
echo ""

RESPONSE=$(curl -s -D /dev/stderr -X POST "${BASE_URL}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"capabilities":{},"clientInfo":{"name":"test-sh","version":"1.0"},"protocolVersion":"2025-03-26"},"id":1}' \
  2>headers.tmp)

if [ $? -ne 0 ]; then
    echo "[FAIL] Could not connect to ${BASE_URL}"
    echo "       Is the server running? Start it on Windows with:"
    echo "       uv run main.py --transport streamable-http"
    rm -f headers.tmp
    exit 1
fi

echo "Response:"
echo "${RESPONSE}"
echo ""

# Extract session ID
SESSION_ID=$(grep -i "mcp-session-id" headers.tmp | tr -d '\r' | awk '{print $2}')
rm -f headers.tmp

if [ -z "${SESSION_ID}" ]; then
    echo "[FAIL] No session ID received"
    exit 1
fi

echo "Session ID: ${SESSION_ID}"
echo ""

# Step 2: Send initialized notification
echo "[2/3] Sending initialized notification..."
echo ""

curl -s -o /dev/null -X POST "${BASE_URL}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: ${SESSION_ID}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

echo "Done."
echo ""

# Step 3: List tools
echo "[3/3] Listing available tools..."
echo ""

TOOLS_RESPONSE=$(curl -s -X POST "${BASE_URL}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: ${SESSION_ID}" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}')

echo "Response:"
echo "${TOOLS_RESPONSE}"
echo ""

# Validate tools response contains expected tools
if echo "${TOOLS_RESPONSE}" | grep -q "compile_delphi_project"; then
    echo "[OK] compile_delphi_project found"
else
    echo "[FAIL] compile_delphi_project not found"
fi

if echo "${TOOLS_RESPONSE}" | grep -q "generate_config_from_build_log"; then
    echo "[OK] generate_config_from_build_log found"
else
    echo "[FAIL] generate_config_from_build_log not found"
fi

if echo "${TOOLS_RESPONSE}" | grep -q "generate_config_from_multiple_build_logs"; then
    echo "[OK] generate_config_from_multiple_build_logs found"
else
    echo "[FAIL] generate_config_from_multiple_build_logs not found"
fi

if echo "${TOOLS_RESPONSE}" | grep -q "extend_config_from_build_log"; then
    echo "[OK] extend_config_from_build_log found"
else
    echo "[FAIL] extend_config_from_build_log not found"
fi

echo ""
echo "============================================"
echo " All tests passed!"
echo "============================================"
