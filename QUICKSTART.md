# Quick Start Guide

Get the Delphi Build MCP Server up and running in 5 minutes.

## Prerequisites

- **Delphi** 11, 12, or 13 installed
- **Python** 3.10 or higher
- **Claude Code** or another MCP-compatible client

## Step 1: Install UV and the MCP Server

First, install UV if you haven't already:

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip
pip install uv
```

Then install the MCP server:

```bash
cd delphi-build-mcp-server

# Create virtual environment and install dependencies
uv venv
uv pip install -e .
```

## Step 2: Generate Configuration from IDE Build Log

The config generator uses **multi-line parsing** with `re.DOTALL` to extract 80+ library paths from your IDE build log. This is fully functional and tested.

### 2.1 Create Build Log(s) in Delphi IDE

1. Open your Delphi project in the IDE
2. Go to **Tools → Options → Building → Compiling and Running**
3. Set **Show compiler progress** to "Verbose"
4. Build your project (**Project → Build**)
5. Go to **View → Messages** window
6. Right-click in the Messages pane → **Copy All**
7. Save to a file named `build.log`

**For Multi-Platform Projects (Win32/Win64/Linux64):**
1. Build with each Platform/Config combination you need
2. Save each build log separately:
   - `build_debug_win32.log`
   - `build_release_win32.log`
   - `build_debug_linux64.log`
   - etc.

**Alternative Method:**
- In the Messages window, click **View → Message View Options**
- Enable "Save messages to file"
- Build your project
- The log will be saved automatically

### 2.2 Generate Config File

**Single Build Log (Simple Projects):**

```bash
uv run python -m src.config_generator build.log
```

**Multiple Build Logs (Multi-Platform Projects):**

Use the MCP tool from Claude Code:
```
Please generate a Delphi configuration from these build logs:
- X:\path\to\build_debug_win32.log
- X:\path\to\build_release_win32.log
- X:\path\to\build_debug_linux64.log
```

Or use the Python API:
```python
from src.multi_config_generator import MultiConfigGenerator
from pathlib import Path

generator = MultiConfigGenerator(use_env_vars=True)
result = generator.generate_from_build_logs(
    build_log_paths=[
        "build_debug_win32.log",
        "build_release_linux64.log"
    ]
)
# Creates: delphi_config_win32.toml, delphi_config_linux64.toml
```

By default, this creates separate platform-specific config files with:
- Platform-specific library paths
- Platform-specific compiler flags (e.g., `--libpath` for Linux64)

Use `generate_separate_files=False` for a single unified config instead.

## Step 3: Configure Claude Code

Add the MCP server to your Claude Code configuration file.

### On Windows

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

**Option 1: Using UV (Recommended)**

```json
{
  "mcpServers": {
    "delphi-build": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "X:\\path\\to\\delphi-build-mcp-server",
        "python",
        "main.py"
      ],
      "env": {
        "DELPHI_CONFIG": "X:\\path\\to\\delphi_config.toml"
      }
    }
  }
}
```

**Option 2: Direct Python from UV environment**

```json
{
  "mcpServers": {
    "delphi-build": {
      "command": "X:\\path\\to\\delphi-build-mcp-server\\.venv\\Scripts\\python.exe",
      "args": [
        "X:\\path\\to\\delphi-build-mcp-server\\main.py"
      ],
      "env": {
        "DELPHI_CONFIG": "X:\\path\\to\\delphi_config.toml"
      }
    }
  }
}
```

### On macOS/Linux (if running Delphi via Wine)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

**Option 1: Using UV (Recommended)**

```json
{
  "mcpServers": {
    "delphi-build": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/delphi-build-mcp-server",
        "python",
        "main.py"
      ],
      "env": {
        "DELPHI_CONFIG": "/path/to/delphi_config.toml"
      }
    }
  }
}
```

**Option 2: Direct Python from UV environment**

```json
{
  "mcpServers": {
    "delphi-build": {
      "command": "/path/to/delphi-build-mcp-server/.venv/bin/python",
      "args": [
        "/path/to/delphi-build-mcp-server/main.py"
      ],
      "env": {
        "DELPHI_CONFIG": "/path/to/delphi_config.toml"
      }
    }
  }
}
```

## Step 4: Restart Claude Code

Close and reopen Claude Code to load the MCP server.

## Step 5: Test Compilation

In Claude Code, try compiling a project:

```
Please compile my Delphi project at X:\MyProject\MyApp.dproj
```

The MCP server will:
1. Parse the .dproj file to get build settings
2. Use the config file for library paths
3. Run the compiler
4. Return only errors (warnings and hints filtered out)

## Verification

If everything is working, you should see:

```json
{
  "success": true,
  "exit_code": 0,
  "errors": [],
  "compilation_time_seconds": 2.5,
  "output_executable": "X:\\MyProject\\Win32\\Debug\\MyApp.exe"
}
```

## Troubleshooting

### Issue: "Delphi compiler not found"

**Solution:** Check your `delphi_config.toml` file:

```toml
[delphi]
version = "23.0"  # Verify this matches your Delphi version
root_path = "C:/Program Files (x86)/Embarcadero/Studio/23.0"  # Verify this path exists
```

### Issue: "Unit XYZ not found"

**Solution:** Your build log may not have captured all library paths. Options:

1. **Rebuild with verbose output** and regenerate config
2. **Manually add the missing path** to `delphi_config.toml`:

```toml
[paths.libraries]
# ... existing paths ...
missing_library = "X:/path/to/missing/library"
```

3. **Use the project's original search paths** by ensuring the .dproj file is up to date

### Issue: MCP server not appearing in Claude Code

**Solution:**
1. Check the config file path is correct
2. Verify Python is in your PATH
3. Check Claude Code logs: `%APPDATA%\Claude\logs\`
4. Ensure JSON syntax is valid (no trailing commas)

## Key Features (All Automatic)

The MCP server handles these automatically - no configuration needed:

- ✅ **Response Files**: Command lines >8000 chars handled via @file.rsp
- ✅ **Multi-Language**: Parses both English and German compiler output
  - German: Fehler, Warnung, Hinweis, Schwerwiegend
  - English: Error, Warning, Hint, Fatal
- ✅ **Multi-Line Parsing**: Extracts 80+ paths from complex build logs
- ✅ **Smart Path Handling**: RTL/VCL source paths excluded (only lib_*.dcu used)
- ✅ **80+ Library Support**: Handles projects with extensive dependencies
- ✅ **Cross-Platform**: Supports Win32, Win64, and Linux64 compilation
- ✅ **Multi-Config**: Generate platform-specific configs from multiple build logs (Debug/Release × platforms)

## Next Steps

- Read [DOCUMENTATION.md](DOCUMENTATION.md) for complete feature documentation
- Learn about all available tools and parameters
- Understand how .dproj parsing works
- Configure advanced options

## Common Workflows

### Workflow 1: Fix Compilation Errors with AI

```
User: Please compile MyApp.dproj and fix any errors you find

Claude: I'll compile the project first...
[Uses compile_delphi_project tool]

I found 3 errors:
1. Unit1.pas(42): Undeclared identifier 'FooBar'
2. Unit2.pas(15): Type mismatch

Let me fix these...
[Reads files, makes fixes, recompiles]

All errors fixed! The project now compiles successfully.
```

### Workflow 2: Debug Configuration Issues

```
User: The compilation is failing with "Unit System.JSON not found"

Claude: Let me check your namespace configuration...
[Reads delphi_config.toml]

Your namespace prefixes are missing "System". Let me add it...
[Edits config file, recompiles]

Fixed! Added "System" to namespace prefixes.
```

### Workflow 3: New Project Setup

```
User: I just installed Delphi on a new machine. Help me set up the MCP server.

Claude: Let's get you set up:

1. First, build any Delphi project in the IDE with verbose output
2. Save the build log
3. I'll generate the config file from it

Please paste your build log or tell me where it's saved.

[User provides log]

Perfect! I've generated the config file with 47 library paths.
The server is now ready to compile your projects.
```

### Workflow 4: Multi-Platform Linux64 Setup

```
User: I need to compile my project for both Windows and Linux.

Claude: I'll help you set up cross-platform compilation. Please:

1. In Delphi IDE, select Platform = Win32, Config = Debug
2. Build the project and save the build log as build_debug_win32.log
3. Select Platform = Linux64, Config = Debug
4. Build and save as build_debug_linux64.log

[User provides logs]

I'll generate platform-specific configs from both build logs...

[Uses generate_config_from_multiple_build_logs tool]

Done! Generated delphi_config_win32.toml and delphi_config_linux64.toml.
Let me compile for Linux64 to verify...

[Compiles with override_platform: "Linux64"]

Success! Your project compiles for:
- Win32 Debug: 1.05s
- Linux64 Debug: 2.72s
```

## Tips

1. **Always use .dproj files** - They contain all compiler settings and ensure IDE-matching behavior
2. **Update config when adding libraries** - Regenerate from a fresh build log after installing new components
3. **Use Debug configuration for development** - The MCP server compiles whatever config is active in the .dproj
4. **Check filtered warnings** - The response includes statistics on how many warnings/hints were filtered
5. **Rebuild when needed** - Use `force_build_all: true` parameter if incremental compilation causes issues

## Support

- **Issues**: https://github.com/your-org/delphi-build-mcp-server/issues
- **Discussions**: https://github.com/your-org/delphi-build-mcp-server/discussions
- **Documentation**: [DOCUMENTATION.md](DOCUMENTATION.md)
