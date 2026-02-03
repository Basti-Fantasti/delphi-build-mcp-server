@echo off
REM Test script for Delphi Build MCP Server - Streamable HTTP Transport
REM Usage: First start the server, then run this script
REM   Start server:  uv run main.py --transport streamable-http
REM   Run tests:     test_http_transport.bat [host] [port]

setlocal enabledelayedexpansion

set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1
set PORT=%2
if "%PORT%"=="" set PORT=8080
set BASE_URL=http://%HOST%:%PORT%/mcp

echo ============================================
echo  Delphi Build MCP Server - HTTP Transport Test
echo  Target: %BASE_URL%
echo ============================================
echo.

REM Step 1: Initialize
echo [1/3] Sending initialize request...
echo.

curl -s -D response_headers.tmp -o response_body.tmp -X POST %BASE_URL% ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json, text/event-stream" ^
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"params\":{\"capabilities\":{},\"clientInfo\":{\"name\":\"test-bat\",\"version\":\"1.0\"},\"protocolVersion\":\"2025-03-26\"},\"id\":1}"

if %ERRORLEVEL% neq 0 (
    echo [FAIL] Could not connect to %BASE_URL%
    echo        Is the server running? Start it with:
    echo        uv run main.py --transport streamable-http
    goto :cleanup
)

echo Response:
type response_body.tmp
echo.
echo.

REM Extract session ID from headers
for /f "tokens=2 delims= " %%a in ('findstr /i "mcp-session-id" response_headers.tmp') do (
    set SESSION_ID=%%a
)
REM Remove trailing carriage return
set SESSION_ID=%SESSION_ID: =%

if "%SESSION_ID%"=="" (
    echo [FAIL] No session ID received
    goto :cleanup
)

echo Session ID: %SESSION_ID%
echo.

REM Step 2: Send initialized notification
echo [2/3] Sending initialized notification...
echo.

curl -s -o nul -X POST %BASE_URL% ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json, text/event-stream" ^
  -H "mcp-session-id: %SESSION_ID%" ^
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"

echo Done.
echo.

REM Step 3: List tools
echo [3/3] Listing available tools...
echo.

curl -s -o response_body.tmp -X POST %BASE_URL% ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json, text/event-stream" ^
  -H "mcp-session-id: %SESSION_ID%" ^
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/list\",\"params\":{},\"id\":2}"

echo Response:
type response_body.tmp
echo.
echo.

echo ============================================
echo  [OK] All tests passed!
echo ============================================

:cleanup
if exist response_headers.tmp del response_headers.tmp
if exist response_body.tmp del response_body.tmp
endlocal
