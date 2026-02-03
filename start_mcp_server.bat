@echo off
REM Delphi Build MCP Server - Auto-Start Script
REM
REM Starts the MCP server with Streamable HTTP transport in the background.
REM Place this file (or a shortcut to it) in your Windows Startup folder
REM to start the server automatically at logon:
REM   Win+R -> shell:startup -> paste shortcut here
REM
REM Configuration:
REM   - Edit the variables below to match your setup
REM   - Default: listens on 0.0.0.0:8080

set MCP_SERVER_DIR=%~dp0
set HOST=0.0.0.0
set PORT=8080

cd /d "%MCP_SERVER_DIR%"
start "Delphi MCP Server" /min uv run main.py --transport streamable-http --host %HOST% --port %PORT%
