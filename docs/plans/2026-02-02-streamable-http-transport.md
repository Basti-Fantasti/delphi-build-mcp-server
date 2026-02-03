# Streamable HTTP Transport Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Streamable HTTP transport to the Delphi Build MCP Server so it can be accessed over TCP/IP from WSL-Ubuntu, while keeping stdio as the default for local use.

**Architecture:** CLI argument parsing via `argparse` selects between `stdio` (default, unchanged) and `streamable-http` transport. The HTTP mode uses the MCP SDK's `StreamableHTTPSessionManager` with a Starlette app served by uvicorn on `0.0.0.0:8080`. No new dependencies required -- `uvicorn`, `starlette`, and `anyio` are already transitive deps of the `mcp` package.

**Tech Stack:** Python 3.10+, MCP SDK 1.21.x, Starlette, uvicorn, argparse

---

### Task 1: Add CLI argument parsing and Streamable HTTP transport to main.py

**Files:**
- Modify: `main.py`

**Step 1: Add argparse imports and argument parsing**

Add `argparse` import and a `parse_args()` function at the top of `main.py`:

```python
import argparse

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Delphi Build MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0, only used with streamable-http)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080, only used with streamable-http)",
    )
    return parser.parse_args()
```

**Step 2: Add Streamable HTTP runner function**

Add a new `run_streamable_http()` function that sets up the Starlette app with `StreamableHTTPSessionManager`:

```python
import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

async def run_streamable_http(host: str, port: int) -> None:
    """Run the MCP server with Streamable HTTP transport."""
    import uvicorn

    session_manager = StreamableHTTPSessionManager(app=app)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[
            Mount("/mcp", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
```

**Step 3: Update main() to dispatch based on transport argument**

Replace the existing `main()` with:

```python
async def main():
    """Main entry point for the MCP server."""
    args = parse_args()

    if args.transport == "streamable-http":
        await run_streamable_http(args.host, args.port)
    else:
        # Run the server using stdio transport (default, unchanged behavior)
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
```

**Step 4: Verify stdio mode still works (no regression)**

Run: `uv run main.py --help`
Expected: Shows help with `--transport`, `--host`, `--port` options.

Run: `echo '{}' | timeout 3 uv run main.py 2>&1 || true`
Expected: Server starts in stdio mode (default), same as before.

**Step 5: Verify streamable-http mode starts**

Run: `timeout 5 uv run main.py --transport streamable-http 2>&1 || true`
Expected: uvicorn starts, prints `Uvicorn running on http://0.0.0.0:8080`

---

### Task 2: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Add "Network/Remote Transport" to the Features list**

After the existing `MCP Compatible` bullet, add:
```markdown
- **Network Transport**: Streamable HTTP support for remote access (e.g., WSL-Ubuntu to Windows host)
```

**Step 2: Add Server Options section after "Configure Claude Code"**

Add a new section documenting the CLI arguments:

```markdown
### Server Options

The server supports two transport modes:

| Flag | Default | Description |
|------|---------|-------------|
| `--transport` | `stdio` | Transport type: `stdio` or `streamable-http` |
| `--host` | `0.0.0.0` | Bind address (streamable-http only) |
| `--port` | `8080` | Listen port (streamable-http only) |

**Local (stdio, default):**
```bash
uv run main.py
```

**Network (Streamable HTTP):**
```bash
uv run main.py --transport streamable-http
# Server listens on http://0.0.0.0:8080/mcp
```
```

**Step 3: Add WSL-Ubuntu / Remote Client section after local Claude Code config**

```markdown
### Configure Claude Code in WSL-Ubuntu (Remote)

When running Claude Code in WSL-Ubuntu and the Delphi compiler is on the Windows host:

**1. Start the MCP server on Windows:**

```bash
cd C:\path\to\delphi-build-mcp-server
uv run main.py --transport streamable-http
```

**2. Find your Windows host IP from WSL:**

```bash
# Method 1: WSL gateway IP
cat /etc/resolv.conf | grep nameserver | awk '{print $2}'

# Method 2: Windows hostname
hostname -I  # run on Windows side
```

**3. Configure Claude Code in WSL:**

Edit `~/.claude.json` (or project-level `.mcp.json`):

```json
{
  "mcpServers": {
    "delphi-build": {
      "url": "http://<windows-host-ip>:8080/mcp"
    }
  }
}
```

> **Note:** If the connection is refused, you may need to allow port 8080 through Windows Firewall:
> ```powershell
> netsh advfirewall firewall add rule name="Delphi MCP Server" dir=in action=allow protocol=TCP localport=8080
> ```
```

---

### Task 3: Update QUICKSTART.md

**Files:**
- Modify: `QUICKSTART.md`

**Step 1: Add "Step 3b: Configure for WSL-Ubuntu (Remote)" section**

After the existing Step 3 (Configure Claude Code), add a new subsection:

```markdown
### Step 3b: Configure for WSL-Ubuntu (Remote Access)

If you run Claude Code in WSL-Ubuntu but have Delphi installed on the Windows host, use the network transport:

**On Windows -- Start the server:**

```bash
cd C:\path\to\delphi-build-mcp-server
uv run main.py --transport streamable-http
```

The server starts on `http://0.0.0.0:8080/mcp`.

**In WSL-Ubuntu -- Find the Windows host IP:**

```bash
cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
```

**In WSL-Ubuntu -- Configure Claude Code:**

Edit `~/.claude.json`:

```json
{
  "mcpServers": {
    "delphi-build": {
      "url": "http://<windows-host-ip>:8080/mcp"
    }
  }
}
```

**Test connectivity:**

```bash
curl -X POST http://<windows-host-ip>:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"capabilities":{}, "clientInfo":{"name":"test","version":"1.0"},"protocolVersion":"2025-03-26"},"id":1}'
```

If you get a JSON response, the connection works.

> **Firewall:** If the connection is refused, allow port 8080 in Windows Firewall:
> ```powershell
> netsh advfirewall firewall add rule name="Delphi MCP Server" dir=in action=allow protocol=TCP localport=8080
> ```
```

---

### Task 4: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add v1.6.0 entry at the top (below the header)**

```markdown
## [1.6.0] - 2026-02-02

### Added

- **Streamable HTTP Transport**: New `--transport streamable-http` CLI option for network access
  - Enables remote MCP clients (e.g., Claude Code in WSL-Ubuntu) to connect over TCP/IP
  - Endpoint: `http://<host>:<port>/mcp`
  - Default bind: `0.0.0.0:8080`
  - CLI flags: `--transport`, `--host`, `--port`
  - Uses MCP SDK's `StreamableHTTPSessionManager` with stateful sessions
  - No new dependencies (uvicorn, starlette already included in MCP SDK)
- **Server CLI Options**: `--transport`, `--host`, `--port` command-line arguments
  - Default transport remains `stdio` (no breaking changes)
- **WSL-Ubuntu Documentation**: Setup guide for using the Delphi MCP server from WSL

```

---

### Task 5: Update pyproject.toml version

**Files:**
- Modify: `pyproject.toml`

**Step 1: Bump version to 1.6.0**

Change `version = "1.5.0"` to `version = "1.6.0"`.
