# Delphi Build MCP Server

A Model Context Protocol (MCP) server that enables AI coding agents like Claude Code to compile Delphi projects programmatically.

## Features

- **Automatic Configuration**: Generate config from IDE build logs with multi-line parsing
- **Smart Compilation**: Reads .dproj files for build settings and compiler flags
- **Filtered Output**: Returns only errors, filters out warnings and hints
- **Multi-Language Support**: Parses both English and German compiler output
- **Response File Support**: Handles command lines >8000 characters automatically
- **Multi-Platform**: Supports Win32 and Win64 compilation
- **80+ Library Paths**: Successfully handles projects with extensive dependencies
- **Environment Variables**: Auto-expands `${USERNAME}` in paths
- **MCP Compatible**: Works with Claude Code, Cline, and other MCP clients

## Quick Start

### 1. Install

```bash
# Install UV if you haven't already
# Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: pip install uv

cd delphi-build-mcp-server
uv sync
```

### 2. Generate Configuration

In Delphi IDE:
1. Tools -> Options -> Building -> Show compiler progress -> "Verbose"
2. Build your project
3. View -> Messages -> Right-click -> Copy All
4. Save to `build.log`

Then generate config:

```bash
uv run python -m src.config_generator build.log
```

Or use the Python API:

```python
from src.config_generator import ConfigGenerator
from pathlib import Path

generator = ConfigGenerator()
result = generator.generate_from_build_log(
    build_log_path=Path("build.log"),
    output_path=Path("delphi_config.toml")
)
print(result.message)
```

### 3. Configure Claude Code

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

**Using UV (Recommended):**

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

**Or use direct Python path:**

```json
{
  "mcpServers": {
    "delphi-build": {
      "command": "X:\\path\\to\\delphi-build-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["X:\\path\\to\\delphi-build-mcp-server\\main.py"],
      "env": {
        "DELPHI_CONFIG": "X:\\path\\to\\delphi_config.toml"
      }
    }
  }
}
```

### 4. Use in Claude Code

```
Please compile my Delphi project at X:\MyProject\MyApp.dproj
```

## Tools

### `compile_delphi_project`

Compile a Delphi project and return parsed results.

**Parameters:**
- `project_path` (required): Path to .dpr or .dproj file
- `force_build_all`: Force rebuild all units
- `override_config`: Override build config (Debug/Release)
- `override_platform`: Override platform (Win32/Win64)
- `additional_search_paths`: Extra search paths
- `additional_flags`: Additional compiler flags

**Returns:**
- `success`: Whether compilation succeeded
- `errors`: List of compilation errors (warnings/hints filtered)
- `compilation_time_seconds`: Time taken
- `output_executable`: Path to compiled EXE
- `statistics`: Compilation statistics

### `generate_config_from_build_log`

Generate `delphi_config.toml` from an IDE build log.

**Parameters:**
- `build_log_path` (required): Path to build log file
- `output_config_path`: Output file path (default: delphi_config.toml)
- `use_env_vars`: Replace paths with ${USERNAME} (default: true)

**Returns:**
- `success`: Whether generation succeeded
- `config_file_path`: Path to generated config
- `statistics`: Paths found and processed
- `detected_info`: Delphi version, platform, build config

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute setup guide
- **[DOCUMENTATION.md](DOCUMENTATION.md)** - Complete reference
- **[PRD.md](PRD.md)** - Product requirements and specifications

## Project Structure

```
delphi-build-mcp-server/
├── main.py                       # MCP server entry point
├── src/
│   ├── models.py                 # Pydantic data models
│   ├── buildlog_parser.py        # Parse IDE build logs
│   ├── dproj_parser.py           # Parse .dproj files
│   ├── config.py                 # Load TOML configuration
│   ├── output_parser.py          # Parse compiler output
│   ├── config_generator.py       # Generate TOML configs
│   └── compiler.py               # Compiler orchestration
├── delphi_config.toml.template   # Configuration template
├── pyproject.toml                # Python project config
├── QUICKSTART.md                 # Quick start guide
├── DOCUMENTATION.md              # Complete documentation
└── PRD.md                        # Product requirements
```

## Requirements

- Python 3.10+
- Delphi 11, 12, or 13
- MCP-compatible client (Claude Code, Cline, etc.)

## How It Works

**Note:** The server automatically handles response files for projects with 80+ library paths (command lines >8000 chars) and parses both English and German compiler output.

```
1. AI Agent calls compile_delphi_project
   |
   v
2. MCP Server loads delphi_config.toml
   - Delphi installation paths
   - Library search paths
   |
   v
3. Parse .dproj file
   - Active configuration (Debug/Release)
   - Compiler flags and defines
   - Project-specific search paths
   |
   v
4. Build compiler command
   - Merge config file + .dproj settings
   - Add search paths, namespaces, aliases
   |
   v
5. Execute dcc32.exe/dcc64.exe
   |
   v
6. Parse output
   - Extract errors (E####, F####)
   - Filter warnings (W####) and hints (H####)
   |
   v
7. Return structured result to AI
```

## Example Usage

### Compile a Project

```python
from src.compiler import DelphiCompiler
from pathlib import Path

compiler = DelphiCompiler()
result = compiler.compile_project(
    project_path=Path("X:/MyProject/MyApp.dproj")
)

if result.success:
    print(f"Compilation successful: {result.output_executable}")
else:
    print(f"Compilation failed with {len(result.errors)} errors:")
    for error in result.errors:
        print(f"  {error.file}({error.line},{error.column}): {error.message}")
```

### Generate Config from Build Log

```python
from src.config_generator import ConfigGenerator
from pathlib import Path

generator = ConfigGenerator(use_env_vars=True)
result = generator.generate_from_build_log(
    build_log_path=Path("build.log"),
    output_path=Path("delphi_config.toml")
)

print(f"{result.message}")
print(f"  Detected: Delphi {result.detected_info.delphi_version}")
print(f"  Platform: {result.detected_info.platform}")
print(f"  Paths found: {result.statistics['unique_paths']}")
```

## Troubleshooting

### "Configuration file not found"

Generate it from a build log:
```bash
uv run python -m src.config_generator build.log
```

### "Unit not found"

Regenerate config from a fresh IDE build log that includes all dependencies.

### "Compiler not found"

Verify `delphi.root_path` in `delphi_config.toml` points to your Delphi installation.

## Development

### Install Development Dependencies

```bash
uv pip install -e ".[dev]"
```

### Run Tests

```bash
uv run pytest
```

### Test Sample Projects

Two sample projects are included for testing:

```bash
# Test successful compilation
uv run python test_compile_samples.py
```

- **sample/working/Working.dproj** - Compiles successfully
- **sample/broken/Broken.dproj** - Intentionally has errors for testing error parsing

### Code Formatting

```bash
uv run black src/
uv run ruff check src/
```

## Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**: [DOCUMENTATION.md](DOCUMENTATION.md)
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Issues**: https://github.com/your-org/delphi-build-mcp-server/issues

## Acknowledgments

- Built with [Model Context Protocol](https://modelcontextprotocol.io)
- Designed for [Claude Code](https://claude.com/claude-code)
- Supports [Embarcadero Delphi](https://www.embarcadero.com/products/delphi)
